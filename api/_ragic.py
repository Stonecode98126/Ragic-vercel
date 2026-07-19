"""
共用工具（不是路由，檔名以 _ 開頭，Vercel 不會把它當網址）。

只用 Python 內建模組，不需要安裝任何套件，也不需要 requirements.txt。
所有設定都從 Vercel 環境變數讀取，API Key 不會出現在前端。
"""

import json
import os
import re
import urllib.error
import urllib.request
from urllib.parse import urlencode, urlparse

# ── 設定（在 Vercel → Settings → Environment Variables 設定）──
API_KEY = os.environ.get("RAGIC_API_KEY", "")
RAGIC_URL = os.environ.get(
    "RAGIC_URL",
    "https://ap14.ragic.com/homedesyne/ragicinventory/20002",
)
FIELD_CODE = os.environ.get("RAGIC_FIELD_CODE", "").strip()
FIELD_NAME = os.environ.get("RAGIC_FIELD_NAME", "").strip()
FIELD_QTY = os.environ.get("RAGIC_FIELD_QTY", "").strip()
FIELD_IMG = os.environ.get("RAGIC_FIELD_IMG", "").strip()

CODE_TOKENS = ["商品編號", "編號", "貨號", "料號", "品號", "SKU"]
NAME_TOKENS = ["商品名稱", "品名", "名稱"]
QTY_TOKENS = ["庫存數量", "庫存", "在庫", "存量", "數量"]
IMG_TOKENS = ["商品圖", "圖片", "圖檔", "照片", "相片", "圖", "image", "photo", "img"]
IMG_EXT = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp")

# 從 RAGIC_URL 推導圖片下載用的伺服器與帳號名
_p = urlparse(RAGIC_URL)
RAGIC_SERVER = f"{_p.scheme}://{_p.netloc}"                    # https://ap14.ragic.com
_path = _p.path.strip("/")
RAGIC_ACCOUNT = _path.split("/")[0] if _path else ""           # homedesyne


class RagicError(Exception):
    def __init__(self, message, status=502):
        super().__init__(message)
        self.message = message
        self.status = status


def _auth_headers():
    if not API_KEY:
        raise RagicError("伺服器未設定 RAGIC_API_KEY（請在 Vercel 環境變數設定）", 500)
    return {"Authorization": f"Basic {API_KEY}"}


def fetch_json(params):
    """對表單發 GET，回傳 dict。"""
    url = RAGIC_URL + "?" + urlencode({"api": "", "v": "3", **params})
    req = urllib.request.Request(url, headers=_auth_headers())
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            raw = r.read()
    except urllib.error.HTTPError as e:
        if e.code == 401:
            raise RagicError("Ragic 認證失敗：API Key 可能不正確或已失效")
        raise RagicError(f"Ragic 回應異常（HTTP {e.code}）")
    except Exception as e:  # noqa: BLE001
        raise RagicError(f"連線 Ragic 失敗：{e}")

    try:
        data = json.loads(raw.decode("utf-8"))
    except Exception:  # noqa: BLE001
        raise RagicError("Ragic 回應不是有效的 JSON（可能被導向登入頁）")
    if not isinstance(data, dict):
        raise RagicError("Ragic 回應格式非預期")
    return data


def fetch_image(f):
    """抓取圖片檔，回傳 (bytes, content_type)。"""
    url = RAGIC_SERVER + "/sims/file.jsp?" + urlencode(
        {"a": RAGIC_ACCOUNT, "f": f, "APIKey": API_KEY}
    )
    req = urllib.request.Request(url, headers=_auth_headers())
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.read(), r.headers.get("Content-Type", "image/jpeg")
    except urllib.error.HTTPError as e:
        raise RagicError(f"取得圖片失敗（HTTP {e.code}）")
    except Exception as e:  # noqa: BLE001
        raise RagicError(f"取得圖片失敗：{e}")


def resolve_key(sample, configured, tokens):
    if configured and configured in sample:
        return configured
    keys = [k for k in sample if not k.startswith("_")]
    for t in tokens:
        if t in keys:
            return t
    for k in keys:
        if any(t in k for t in tokens):
            return k
    return None


def first_image_value(record):
    """找出圖片檔名（Ragic 檔案欄位值格式：hash@原始檔名.jpg）。"""
    def pick(val):
        for part in re.split(r"[\n,]", str(val)):
            part = part.strip()
            if "@" in part and part.lower().endswith(IMG_EXT):
                return part
        return None

    if FIELD_IMG and FIELD_IMG in record:
        got = pick(record[FIELD_IMG])
        if got:
            return got
    for k, v in record.items():
        if k.startswith("_"):
            continue
        got = pick(v)
        if got:
            return got
    for k, v in record.items():
        if k.startswith("_"):
            continue
        if any(t.lower() in k.lower() for t in IMG_TOKENS) and str(v).strip():
            return str(v).strip()
    return None
