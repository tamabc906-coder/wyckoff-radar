"""Cài đặt: docs/data/settings.json (commit trong repo) → Cloudflare Worker KV nếu có → mặc định trong code.
Chép khuôn price-path/job/settings.py, đổi DEFAULTS cho Wyckoff Radar.

events_disabled: sự kiện không push (vẫn gắn nhãn trên Bảng/Biểu đồ). Mặc định = mọi sự kiện KHÔNG đạt ★
khi đo 11 năm (scripts/measure.py, G2) — chốt sau G2; trước đó để trống để job/replay in được mọi sự kiện.
"""
from __future__ import annotations

import json
import logging

import httpx

from common.config import HTTP_TIMEOUT, SITE_DATA, WORKER_TOKEN, WORKER_URL

logger = logging.getLogger(__name__)

DEFAULTS = {
    # id sự kiện không push (xem job/wyckoff.py EVENTS). Chốt theo reports/measure-2026-09-21.md: chỉ `sc` đạt ★.
    "events_disabled": ["spring3", "test", "sos", "lps", "bu", "bc", "utad", "sow", "lpsy"],
    "buy_only": False,         # True = không push sự kiện THOÁT dù có bật
    "history_days": 30,        # số phiên hiện ở tab Lịch sử
    "heartbeat": False,        # nhịp tim thứ Hai
    "tr_min_bars": 20,         # vùng đi ngang tối thiểu (phiên) để xét tín hiệu mua
}

LOCAL = SITE_DATA / "settings.json"


def load() -> dict:
    s = dict(DEFAULTS)
    if LOCAL.exists():
        try:
            s.update(json.loads(LOCAL.read_text(encoding="utf-8")))
        except Exception as exc:  # noqa: BLE001
            logger.warning("settings.json hỏng: %s", exc)
    if WORKER_URL and WORKER_TOKEN:
        try:
            r = httpx.get(f"{WORKER_URL}/settings", headers={"Authorization": f"Bearer {WORKER_TOKEN}"},
                          timeout=HTTP_TIMEOUT)
            if r.status_code == 200 and r.text.strip():
                s.update(r.json())
                s["_source"] = "worker"
        except Exception as exc:  # noqa: BLE001
            logger.warning("Worker /settings không trả lời: %s — dùng bản local", exc)
    s["events_disabled"] = [str(x) for x in (s.get("events_disabled") or [])]
    s["tr_min_bars"] = int(s.get("tr_min_bars") or DEFAULTS["tr_min_bars"])
    return s
