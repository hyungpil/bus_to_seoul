"""실시간 모니터링 웹 대시보드 (표준 라이브러리 http.server)."""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import db
from .config import KST
from .naver import NaverBusClient
from .service import live_status, stats

log = logging.getLogger(__name__)
STATIC = Path(__file__).parent / "static" / "index.html"
CACHE_SEC = 20

_client = NaverBusClient()
_cache = {"t": 0.0, "data": None}
_lock = threading.Lock()


def cached_live():
    with _lock:
        if time.time() - _cache["t"] > CACHE_SEC or _cache["data"] is None:
            conn = db.connect()
            try:
                _cache["data"] = live_status(_client, conn)
            finally:
                conn.close()
            _cache["t"] = time.time()
        return _cache["data"]


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        cors_origin = os.environ.get("BUS_CORS_ORIGIN", "*")
        self.send_header("Access-Control-Allow-Origin", cors_origin)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj):
        self._send(200, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def do_GET(self):
        path = self.path.split("?")[0]
        try:
            if path in ("/", "/index.html"):
                self._send(200, STATIC.read_bytes(), "text/html; charset=utf-8")
            elif path == "/healthz":
                self._send(200, b"ok", "text/plain; charset=utf-8")
            elif path == "/api/health":
                self._json({"status": "ok", "now": db.fmt(datetime.now(KST))})
            elif path == "/api/live":
                self._json(cached_live())
            elif path == "/api/stats":
                conn = db.connect()
                try:
                    self._json(stats(conn))
                finally:
                    conn.close()
            else:
                self._send(404, b"not found", "text/plain")
        except Exception as e:
            log.exception("request failed")
            self._send(500, json.dumps({"error": str(e)}).encode(), "application/json")

    def do_OPTIONS(self):
        self.send_response(204)
        cors_origin = os.environ.get("BUS_CORS_ORIGIN", "*")
        self.send_header("Access-Control-Allow-Origin", cors_origin)
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def log_message(self, fmt, *args):
        log.debug(fmt, *args)


def serve(host: str, port: int):
    srv = ThreadingHTTPServer((host, port), Handler)
    log.info("대시보드: http://%s:%d", host, port)
    print(f"대시보드: http://{host}:{port}  (Ctrl+C 종료)")
    srv.serve_forever()
