"""
商品庫存查詢 — Vercel 後端函式

部署在 Vercel。API Key 放在 Vercel 專案的環境變數 RAGIC_API_KEY，
永遠不會出現在前端瀏覽器裡。前端與本 API 同網域，不需處理 CORS。

路由：
  GET /api/lookup?code=商品編號   → 回傳名稱與庫存數量
  GET /api/fields                 → 除錯用，列出實際欄位名
"""

import os

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

# ── 設定（在 Vercel 環境變數設定，勿寫死在程式裡）──────────
API_KEY = os.getenv("RAGIC_API_KEY", "")
RAGIC_URL = os.getenv(
    "RAGIC_URL",
    "https://ap14.ragic.com/homedesyne/ragicinventory/20002",
)

FIELD_CODE = os.getenv("RAGIC_FIELD_CODE", "").strip()
FIELD_NAME = os.getenv("RAGIC_FIELD_NAME", "").strip()
FIELD_QTY = os.getenv("RAGIC_FIELD_QTY", "").strip()

CODE_TOKENS = ["商品編號", "編號", "貨號", "料號", "品號", "SKU"]
NAME_TOKENS = ["商品名稱", "品名", "名稱"]
QTY_TOKENS = ["庫存數量", "庫存", "在庫", "存量", "數量"]

# 若你另外還有前端放在別的網域（例如 GitHub Pages），把網域填進來。
# 同網域（都在 Vercel）時可留空。
ALLOWED_ORIGINS = [
    o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()
]

app = FastAPI(title="商品庫存查詢")

if ALLOWED_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_methods=["GET"],
        allow_headers=["*"],
    )


def _headers() -> dict:
    if not API_KEY:
        raise HTTPException(500, "伺服器未設定 RAGIC_API_KEY（請在 Vercel 環境變數設定）")
    return {"Authorization": f"Basic {API_KEY}"}


def _resolve_key(sample: dict, configured: str, tokens: list):
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


@app.get("/api/fields")
async def fields():
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
async def lookup(code: str = Query(..., min_length=1)):
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
            "找不到『商品編號』欄位，請開 /api/fields 查看實際欄位名，"
            "並在環境變數設定 RAGIC_FIELD_CODE",
        )

    exact = [
        rec for rec in data.values()
        if str(rec.get(code_key, "")).strip() == code
    ]
    if not exact:
        return JSONResponse({"found": False, "code": code}, status_code=404)

    results = [{
        "code": str(rec.get(code_key, "")).strip(),
        "name": str(rec.get(name_key, "")).strip() if name_key else "",
        "qty": str(rec.get(qty_key, "")).strip() if qty_key else "",
    } for rec in exact]

    return {"found": True, "code": code, "result": results[0], "all": results}


# 本機測試用：讓 uvicorn 也能提供前端頁面（Vercel 上由靜態檔提供，不會用到）
@app.get("/")
def index():
    path = os.path.join(os.path.dirname(__file__), "..", "index.html")
    if os.path.exists(path):
        return FileResponse(path)
    return JSONResponse({"ok": True, "hint": "API 正常運作中，前端請開 index.html"})
