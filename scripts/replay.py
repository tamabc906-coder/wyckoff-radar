r"""Tái lập tín hiệu N phiên gần nhất từ kho nến → docs/data/daily/<ngày>.json, để tab Lịch sử có nội dung
ngay khi chạy thật (và để đối chiếu: job thật phải cho đúng những tín hiệu này vào ngày đó).

    venv\Scripts\python -m scripts.replay            # 30 phiên, không ghi đè file đã có
    venv\Scripts\python -m scripts.replay --days 60 --overwrite
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime

from common import store
from common.config import HISTORY, INDEX_SYMBOL, TZ
from job import settings, watchlist, wyckoff as W
from job.run_daily import DAILY, STATS, _dump, _load, build_signal

for s in (sys.stdout, sys.stderr):
    if hasattr(s, "reconfigure"):
        s.reconfigure(encoding="utf-8", errors="replace")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--overwrite", action="store_true")
    a = ap.parse_args()
    cfg = settings.load()
    stats = _load(STATS, {})
    items, src = watchlist.load()
    if not items:
        print("Không có danh mục", file=sys.stderr)
        return 2
    hist = store.load(HISTORY)
    dates = sorted({r[0] for sym in hist["bars"] if sym != INDEX_SYMBOL for r in hist["bars"][sym][-a.days:]})[-a.days:]
    per_day: dict[str, list] = {d: [] for d in dates}
    for it in items:
        sym = it["symbol"]
        bars = store.bars(hist, sym)
        if len(bars) < W.MIN_BARS + 5:
            continue
        R = W.analyze(bars)
        by_i: dict[int, list] = {}
        for e in R.events:
            if W.EVENTS[e["id"]]["direction"] != "label" and bars[e["at"]]["d"].isoformat() in per_day:
                by_i.setdefault(e["at"], []).append(e)
        for i, evs in by_i.items():
            for e in sorted(evs, key=lambda x: W.EVENTS[x["id"]]["priority"]):
                s = build_signal(sym, it, bars, R, e, stats, cfg)
                per_day[bars[i]["d"].isoformat()].append({"symbol": s["symbol"], "event": s["event"], "name": s["name"],
                                                         "direction": s["direction"], "price": s["price"], "push": s["push"], "grade": s["grade"]})
    n = 0
    for d, sigs in per_day.items():
        f = DAILY / f"{d}.json"
        if f.exists() and not a.overwrite:
            continue
        order = {"buy": 0, "exit": 1, "watch": 2}
        sigs.sort(key=lambda s: (order.get(s["direction"], 3), s["symbol"]))
        _dump(f, {"trade_date": d, "generated_at": datetime.now(TZ).isoformat(timespec="seconds"), "late": False,
                  "replay": True, "signals": sigs, "stale": []})
        n += 1
        print(f"{d}: {len(sigs)} tín hiệu — " + ", ".join(f"{s['symbol']}:{s['event']}" for s in sigs))
    print(f"Ghi {n} file vào {DAILY}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
