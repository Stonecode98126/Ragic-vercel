# /api/update  —  把庫存數量寫回 Ragic
#
# 前端會 POST 一段 JSON：{ "code": "商品編號", "qty": 新的庫存數字 }
# 這支程式會：
#   1. 用商品編號在 Ragic 找到那筆資料（拿到它的記錄 ID _ragicId）
#   2. 找出「庫存數量」欄位的「數字欄位 ID」（可自動偵測，或用環境變數指定）
#   3. 用 Ragic 的寫入 API 把新數量存回去
#
# 只用 Python 內建功能，不裝任何套件（跟這個專案其它 api/*.py 一致）。
#
# 需要的環境變數（Vercel → Settings → Environment Variables）：
#   RAGIC_API_KEY   ← 必填。要「可編輯」權限的 Key（唯讀 Key 只能查、不能存檔）
#   RAGIC_URL       ← 必填。例：https://ap14.ragic.com/homedesyne/ragicinventory/20002
#   RAGIC_FIELD_CODE   （選填）商品編號欄位的「中文名稱」，抓錯時再指定
#   RAGIC_FIELD_QTY    （選填）庫存數量欄位的「中文名稱」，抓錯時再指定
#   RAGIC_FIELD_QTY_ID （選填）庫存數量欄位的「數字欄位 ID」。設了這個最保險，
#                       就不用自動偵測。到 /api/fields 或 Ragic 表單設計裡可查到。

import os
import json
import urllib.request
import urllib.parse
import urllib.error
from http.server import BaseHTTPRequestHandler


# ── Ragic 連線設定 ──────────────────────────────
API_KEY = os.environ.get("RAGIC_API_KEY", "")
BASE    = os.environ.get("RAGIC_URL", "").rstrip("/")

# 欄位名稱：沒指定就用關鍵字自動猜
FIELD_CODE_ENV = os.environ.get("RAGIC_FIELD_CODE", "").strip()
FIELD_QTY_ENV  = os.environ.get("RAGIC_FIELD_QTY", "").strip()
FIELD_QTY_ID_ENV = os.environ.get("RAGIC_FIELD_QTY_ID", "").strip()

CODE_HINTS = ["商品編號", "編號", "貨號", "料號", "code", "sku", "barcode"]
QTY_HINTS  = ["庫存數量", "庫存", "數量", "存量", "qty", "stock", "quantity"]


def _headers():
    # Ragic 的特例：把 API Key 直接接在 "Basic " 後面（不是標準 base64）
    return {"Authorization": "Basic " + API_KEY}


def _get_json(url):
    req = urllib.request.Request(url, headers=_headers(), method="GET")
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _guess_field(sample_record, hints, explicit=""):
    """從一筆資料的欄位名稱中，用關鍵字挑出對應欄位名。"""
    names = [k for k in sample_record.keys() if not str(k).startswith("_")]
    if explicit and explicit in sample_record:
        return explicit
    # 先找完全一樣的，再找包含關鍵字的
    for h in hints:
        for n in names:
            if n == h:
                return n
    for h in hints:
        for n in names:
            if h.lower() in str(n).lower():
                return n
    return None


def _find_record(code):
    """用商品編號找到那筆資料，回傳 (ragicId, record_dict, code_field_name, qty_field_name)。"""
    code_norm = str(code).strip().lower()

    # 先用全文檢索 fts 縮小範圍；若沒結果，退而讀整份清單再比對
    candidates = {}
    try:
        url = BASE + "?api&v=3&fts=" + urllib.parse.quote(str(code))
        candidates = _get_json(url) or {}
    except Exception:
        candidates = {}

    if not isinstance(candidates, dict) or not candidates:
        url = BASE + "?api&v=3"
        candidates = _get_json(url) or {}

    if not isinstance(candidates, dict):
        return None

    code_field = None
    qty_field  = None

    for rid, rec in candidates.items():
        if not isinstance(rec, dict):
            continue
        if code_field is None:
            code_field = _guess_field(rec, CODE_HINTS, FIELD_CODE_ENV)
            qty_field  = _guess_field(rec, QTY_HINTS, FIELD_QTY_ENV)
        if not code_field:
            continue
        val = str(rec.get(code_field, "")).strip().lower()
        if val == code_norm:
            ragic_id = rec.get("_ragicId", rid)
            return (str(ragic_id), rec, code_field, qty_field)

    return None


