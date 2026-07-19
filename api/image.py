import json
import os
import sys
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, os.path.dirname(__file__))
import _ragic as R  # noqa: E402


def _guess_ctype(name):
    n = name.lower()
    if n.endswith(".png"):
        return "image/png"
    if n.endswith(".gif"):
        return "image/gif"
    if n.endswith(".webp"):
        return "image/webp"
    if n.endswith(".bmp"):
        return "image/bmp"
    return "image/jpeg"


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        f = (parse_qs(urlparse(self.path).query).get("f", [""])[0] or "").strip()
        try:
            if not f.lower().endswith(R.IMG_EXT):
                return self._err(400, "檔名格式不正確")

            content, ctype = R.fetch_image(f)
            ctype = (ctype or "").lower()
            # 若回傳的是網頁（HTML），代表被導向登入頁 → 認證/權限問題
            if "html" in ctype or "text/" in ctype:
                return self._err(
                    502, "取得圖片失敗（被導向登入頁，可能是圖片權限或認證問題）"
                )
            # 有些情況 content-type 不是標準 image，依副檔名補上
            if "image" not in ctype:
                ctype = _guess_ctype(f)

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
