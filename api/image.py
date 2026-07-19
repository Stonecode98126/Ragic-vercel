import json
import os
import sys
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, os.path.dirname(__file__))
import _ragic as R  # noqa: E402


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        f = (parse_qs(urlparse(self.path).query).get("f", [""])[0] or "").strip()
        try:
            if "@" not in f or not f.lower().endswith(R.IMG_EXT):
                return self._err(400, "檔名格式不正確")

            content, ctype = R.fetch_image(f)
            if "image" not in (ctype or ""):
                return self._err(502, "取得圖片失敗（回傳非圖片內容）")

            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "public, max-age=3600")
            self.end_headers()
            self.wfile.write(content)
        except R.RagicError as e:
            self._err(e.status, e.message)
        except Exception as e:  # noqa: BLE001
            self._err(500, f"伺服器錯誤：{e}")

    def _err(self, status, msg):
        body = json.dumps({"error": msg}, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
