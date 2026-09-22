r"""Chụp 5 tab PWA bằng Chrome headless (máy dev). Chrome không cho cửa sổ < ~500 px nên bọc trang trong iframe
420 px (bài học candle-radar). Cần docs/data/latest.json (chạy job --no-push trước).

    venv\Scripts\python -m scripts.shot            # → reports/shots/<tab>.png
"""
from __future__ import annotations

import subprocess
import sys
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
OUT = ROOT / "reports" / "shots"
CHROME = next((p for p in (r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                           r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe") if Path(p).exists()), None)
TABS = {"today": 1500, "board": 1400, "chart": 1100, "history": 1400, "settings": 1500}


class Quiet(SimpleHTTPRequestHandler):
    def log_message(self, *a):  # noqa: D401
        pass


def main() -> int:
    if not CHROME:
        print("Không thấy Chrome", file=sys.stderr)
        return 1
    OUT.mkdir(parents=True, exist_ok=True)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), partial(Quiet, directory=str(DOCS)))
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        for tab, h in TABS.items():
            frame = OUT / f"_frame_{tab}.html"
            frame.write_text(f'<!doctype html><body style="margin:0;background:#888"><iframe src="http://127.0.0.1:{port}/index.html#{tab}" '
                             f'style="width:420px;height:{h}px;border:0;display:block"></iframe></body>', encoding="utf-8")
            png = OUT / f"{tab}.png"
            subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--window-size=520,{h + 20}",
                            "--virtual-time-budget=8000", f"--screenshot={png}", frame.as_uri()],
                           check=True, capture_output=True, timeout=90)
            frame.unlink()
            print(f"{tab}: {png}")
    finally:
        srv.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