def _resolve_qty_field_id(ragic_id, qty_field_name, name_record):
    """找出庫存數量欄位的『數字欄位 ID』。

    優先用環境變數 RAGIC_FIELD_QTY_ID；否則把同一筆資料分別用
    欄位名稱(FNAME) 與 欄位ID(EID) 讀一次，依欄位順序配對出 ID。
    """
    if FIELD_QTY_ID_ENV:
        return FIELD_QTY_ID_ENV

    if not qty_field_name:
        return None

    # 用 EID 命名再讀一次同一筆
    id_record = _get_json(BASE + "/" + ragic_id + "?api&v=3&naming=EID")
    if not isinstance(id_record, dict):
        return None

    name_fields = [k for k in name_record.keys() if not str(k).startswith("_")]
    id_fields   = [k for k in id_record.keys()   if not str(k).startswith("_")]

    # 主要方法：同一份表單，兩種命名的欄位順序一致 → 直接依序配對
    if len(name_fields) == len(id_fields):
        pairing = dict(zip(name_fields, id_fields))
        fid = pairing.get(qty_field_name)
        if fid:
            return str(fid)

    # 備援：用「數值相同且唯一」的欄位反推 ID
    qty_val = str(name_record.get(qty_field_name, ""))
    matches = [fid for fid in id_fields if str(id_record.get(fid, "")) == qty_val]
    if len(matches) == 1:
        return str(matches[0])

    return None


def _write_qty(ragic_id, qty_field_id, new_qty):
    """用 Ragic 寫入 API 更新單一欄位。"""
    body = urllib.parse.urlencode({str(qty_field_id): str(new_qty), "api": ""}).encode("utf-8")
    url = BASE + "/" + ragic_id + "?api"
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "Authorization": "Basic " + API_KEY,
        "Content-Type": "application/x-www-form-urlencoded",
    })
    with urllib.request.urlopen(req, timeout=20) as resp:
        raw = resp.read().decode("utf-8")
    try:
        return json.loads(raw)
    except Exception:
        return {"status": "UNKNOWN", "raw": raw}


class handler(BaseHTTPRequestHandler):
    def _send(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        # 設定檢查
        if not API_KEY or not BASE:
            return self._send(500, {"ok": False, "error": "後端未設定 RAGIC_API_KEY 或 RAGIC_URL"})

        # 讀取前端傳來的 JSON
        try:
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
        except Exception:
            return self._send(400, {"ok": False, "error": "請求格式錯誤（需要 JSON）"})

        code = str(data.get("code", "")).strip()
        qty_raw = data.get("qty", None)
        if not code:
            return self._send(400, {"ok": False, "error": "缺少商品編號 code"})
        try:
            new_qty = int(float(qty_raw))
        except Exception:
            return self._send(400, {"ok": False, "error": "數量 qty 必須是數字"})
        if new_qty < 0:
            new_qty = 0

        # 1) 找到那筆資料
        try:
            found = _find_record(code)
        except Exception as e:
            return self._send(502, {"ok": False, "error": "查詢 Ragic 失敗：" + str(e)})
        if not found:
            return self._send(404, {"ok": False, "error": "查無此編號：" + code})
        ragic_id, rec, code_field, qty_field = found

        # 2) 找到庫存欄位的數字 ID
        try:
            qty_id = _resolve_qty_field_id(ragic_id, qty_field, rec)
        except Exception as e:
            return self._send(502, {"ok": False, "error": "取得欄位 ID 失敗：" + str(e)})
        if not qty_id:
            return self._send(500, {"ok": False, "error":
                "找不到庫存數量欄位的 ID。請在 Vercel 環境變數設定 RAGIC_FIELD_QTY_ID（庫存欄位的數字 ID）後再試。"})

        # 3) 寫回 Ragic
        try:
            result = _write_qty(ragic_id, qty_id, new_qty)
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = e.read().decode("utf-8")
            except Exception:
                pass
            return self._send(502, {"ok": False, "error": "寫入 Ragic 失敗（HTTP %s）。可能是 Key 沒有編輯權限。" % e.code, "detail": detail[:300]})
        except Exception as e:
            return self._send(502, {"ok": False, "error": "寫入 Ragic 失敗：" + str(e)})

        status = str(result.get("status", "")).upper()
        if status and status not in ("SUCCESS", "UNKNOWN"):
            return self._send(502, {"ok": False, "error": "Ragic 回報未成功：" + json.dumps(result, ensure_ascii=False)[:300]})

        return self._send(200, {"ok": True, "code": code, "qty": new_qty, "ragicId": ragic_id, "fieldId": qty_id})

    # 讓瀏覽器的 CORS 預檢 / 誤用 GET 時有明確回應
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Allow", "POST, OPTIONS")
        self.end_headers()

    def do_GET(self):
        self._send(405, {"ok": False, "error": "這個網址只接受 POST（由頁面上的存檔按鈕呼叫）"})
