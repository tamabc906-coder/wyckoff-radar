r"""G2 — đo từng sự kiện Wyckoff trên kho nến 11 năm, trước khi bật push. Khuôn demand-candle-lab/measure.py.

    venv\Scripts\python -m scripts.measure --md            # ghi reports/measure-<ngày>.md + docs/data/stats.json
    venv\Scripts\python -m scripts.measure --from 2018     # đổi năm bắt đầu (mặc định 2016)

Lệnh: mua mở cửa phiên SAU nến phát hiện (e["at"]), bán đóng cửa sau h phiên; phí 0,15 %/chiều + thuế 0,1 %.
Ba quy tắc bắt buộc: tách MUA/THOÁT (VN không bán khống), in mốc "mua đại rồi giữ", tách theo năm.
★ (MUA) = TB +10p hơn mua-đại, |t| ≥ 2, thắng mua-đại ≥ 70 % số năm có ≥ 5 lệnh và ≥ 6 năm như vậy.
★ (THOÁT) = TB +10p THẤP hơn mua-đại với cùng điều kiện t/năm (giá sau tín hiệu thoát phải kém).

Đối chứng (những gì đã đo ở app khác, để biết Wyckoff có hơn không):
  - ctrl_sc_lab   : nến đỏ KL ≥ 1,5× tại vùng cầu (demand-candle-lab: +2,36 %/10p, 8/11 năm)
  - ctrl_ceiling  : Trần + KL ≥ 2× + phá đỉnh 20p, đóng cửa ≥ 80 % (candle-radar: +2,76 %/10p, 5/5 năm)
  - ctrl_spring_hv: "Spring" cũ của candle-radar — phá đáy 20p, đóng lại, nến xanh, KL ≥ 1,5× (+3,75 % lệch năm)
  - sos vs lps    : mua ngay tại SOS hay chờ LPS (hai dòng sự kiện)
  - buy_entry     : gộp mọi điểm vào Wyckoff (spring3 + test + lps + bu) — chuỗi đầy đủ
  - <sự kiện> · RS>0: chỉ lấy tín hiệu khi mã mạnh hơn VN-Index 20 phiên
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from datetime import datetime

from common import store
from common.config import HISTORY, INDEX_SYMBOL, REPORTS, SITE_DATA, TZ
from job import wyckoff as W

for s in (sys.stdout, sys.stderr):
    if hasattr(s, "reconfigure"):
        s.reconfigure(encoding="utf-8", errors="replace")

HS = (5, 10, 20)
FEE, TAX = 0.0015, 0.001
STATS = SITE_DATA / "stats.json"

CTRL_NAMES = {
    "ctrl_sc_lab": "Đối chứng: nến đỏ KL ≥ 1,5× tại vùng cầu (demand-candle-lab)",
    "ctrl_ceiling": "Đối chứng: Trần + KL ≥ 2× + phá đỉnh 20p (candle-radar)",
    "ctrl_spring_hv": "Đối chứng: Spring KL ≥ 1,5× đáy 20p, không vùng (candle-radar cũ)",
    "buy_entry": "Gộp điểm vào Wyckoff: spring3 + test + lps + bu",
}
BUY_ENTRY = ("spring3", "test", "lps", "bu")


def net_ret(bars, i, h):
    """Mua mở cửa i+1, bán đóng cửa i+1+h, sau phí/thuế. None nếu chưa đủ phiên."""
    if i + 1 + h >= len(bars) or bars[i + 1]["o"] <= 0:
        return None
    return bars[i + 1 + h]["c"] * (1 - FEE - TAX) / (bars[i + 1]["o"] * (1 + FEE)) - 1


def stats(rets):
    n = len(rets)
    if n == 0:
        return {"n": 0, "mean": 0.0, "win": 0.0, "t": 0.0}
    m = sum(rets) / n
    sd = math.sqrt(sum((r - m) ** 2 for r in rets) / (n - 1)) if n > 1 else 0.0
    return {"n": n, "mean": m, "win": sum(r > 0 for r in rets) / n, "t": m / (sd / math.sqrt(n)) if sd > 0 else 0.0}


# ---------- đối chứng ----------

def in_demand(bars, i, zone_win=60, tol=0.03, drop_win=10, drop_pct=0.05):
    if i < zone_win + drop_win:
        return False
    lo60 = min(x["l"] for x in bars[i - zone_win:i])
    ref = bars[i - drop_win]["c"]
    return bars[i]["l"] <= lo60 * (1 + tol) and ref > 0 and bars[i]["c"] / ref - 1 <= -drop_pct


def ctrl_sc_lab(bars, i, av):
    return av > 0 and W.is_bear(bars[i]) and bars[i]["v"] >= 1.5 * av and in_demand(bars, i)


def ctrl_ceiling(bars, i, av):
    if i < 21 or av <= 0:
        return False
    _, ceil = W.limit_flags(bars, i, 0.065)
    return (ceil and bars[i]["v"] >= 2 * av and bars[i]["c"] > max(x["h"] for x in bars[i - 20:i])
            and W.close_pos(bars[i]) >= 0.8)


def ctrl_spring_hv(bars, i, av):
    if i < 20 or av <= 0:
        return False
    lo = min(x["l"] for x in bars[i - 20:i])
    b = bars[i]
    return b["l"] < lo < b["c"] and W.is_bull(b) and b["v"] >= 1.5 * av


# ---------- đo ----------

def collect(st, from_year: int):
    """rows[key][h] → [(năm, ret)]; base[h] → [(năm, ret)]; months = số tháng-lịch có dữ liệu."""
    syms = sorted(s for s in st["bars"] if s != INDEX_SYMBOL)
    idx_bars = store.bars(st, INDEX_SYMBOL)
    idx = {b["d"]: b["c"] for b in idx_bars}
    rows: dict[str, dict[int, list]] = defaultdict(lambda: defaultdict(list))
    base: dict[int, list] = defaultdict(list)
    months = set()
    n_sym = 0
    for sym in syms:
        bars = store.bars(st, sym)
        if len(bars) < 300:
            continue
        n_sym += 1
        R = W.analyze(bars)
        for i in range(W.MIN_BARS, len(bars)):
            y = bars[i]["d"].year
            if y < from_year:
                continue
            months.add((y, bars[i]["d"].month))
            rets = {h: net_ret(bars, i, h) for h in HS}
            for h in HS:
                if rets[h] is not None:
                    base[h].append((y, rets[h]))
            av = W.avg_vol(bars, i, W.CFG["vol_n"])
            for cid, fn in (("ctrl_sc_lab", ctrl_sc_lab), ("ctrl_ceiling", ctrl_ceiling), ("ctrl_spring_hv", ctrl_spring_hv)):
                if fn(bars, i, av):
                    for h in HS:
                        if rets[h] is not None:
                            rows[cid][h].append((y, rets[h]))
        for e in R.events:
            eid = e["id"]
            if W.EVENTS[eid]["direction"] == "label":
                continue
            at = e["at"]
            y = bars[at]["d"].year
            if y < from_year:
                continue
            rets = {h: net_ret(bars, at, h) for h in HS}
            # RS20 tại nến phát hiện
            rs = None
            if at >= 20:
                d1, d0 = bars[at]["d"], bars[at - 20]["d"]
                if d1 in idx and d0 in idx and idx[d0] and bars[at - 20]["c"]:
                    rs = (bars[at]["c"] / bars[at - 20]["c"]) / (idx[d1] / idx[d0]) - 1
            keys = [eid]
            if eid in BUY_ENTRY:
                keys.append("buy_entry")
            if rs is not None and rs > 0:
                keys.append(f"{eid} · RS>0")
            for h in HS:
                if rets[h] is None:
                    continue
                for k in keys:
                    rows[k][h].append((y, rets[h]))
    return rows, base, len(months), n_sym


def years_beat(rows_h, base_year_h, years, side):
    won = tot = 0
    for Y in years:
        rr = [r for y, r in rows_h if y == Y]
        if len(rr) < 5:
            continue
        tot += 1
        m = sum(rr) / len(rr)
        b = base_year_h[Y]["mean"]
        won += (m > b) if side == "buy" else (m < b)
    return won, tot


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="from_year", type=int, default=2016)
    ap.add_argument("--md", action="store_true", help="ghi reports/measure-<ngày>.md và docs/data/stats.json")
    a = ap.parse_args()

    st = store.load(HISTORY)
    rows, base, n_months, n_sym = collect(st, a.from_year)
    years = sorted({y for y, _ in base[10]})
    base_year = {h: {Y: stats([r for y, r in base[h] if y == Y]) for Y in years} for h in HS}
    base_all = {h: stats([r for _, r in base[h]]) for h in HS}
    first, last = store.span(st, "HPG")[0], store.span(st, "HPG")[1]

    out: list[str] = []
    P = out.append
    P(f"# Đo sự kiện Wyckoff — {n_sym} mã · {a.from_year}→{last[:4]} (kho {first} → {last}) · chạy {datetime.now(TZ):%Y-%m-%d %H:%M}\n")
    P("Lệnh: mua mở cửa phiên SAU nến phát hiện, giữ h phiên, bán đóng cửa; phí 0,15 %/chiều + thuế 0,1 %. "
      "'năm thắng' = số năm có ≥ 5 lệnh mà TB lệnh hơn mua-đại cùng năm / số năm đó (THOÁT: thấp hơn). "
      "★ = hơn mua-đại, |t| ≥ 2, thắng ≥ 70 % số năm với ≥ 6 năm đủ lệnh. "
      "Ngưỡng sự kiện: `job/wyckoff.py` CFG (nguồn Villahermosa/Trading-POC/StockCharts — điểm khởi đầu, không phải chân lý).\n")
    P("## Mốc mua-đại (mọi phiên-mã)\n")
    P("| h | n | TB | thắng |\n|---|---:|---:|---:|")
    for h in HS:
        b = base_all[h]
        P(f"| +{h}p | {b['n']:,} | {b['mean'] * 100:+.2f} % | {b['win'] * 100:.0f} % |")
    P("")
    P("| Năm | " + " | ".join(f"+{h}p" for h in HS) + " |\n|---|" + "---:|" * len(HS))
    for Y in years:
        P(f"| {Y} | " + " | ".join(f"{base_year[h][Y]['mean'] * 100:+.2f} %" for h in HS) + " |")
    P("")

    stats_json = {"generated_at": datetime.now(TZ).isoformat(timespec="seconds"), "from_year": a.from_year,
                  "n_symbols": n_sym, "base": {str(h): base_all[h]["mean"] for h in HS}, "events": {}}
    starred: list[str] = []

    def table(title, keys, side):
        P(f"## {title} — +10 phiên, mua-đại {base_all[10]['mean'] * 100:+.2f} %\n")
        P("| Sự kiện | n | /tháng | +5p | +10p | đúng | t | +20p | năm thắng | theo năm (+10p) |")
        P("|---|---:|---:|---:|---:|---:|---:|---:|---:|---|")
        for k in keys:
            name = W.EVENTS[k]["name"] if k in W.EVENTS else CTRL_NAMES.get(k, k)
            r = rows.get(k)
            if not r or not r[10]:
                P(f"| {name} (`{k}`) | 0 | — | — | — | — | — | — | — | |")
                continue
            s5, s10, s20 = (stats([x for _, x in r[h]]) for h in HS)
            won, tot = years_beat(r[10], base_year[10], years, side)
            good = (s10["mean"] > base_all[10]["mean"]) if side == "buy" else (s10["mean"] < base_all[10]["mean"])
            star = tot >= 6 and won / tot >= 0.7 and good and abs(s10["t"]) >= 2
            by_year = {Y: stats([x for y, x in r[10] if y == Y]) for Y in years}
            yr = " ".join(f"{str(Y)[2:]}:{by_year[Y]['mean'] * 100:+.1f}({by_year[Y]['n']})" for Y in years if by_year[Y]["n"])
            P(f"| {'★ ' if star else ''}{name} (`{k}`) | {s10['n']:,} | {s10['n'] / n_months:.1f} | {s5['mean'] * 100:+.2f} % | "
              f"**{s10['mean'] * 100:+.2f} %** | {s10['win'] * 100:.0f} % | {s10['t']:.1f} | {s20['mean'] * 100:+.2f} % | {won}/{tot} | {yr} |")
            if k in W.EVENTS:
                stats_json["events"][k] = {
                    "direction": W.EVENTS[k]["direction"], "n": s10["n"], "per_month": round(s10["n"] / n_months, 2),
                    "mean": {str(h): round(s["mean"], 5) for h, s in zip(HS, (s5, s10, s20))},
                    "win10": round(s10["win"], 3), "t10": round(s10["t"], 2), "years_won": won, "years_total": tot,
                    "star": bool(star), "by_year": {str(Y): [by_year[Y]["n"], round(by_year[Y]["mean"], 5)] for Y in years if by_year[Y]["n"]},
                }
                if star:
                    starred.append(k)
        P("")

    buy_ids = [k for k in W.EVENTS if W.EVENTS[k]["direction"] == "buy"]
    watch_ids = [k for k in W.EVENTS if W.EVENTS[k]["direction"] == "watch"]
    exit_ids = [k for k in W.EVENTS if W.EVENTS[k]["direction"] == "exit"]
    table("Tín hiệu MUA", buy_ids, "buy")
    table("Đối chứng và gộp (MUA)", ["buy_entry", "ctrl_sc_lab", "ctrl_ceiling", "ctrl_spring_hv"], "buy")
    table("Lọc sức mạnh tương đối: chỉ lấy khi RS20 > 0 (MUA)", [f"{k} · RS>0" for k in buy_ids], "buy")
    table("Sự kiện THEO DÕI (không push; đo để biết giá đi đâu sau đó)", watch_ids, "buy")
    table("Tín hiệu THOÁT — đạt khi giá SAU tín hiệu thấp hơn mua-đại", exit_ids, "exit")

    P("## Đọc kết quả\n")
    P("- So `sc` với `ctrl_sc_lab`, `sos` với `ctrl_ceiling`, `spring3`/`test` với `ctrl_spring_hv`: Wyckoff chỉ đáng thêm "
      "nếu hơn đối chứng đã có, hoặc cho tín hiệu ở thời điểm khác (sớm hơn/ít hơn).")
    P("- `lps` so `sos`: chờ nhịp lùi có lợi hơn mua ngay không.")
    P("- Sự kiện n nhỏ (< 30) hoặc ít năm đủ lệnh: chưa kết luận được, để ở chế độ nhãn.")
    P(f"- ★ đạt: {', '.join(starred) if starred else 'không có'} → `docs/data/settings.json` `events_disabled` = mọi sự kiện MUA/THOÁT còn lại.")
    text = "\n".join(out)
    print(text)

    if a.md:
        REPORTS.mkdir(parents=True, exist_ok=True)
        path = REPORTS / f"measure-{datetime.now(TZ):%Y-%m-%d}.md"
        path.write_text(text, encoding="utf-8")
        stats_json["starred"] = starred
        STATS.write_text(json.dumps(stats_json, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\nĐã ghi {path} và {STATS}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
