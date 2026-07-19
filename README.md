# 商品庫存查詢（Vercel 版）

前端靜態頁 + Python 後端函式，一個 Vercel 專案搞定。
API Key 放在 Vercel 環境變數，前端看不到。

## 結構
- `index.html` — 前端（Vercel 自動以靜態檔提供在 /）
- `api/index.py` — 後端函式（/api/lookup、/api/fields）
- `vercel.json` — 把 /api/* 導到函式
- `requirements.txt` — 後端相依套件

## 部署步驟
1. 把這個資料夾推到 GitHub（或用 Vercel CLI）。
2. 在 Vercel 匯入這個 repo，框架選 "Other"，其餘用預設。
3. 到 Project → Settings → Environment Variables 設定：
   - `RAGIC_API_KEY` = 你的（唯讀）API Key
   - `RAGIC_URL` = https://ap14.ragic.com/homedesyne/ragicinventory/20002
   （可選）`RAGIC_FIELD_CODE` / `RAGIC_FIELD_NAME` / `RAGIC_FIELD_QTY`
4. Deploy。打開 https://你的專案.vercel.app 就能用。

## 先確認欄位抓對
部署後開 `https://你的專案.vercel.app/api/fields`，
會列出實際欄位名與自動比對結果。抓錯就用環境變數指定欄位名再重新部署。

## 本機測試
```bash
pip install -r requirements.txt uvicorn
RAGIC_API_KEY=你的KEY uvicorn api.index:app --port 8000
# 開 http://localhost:8000
```

## 安全
- API Key 只放 Vercel 環境變數，不要寫進程式或 commit。
- 目前用唯讀 key 測試很好；日後若要做「改庫存」才需要有寫入權限的 key。
