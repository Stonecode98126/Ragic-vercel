# 商品庫存查詢（Vercel 原生 Python 版）

前端靜態頁 + Vercel 原生 Python 函式。只用 Python 內建功能，
不需安裝任何套件，也不需要 requirements.txt。API Key 放在 Vercel 環境變數。

## 結構
- `index.html` — 前端（Vercel 自動以靜態檔提供在 /）
- `api/lookup.py` — /api/lookup 查商品
- `api/fields.py` — /api/fields 列出欄位名（除錯用）
- `api/image.py`  — /api/image 代理圖片下載
- `api/_ragic.py` — 共用工具（檔名開頭是 _，不會變成網址）

## 部署
1. 把整個資料夾推到 GitHub。
2. Vercel 匯入這個 repo，Framework 選 "Other"，其餘用預設。
3. Settings → Environment Variables 設定：
   - `RAGIC_API_KEY` = 你的（唯讀）API Key
   - `RAGIC_URL` = https://ap14.ragic.com/homedesyne/ragicinventory/20002
   （可選）`RAGIC_FIELD_CODE / NAME / QTY / IMG`：自動比對抓錯欄位時才需要
4. Deploy → 打開 https://你的專案.vercel.app

## 部署後先確認欄位
瀏覽器打開 https://你的專案.vercel.app/api/fields
會列出實際欄位名，以及自動比對到的 code / name / qty / image_value。
抓錯時把對應欄位名填進上面的環境變數，重新部署即可。

## 安全
API Key 只放 Vercel 環境變數；圖片也經後端代理，金鑰不會出現在前端。
