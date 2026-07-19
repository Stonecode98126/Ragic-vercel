import json
import os
import sys
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, os.path.dirname(__file__))
import _ragic as R  # noqa: E402


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        qs = parse_qs(urlparse(self.path).query)
        code = (qs.get("code", [""])[0] or "").strip()
        try:
            if not code:
                return self._send(400, {"error": "缺少 code 參數"})

            data = R.fetch_json({"fts": code, "subtables": "0"})
            if not data:
                return self._send(404, {"found": False, "code": code})

            sample = next(iter(data.values()))
            code_key = R.resolve_key(sample, R.FIELD_CODE, R.CODE_TOKENS)
            name_key = R.resolve_key(sample, R.FIELD_NAME, R.NAME_TOKENS)
            qty_key = R.resolve_key(sample, R.FIELD_QTY, R.QTY_TOKENS)

            if not code_key:
                return self._send(500, {
                    "error": "找不到『商品編號』欄位，請開 /api/fields 查看實際欄位名"
                })

            exact = [
                rec for rec in data.values()
                if str(rec.get(code_key, "")).strip() == code
            ]
            if not exact:
                return self._send(404, {"found": False, "code": code})

            results = [{
                "code": str(rec.get(code_key, "")).strip(),
                "name": str(rec.get(name_key, "")).strip() if name_key else "",
                "qty": str(rec.get(qty_key, "")).strip() if qty_key else "",
                "image": R.first_image_value(rec) or "",
            } for rec in exact]

            self._send(200, {
                "found": True, "code": code,
                "result": results[0], "all": results,
            })
        except R.RagicError as e:
            self._send(e.status, {"error": e.message})
        except Exception as e:  # noqa: BLE001
            self._send(500, {"error": f"伺服器錯誤：{e}"})

    def _send(self, status, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
