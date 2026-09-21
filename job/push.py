"""Web Push qua pywebpush + VAPID. Chép từ price-path/job/push.py, đổi payload cho sự kiện Wyckoff.
Nguồn địa chỉ: Worker KV (GET /subs) → fallback PUSH_SUBS_FALLBACK (JSON trong Secret).

- configured() đòi CẢ HAI khoá: thiếu public key thì lỗi im lặng (bài học KingStock).
- 404/410 = trình duyệt đã huỷ đăng ký → báo Worker xoá và ghi vào state để giao diện hiện dòng đỏ.
"""
from __future__ import annotations

import hashlib
import json
import logging

import httpx
from pywebpush import WebPushException, webpush

from common.config import (
    HTTP_TIMEOUT, PUSH_SUBS_FALLBACK, VAPID_PRIVATE_KEY, VAPID_PUBLIC_KEY, VAPID_SUBJECT,
    WORKER_TOKEN, WORKER_URL,
)

logger = logging.getLogger(__name__)
TTL_ALERT = 16 * 3600


def configured() -> bool:
    return bool(VAPID_PRIVATE_KEY and VAPID_PUBLIC_KEY)


def _worker_headers() -> dict:
    return {"Authorization": f"Bearer {WORKER_TOKEN}"}


def subscriptions() -> tuple[list[dict], str]:
    """(danh sách subscription, nguồn). Worker trước, fallback sau."""
    if WORKER_URL and WORKER_TOKEN:
        try:
            r = httpx.get(f"{WORKER_URL}/subs", headers=_worker_headers(), timeout=HTTP_TIMEOUT)
            r.raise_for_status()
            subs = r.json()
            if isinstance(subs, dict):
                subs = list(subs.values())
            return subs, "worker"
        except Exception as exc:  # noqa: BLE001
            logger.warning("Worker /subs lỗi: %s — dùng fallback", exc)
    if PUSH_SUBS_FALLBACK.strip():
        try:
            subs = json.loads(PUSH_SUBS_FALLBACK)
            return (subs if isinstance(subs, list) else [subs]), "fallback"
        except json.JSONDecodeError as exc:
            logger.error("PUSH_SUBS_FALLBACK không phải JSON: %s", exc)
    return [], "none"


def test_requested() -> bool:
    if not (WORKER_URL and WORKER_TOKEN):
        return False
    try:
        r = httpx.get(f"{WORKER_URL}/test", headers=_worker_headers(), timeout=HTTP_TIMEOUT)
        return bool(r.status_code == 200 and r.json().get("requested"))
    except Exception:  # noqa: BLE001
        return False


def _sub_id(sub: dict) -> str:
    return hashlib.sha256(sub["endpoint"].encode()).hexdigest()[:16]


def _forget(sub: dict) -> None:
    if WORKER_URL and WORKER_TOKEN:
        try:
            httpx.delete(f"{WORKER_URL}/subs/{_sub_id(sub)}", headers=_worker_headers(), timeout=HTTP_TIMEOUT)
        except Exception:  # noqa: BLE001
            pass


def send(payload: dict, subs: list[dict]) -> dict:
    """Gửi một payload tới mọi thiết bị. Trả về {sent, gone, failed, errors}."""
    res = {"sent": 0, "gone": 0, "failed": 0, "errors": []}
    if not configured():
        res["errors"].append("Thiếu VAPID_PUBLIC_KEY/VAPID_PRIVATE_KEY")
        return res
    data = json.dumps(payload, ensure_ascii=False)
    for sub in subs:
        try:
            webpush(
                subscription_info={"endpoint": sub["endpoint"], "keys": sub["keys"]},
                data=data, ttl=TTL_ALERT,
                vapid_private_key=VAPID_PRIVATE_KEY, vapid_claims={"sub": VAPID_SUBJECT},
                headers={"Urgency": "high"},
            )
            res["sent"] += 1
        except WebPushException as exc:
            status = getattr(exc.response, "status_code", None)
            if status in (404, 410):
                res["gone"] += 1
                _forget(sub)
            else:
                res["failed"] += 1
                res["errors"].append(f"{_sub_id(sub)}: {status} {exc}"[:200])
        except Exception as exc:  # noqa: BLE001
            res["failed"] += 1
            res["errors"].append(f"{_sub_id(sub)}: {exc}"[:200])
    return res


def _dm(trade_date: str) -> str:
    return f"{trade_date[8:10]}/{trade_date[5:7]}"


def signal_payload(sig: dict, trade_date: str) -> dict:
    """Một thông báo cho MỘT tín hiệu Wyckoff (mỗi tín hiệu một thông báo, không gộp — như trend của candle-radar).
    sig: phần tử `signals` trong latest.json (symbol, name, direction, price, change_pct, vol_ratio, tr, stop, target…)."""
    arrow = "▲" if sig["direction"] == "buy" else ("▼" if sig["direction"] == "exit" else "•")
    head = "MUA" if sig["direction"] == "buy" else ("THOÁT" if sig["direction"] == "exit" else "Theo dõi")
    bits = [f"giá {sig['price']:.2f} ({sig['change_pct']:+.1f} %)", f"KL {sig['vol_ratio']:.2f}× TB20"]
    tr = sig.get("tr") or {}
    if tr.get("age"):
        bits.append(f"vùng {tr['age']} phiên · GĐ {tr.get('phase', '?')}")
    if sig.get("stop"):
        bits.append(f"stop {sig['stop']:.2f}")
    if sig.get("grade") == "★":
        bits.append("★ đã đo đạt")
    elif sig.get("grade"):
        bits.append(f"đo kém — bật tay")
    return {
        "kind": "wyckoff", "title": f"{arrow} {sig['symbol']} · {head} · {sig['name']} · phiên {_dm(trade_date)}",
        "body": " · ".join(bits), "symbol": sig["symbol"], "url": "./#today",
        "tag": f"wr-{sig['symbol']}-{sig['event']}", "hot": sig["direction"] in ("buy", "exit"),
    }


def heartbeat_payload(n_tr: int, trade_date: str) -> dict:
    return {"kind": "heartbeat", "title": "Wyckoff Radar vẫn chạy",
            "body": f"{n_tr} mã đang trong vùng đi ngang · dữ liệu đến phiên {_dm(trade_date)}",
            "url": "./#board", "tag": "wr-heartbeat", "hot": False}


def test_payload() -> dict:
    return {"kind": "test", "title": "Thông báo thử — máy này đã nhận được",
            "body": "Khi có Spring/Test/SOS/LPS (mua) hay SOW (thoát) sau phiên, thẻ như thế này sẽ hiện kể cả khi app đang đóng.",
            "url": "./#today", "tag": "wr-test"}


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    subs, src = subscriptions()
    print(f"{len(subs)} thiết bị (nguồn: {src}) · VAPID {'OK' if configured() else 'THIẾU'}")
    if "--test" in sys.argv:
        print(send(test_payload(), subs))
