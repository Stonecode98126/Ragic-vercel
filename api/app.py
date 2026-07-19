"""
商品庫存查詢 — 後端代理

作用：把 Ragic 的 API Key 藏在伺服器端，前端只透過本服務查詢，
金鑰永遠不會出現在瀏覽器裡。

查詢邏輯：用 Ragic 的全文檢索 (fts) 找出含有該編號的資料，
再用「商品編號」欄位做精確比對，回傳「商品名稱」與「庫存數量」。
因此不需要事先知道 Ragic 的數字欄位 ID，直接用中文欄位名比對。
"""

import os

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse

load_dotenv()

# ── 設定（可用環境變數覆蓋）────────────────────────────────
API_KEY = os.getenv("RAGIC_API_KEY", "")
# 你的表單 API 端點（帳號 / 頁籤資料夾 / 表單序號）
RAGIC_URL = os.getenv(
    "RAGIC_URL",
    "https://ap14.ragic.com/homedesyne/ragicinventory/20002",
)

# 欄位名稱：留空則自動用關鍵字比對（見下方 *_TOKENS）
FIELD_CODE = os.getenv("RAGIC_FIELD_CODE", "").strip()   # 商品編號
FIELD_NAME = os.getenv("RAGIC_FIELD_NAME", "").strip()   # 商品名稱
FIELD_QTY = os.getenv("RAGIC_FIELD_QTY", "").strip()     # 庫存數量

# 自動比對用的關鍵字（找不到指定欄位時，用包含這些字的欄位名）
CODE_TOKENS = ["商品編號", "編號", "貨號", "料號", "品號", "SKU"]
NAME_TOKENS = ["商品名稱", "品名", "名稱"]
QTY_TOKENS = ["庫存數量", "庫存", "在庫", "存量", "數量"]

app = FastAPI(title="商品庫存查詢")


def _headers() -> dict:
    if not API_KEY:
        raise HTTPException(500, "伺服器未設定 RAGIC_API_KEY，請在 .env 填入 API Key")
    # Ragic 用 API Key 直接接在 "Basic " 後面（非標準 base64）
    return {"Authorization": f"Basic {API_KEY}"}


def _resolve_key(sample: dict, configured: str, tokens: list) -> str | None:
    """從一筆資料的欄位名裡找出對應的 key。"""
    if configured and configured in sample:
        return configured
    keys = [k for k in sample if not k.startswith("_")]
    # 先找完全相等
    for t in tokens:
        if t in keys:
            return t
    # 再找包含關鍵字
    for k in keys:
        if any(t in k for t in tokens):
            return k
    return None


async def _fetch(params: dict) -> dict:
    query = {"api": "", "v": "3", **params}
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(RAGIC_URL, params=query, headers=_headers())
    if r.status_code == 401:
        raise HTTPException(502, "Ragic 認證失敗：API Key 可能不正確或已失效")
    if r.status_code != 200:
        raise HTTPException(502, f"Ragic 回應異常（HTTP {r.status_code}）")
    try:
        data = r.json()
    except Exception:
        raise HTTPException(502, "Ragic 回應不是有效的 JSON（可能被導向登入頁）")
    if not isinstance(data, dict):
        raise HTTPException(502, "Ragic 回應格式非預期")
    return data


@app.get("/")
def index():
    return FileResponse(os.path.join(os.path.dirname(__file__), "index.html"))


@app.get("/api/fields")
async def fields():
    """除錯用：回傳第一筆資料的所有欄位名，讓你確認真正的欄位名稱。"""
    data = await _fetch({"limit": "1"})
    if not data:
        return {"fields": [], "note": "表單目前沒有資料"}
    first = next(iter(data.values()))
    names = [k for k in first if not k.startswith("_")]
    return {
        "fields": names,
        "matched": {
            "code": _resolve_key(first, FIELD_CODE, CODE_TOKENS),
            "name": _resolve_key(first, FIELD_NAME, NAME_TOKENS),
            "qty": _resolve_key(first, FIELD_QTY, QTY_TOKENS),
        },
    }


@app.get("/api/lookup")
async def lookup(code: str = Query(..., min_length=1, description="商品編號")):
    code = code.strip()
    data = await _fetch({"fts": code, "subtables": "0"})

    if not data:
        return JSONResponse({"found": False, "code": code}, status_code=404)

    sample = next(iter(data.values()))
    code_key = _resolve_key(sample, FIELD_CODE, CODE_TOKENS)
    name_key = _resolve_key(sample, FIELD_NAME, NAME_TOKENS)
    qty_key = _resolve_key(sample, FIELD_QTY, QTY_TOKENS)

    if not code_key:
        raise HTTPException(
            500,
            "找不到『商品編號』欄位，請到 /api/fields 查看實際欄位名，"
            "並在 .env 設定 RAGIC_FIELD_CODE",
        )

    # fts 是全文檢索，可能撈到含有該字串的其它資料，這裡用編號做精確比對
    exact = [
        rec for rec in data.values()
        if str(rec.get(code_key, "")).strip() == code
    ]

    if not exact:
        return JSONResponse({"found": False, "code": code}, status_code=404)

    results = []
    for rec in exact:
        results.append({
            "code": str(rec.get(code_key, "")).strip(),
            "name": str(rec.get(name_key, "")).strip() if name_key else "",
            "qty": str(rec.get(qty_key, "")).strip() if qty_key else "",
        })

    # 通常編號唯一，回傳第一筆；若有多筆一起帶回
    return {"found": True, "code": code, "result": results[0], "all": results}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
