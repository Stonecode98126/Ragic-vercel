import json
import os
import sys
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.dirname(__file__))
import _ragic as R  # noqa: E402


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            data = R.fetch_json({"limit": "1"})
            if not data:
                return self._send(200, {"fields": [], "note": "表單目前沒有資料"})
            first = next(iter(data.values()))
            names = [k for k in first if not k.startswith("_")]
            self._send(200, {
                "fields": names,
                "matched": {
                    "code": R.resolve_key(first, R.FIELD_CODE, R.CODE_TOKENS),
                    "name": R.resolve_key(first, R.FIELD_NAME, R.NAME_TOKENS),
                    "qty": R.resolve_key(first, R.FIELD_QTY, R.QTY_TOKENS),
                    "image_value": R.first_image_value(first),
                },
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
