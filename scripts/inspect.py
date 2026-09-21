r"""Soi lõi Wyckoff bằng mắt trên kho nến thật (G1). Không ghi file.

    venv\Scripts\python -m scripts.inspect HPG --from 2022-10-01 --to 2023-03-31   # bảng ngày–sự kiện + vùng
    venv\Scripts\python -m scripts.inspect --count                                  # tần suất sự kiện 39 mã, theo năm
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from datetime import date

from common import store
from common.config import HISTORY, INDEX_SYMBOL
from job import wyckoff as W

for s in (sys.stdout, sys.stderr):
    if hasattr(s, "reconfigure"):
        s.reconfigure(encoding="utf-8", errors="replace")


def show(sym: str, d0: date, d1: date) -> None:
    st = store.load(HISTORY)
    bars = store.bars(st, sym)
    if not bars:
        print(f"{sym}: không có trong kho")
        return
    R = W.analyze(bars)
    print(f"\n== {sym} {d0} → {d1} ==")
    print("Vùng đi ngang chạm khoảng ngày này:")
    for t in R.trs:
        a, b = bars[t.start]["d"], (bars[t.end]["d"] if t.end is not None else bars[-1]["d"])
        if b < d0 or a > d1:
            continue
        print(f"  {t.kind:<4} {t.origin:<5} {a} → {b}  lo {t.lo:.2f}  hi {t.hi:.2f}  GĐ {t.phase}  kết thúc: {t.end_reason or 'đang mở'}")
    print(f"{'ngày':<11}{'đóng':>8}{'KL/TB':>7}  sự kiện")
    for e in R.events:
        d = e["d"]
        if d < d0 or d > d1 or e["id"] in ("er_absorb", "no_demand"):
            continue
        b = bars[e["i"]]
        extra = []
        if "break_pct" in e:
            extra.append(f"phá {e['break_pct'] * 100:.1f} %")
        if "stop" in e and e["stop"]:
            extra.append(f"stop {e['stop']:.2f}")
        if "target" in e and e["target"]:
            extra.append(f"mục tiêu {e['target']['min']:.2f}")
        if "age" in e:
            extra.append(f"tuổi {e['age']}")
        if e["at"] != e["i"]:
            extra.append(f"(chốt {bars[e['at']]['d']})")
        print(f"{d.isoformat():<11}{b['c']:>8.2f}{e.get('vol_ratio', 0):>7.2f}  {e['id']:<8} {W.EVENTS[e['id']]['name']}  {' · '.join(extra)}")


def count() -> None:
    st = store.load(HISTORY)
    per = Counter()
    per_year: dict[str, Counter] = defaultdict(Counter)
    n_sym = 0
    for sym in sorted(st["bars"]):
        if sym == INDEX_SYMBOL:
            continue
        bars = store.bars(st, sym)
        if len(bars) < 300:
            continue
        n_sym += 1
        R = W.analyze(bars)
        for e in R.events:
            per[e["id"]] += 1
            per_year[e["id"]][e["d"].year] += 1
    years = sorted({y for c in per_year.values() for y in c})
    print(f"{n_sym} mã · sự kiện theo năm")
    print(f"{'sự kiện':<10}{'tổng':>6}" + "".join(f"{y:>6}" for y in years))
    for eid in W.EVENTS:
        if per[eid]:
            print(f"{eid:<10}{per[eid]:>6}" + "".join(f"{per_year[eid][y]:>6}" for y in years))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("symbol", nargs="?")
    ap.add_argument("--from", dest="d0", default="2022-09-01")
    ap.add_argument("--to", dest="d1", default="2023-03-31")
    ap.add_argument("--count", action="store_true")
    a = ap.parse_args()
    if a.count:
        count()
    if a.symbol:
        show(a.symbol.upper(), date.fromisoformat(a.d0), date.fromisoformat(a.d1))


if __name__ == "__main__":
    main()
