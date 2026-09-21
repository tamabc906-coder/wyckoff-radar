r"""Tách nhóm sự kiện theo trần/sàn, KL, gốc vùng, năm — để hiểu số đo của scripts/measure.py, KHÔNG đổi ngưỡng.
    venv\Scripts\python -m scripts.split
"""
from __future__ import annotations

import sys
from collections import defaultdict

from common import store
from common.config import HISTORY, INDEX_SYMBOL
from job import wyckoff as W
from scripts.measure import net_ret, stats

for s in (sys.stdout, sys.stderr):
    if hasattr(s, "reconfigure"):
        s.reconfigure(encoding="utf-8", errors="replace")

BASE10 = 0.0057


def main() -> None:
    st = store.load(HISTORY)
    g: dict[tuple, list] = defaultdict(list)
    for sym in sorted(st["bars"]):
        if sym == INDEX_SYMBOL:
            continue
        bars = store.bars(st, sym)
        R = W.analyze(bars)
        for e in R.events:
            at, y = e["at"], bars[e["at"]]["d"].year
            if y < 2016:
                continue
            r = net_ret(bars, at, 10)
            if r is None:
                continue
            fl, ce = W.limit_flags(bars, at, 0.065)
            eid = e["id"]
            if eid == "sos":
                g[("sos", "trần" if ce else "không trần")].append((y, r))
                g[("sos", "gốc " + e["tr"]["origin"])].append((y, r))
                g[("sos", "tuổi<40" if e["age"] < 40 else "tuổi>=40")].append((y, r))
                g[("sos", "KL>=2.5" if e["vol_ratio"] >= 2.5 else "KL<2.5")].append((y, r))
                g[("sos", "có spring trước" if e["tr"]["spring"] is not None else "không spring")].append((y, r))
            elif eid == "sc":
                g[("sc", "sàn" if fl else "không sàn")].append((y, r))
                g[("sc", "KL>=3" if e["vol_ratio"] >= 3 else "KL 2-3")].append((y, r))
                g[("sc", "2022" if y == 2022 else "không 2022")].append((y, r))
            elif eid == "sow":
                g[("sow", "2022" if y == 2022 else "không 2022")].append((y, r))
                g[("sow", e.get("where", ""))].append((y, r))
            elif eid in ("spring2", "spring1", "spring3"):
                vr = e["vol_ratio"]
                g[("spring*", "KL<=0.7" if vr <= 0.7 else ("KL 0.7-1.5" if vr < 1.5 else "KL>=1.5"))].append((y, r))
                g[("spring*", "phá<1%" if e["break_pct"] < 0.01 else ("phá 1-3%" if e["break_pct"] < 0.03 else "phá 3-6%"))].append((y, r))
                g[("spring*", "gốc " + e["tr"]["origin"])].append((y, r))
            elif eid == "test":
                g[("test", "sau " + e["spring"])].append((y, r))
    for k in sorted(g):
        s = stats([r for _, r in g[k]])
        yrs: dict[int, list] = defaultdict(list)
        for y, r in g[k]:
            yrs[y].append(r)
        tot = sum(1 for y in yrs if len(yrs[y]) >= 5)
        won = sum(1 for y in yrs if len(yrs[y]) >= 5 and sum(yrs[y]) / len(yrs[y]) > BASE10)
        print(f"{k[0]:<9}{k[1]:<18} n={s['n']:>4}  +10p {s['mean'] * 100:+6.2f} %  đúng {s['win'] * 100:3.0f} %  "
              f"t {s['t']:5.1f}  năm hơn mua-đại {won}/{tot}")


if __name__ == "__main__":
    main()
