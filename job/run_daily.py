"""Job sau phiên — GitHub Actions 15:45 T2–T6 (hoặc local: python -m job.run_daily [--dry-run|--no-push|--force]).

Luồng: danh mục KingStock → 30 ngày nến DNSE gần nhất (+ VNINDEX) nối vào kho data/history.json → quét Wyckoff
trọn lịch sử từng mã (job/wyckoff.py, ~4 s/39 mã) → tín hiệu có `at` = nến cuối → push từng tín hiệu được bật
(settings.events_disabled, buy_only) → ghi docs/data/latest.json (thẻ + bảng + lịch sử có chấm điểm), bars.json
(160 nến + nhãn + biên vùng cho tab Biểu đồ), daily/<ngày>.json, state.json.

Khung (fetch_bars, idempotent, unsettled, chào máy mới) chép từ price-path/job/run_daily.py.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date, datetime, timedelta

from common import dnse, store as store_mod
from common.config import HISTORY, INDEX_SYMBOL, SITE_DATA, TZ

from . import push, settings, watchlist, wyckoff as W

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("job")

LATEST = SITE_DATA / "latest.json"
BARS = SITE_DATA / "bars.json"
STATE = SITE_DATA / "state.json"
STATS = SITE_DATA / "stats.json"
DAILY = SITE_DATA / "daily"

FETCH_DAYS = 30            # lịch sử nằm trong kho; mỗi ngày chỉ lấy đoạn gần nhất để nối
BARS_IN_CHART = 120        # nến mỗi mã cho tab Biểu đồ (~220 KB bars.json, bot commit mỗi ngày)
CANDLES_IN_CARD = 60       # nến trong thẻ tín hiệu
LIQUID_MIN_BARS = 30
UNSETTLED_RATIO = 0.2
FEE, TAX = 0.0015, 0.001   # chấm điểm lịch sử như scripts/measure.py


def _load(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def _dump(path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1, default=str), encoding="utf-8")


def fetch_bars(tickers: list[str], client=None, days: int = FETCH_DAYS) -> tuple[dict[str, list[dict]], list[str]]:
    """Nến ngày gần nhất cho từng mã + danh sách mã thanh khoản mà nến HÔM NAY chưa chốt. Chép nguyên price-path."""
    bars: dict[str, list[dict]] = {}
    voters: list[str] = []
    lacking: list[str] = []
    today = dnse.today_vn()
    with (client or dnse.DnseClient(days=days)) as c:
        for i, t in enumerate(sorted(tickers), 1):
            b = c.daily(t)
            if not b:
                continue
            if b[-1]["d"] == today:
                minutes = c.today_minutes(t)
                if len(minutes) >= LIQUID_MIN_BARS:
                    voters.append(t)
                    if not dnse.session_settled(minutes):
                        lacking.append(t)
                b[-1] = dnse.merge_today(b[-1], minutes)
            bars[t] = b
            if i % 10 == 0:
                log.info("giá: %d/%d mã", i, len(tickers))
    unsettled = lacking if voters and len(lacking) / len(voters) >= UNSETTLED_RATIO else []
    if lacking and not unsettled:
        log.info("Mã thiếu nến ATC nhưng nguồn nhìn chung đã chốt (%d/%d): %s",
                 len(lacking), len(voters), ", ".join(lacking))
    return bars, unsettled


# ---------- dựng tín hiệu / bảng ----------

def _compact(bars: list[dict]) -> list[list]:
    return [[b["d"].isoformat(), b["o"], b["h"], b["l"], b["c"], int(b["v"])] for b in bars]


def _grade(stats: dict, eid: str) -> tuple[str | None, dict | None]:
    """(hạng, số đo) từ docs/data/stats.json: "★" đạt, "đo kém" không đạt, None chưa đo (sự kiện theo dõi)."""
    ev = (stats.get("events") or {}).get(eid)
    if not ev:
        return None, None
    if W.EVENTS[eid]["direction"] == "watch":            # theo dõi: có số đo để tham khảo nhưng không xếp hạng
        return None, {"mean10": ev["mean"]["10"], "n": ev["n"], "base10": (stats.get("base") or {}).get("10")}
    m = {"mean10": ev["mean"]["10"], "mean5": ev["mean"]["5"], "mean20": ev["mean"]["20"], "n": ev["n"],
         "win10": ev["win10"], "years_won": ev["years_won"], "years_total": ev["years_total"],
         "base10": (stats.get("base") or {}).get("10")}
    return ("★" if ev.get("star") else "đo kém"), m


def _t2(d: date) -> date:
    """Ngày bán sớm nhất: mua mở phiên sau d, cổ phiếu về sau 2 phiên nữa (bỏ T7/CN, chưa tính lễ)."""
    out, k = d, 0
    while k < 3:
        out += timedelta(days=1)
        if out.weekday() < 5:
            k += 1
    return out


def build_signal(sym: str, meta: dict, bars: list[dict], R: W.Result, e: dict, stats: dict, cfg: dict) -> dict:
    i = e["at"]
    b, prev = bars[i], bars[i - 1]
    atr = R.atr[i] or 0.0
    av = R.av(i)
    ev = W.EVENTS[e["id"]]
    grade, m = _grade(stats, e["id"])
    tr = e.get("tr") or (R.tr.to_dict() if R.tr else None)
    stop = e.get("stop")
    target = e.get("target")
    rr = None
    if stop and target and b["c"] > stop:
        rr = round((target["min"] - b["c"]) / (b["c"] - stop), 2)
    n0 = max(0, i + 1 - CANDLES_IN_CARD)
    marks = [[x["i"] - n0, x["id"]] for x in R.events if n0 <= x["i"] <= i and W.EVENTS[x["id"]]["direction"] != "label"]
    push_ok = ev["direction"] in ("buy", "exit") and e["id"] not in cfg["events_disabled"] and not (cfg.get("buy_only") and ev["direction"] == "exit")
    return {
        "symbol": sym, "company_name": meta.get("company_name") or "", "exchange": meta.get("exchange") or "",
        "price": b["c"], "change_pct": round((b["c"] / prev["c"] - 1) * 100, 2) if prev["c"] else 0.0, "volume": int(b["v"]),
        "vol_ratio": round(b["v"] / av, 2) if av else None, "spread_atr": round(W.spread(b) / atr, 2) if atr else None,
        "close_pos": round(W.close_pos(b) * 100), "body_atr": round(W.body(b) / atr, 2) if atr else None,
        "event": e["id"], "name": ev["name"], "direction": ev["direction"], "priority": ev["priority"],
        "hint": ev["hint"], "advice": ev["advice"], "caution": ev["caution"],
        "grade": grade, "stats": m, "push": push_ok,
        "tr": tr, "phase": R.phase(), "age": e.get("age"),
        "break_pct": round(e["break_pct"] * 100, 2) if "break_pct" in e else None,
        "stop": round(stop, 2) if stop else None, "stop_pct": round((stop / b["c"] - 1) * 100, 1) if stop else None,
        "target": target, "rr": rr, "beyond_target": bool(target and b["c"] >= target["min"]),
        "t2_date": _t2(b["d"]).isoformat(),
        "candles": _compact(bars[n0:i + 1]), "marks": marks,
    }


def build_board(sym: str, meta: dict, bars: list[dict], R: W.Result, idx_bars: list[dict]) -> dict:
    i = len(bars) - 1
    st = W.board_state(R, i)
    tr = st["tr"]
    b, prev = bars[i], bars[i - 1]
    return {
        "symbol": sym, "company_name": meta.get("company_name") or "", "price": b["c"],
        "change_pct": round((b["c"] / prev["c"] - 1) * 100, 2) if prev["c"] else 0.0,
        "phase": st["phase"], "tr_lo": tr["lo"] if tr else None, "tr_hi": tr["hi"] if tr else None,
        "tr_age": st["tr_age"], "tr_origin": tr["origin"] if tr else None, "tr_kind": tr["kind"] if tr else None,
        "last_event": st["last_event"], "last_event_date": st["last_event_date"],
        "rs_20": (lambda v: round(v * 100, 1) if v is not None else None)(W.relative_strength(bars, idx_bars, 20)),
    }


def chart_payload(sym: str, bars: list[dict], R: W.Result) -> tuple[list, list, list]:
    n0 = max(0, len(bars) - BARS_IN_CHART)
    marks = [[x["d"].isoformat(), x["id"]] for x in R.events if x["i"] >= n0 and W.EVENTS[x["id"]]["direction"] != "label"]
    trs = []
    for t in R.trs:
        end = t.end if t.end is not None else len(bars) - 1
        if end < n0:
            continue
        trs.append({"lo": t.lo, "hi": t.hi, "from": bars[max(t.start, n0)]["d"].isoformat(), "to": bars[end]["d"].isoformat(),
                    "kind": t.kind, "origin": t.origin, "open": t.end is None})
    return _compact(bars[n0:]), marks, trs


def _net(bars_by_date: dict[str, list], sym: str, d: str, h: int):
    """Lợi suất mua mở phiên sau ngày d, bán đóng cửa sau h phiên (có phí). None nếu chưa đủ phiên."""
    rows = bars_by_date.get(sym) or []
    pos = next((k for k, r in enumerate(rows) if r[0] == d), None)
    if pos is None or pos + 1 + h >= len(rows) or rows[pos + 1][1] <= 0:
        return None
    return round((rows[pos + 1 + h][4] * (1 - FEE - TAX) / (rows[pos + 1][1] * (1 + FEE)) - 1) * 100, 2)


def history(days: int, hist: dict) -> list[dict]:
    """Tab Lịch sử: mỗi phiên các tín hiệu đã phát + lợi suất +5/+10p khi đủ ngày (chấm cả THOÁT: giá giảm = đúng)."""
    out = []
    if not DAILY.exists():
        return out
    for f in sorted(DAILY.glob("*.json"), reverse=True)[:days]:
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        td = d.get("trade_date") or f.stem
        sigs = []
        for s in d.get("signals") or []:
            sigs.append({**s, "r5": _net(hist["bars"], s["symbol"], td, 5), "r10": _net(hist["bars"], s["symbol"], td, 10)})
        out.append({"date": td, "late": bool(d.get("late")), "signals": sigs})
    return out


def _send(signals: list[dict], trade_iso: str, subs: list[dict]) -> dict:
    res = {"sent": 0, "gone": 0, "failed": 0, "errors": [], "n_signals": 0}
    for s in signals:
        if not s["push"]:
            continue
        res["n_signals"] += 1
        r = push.send(push.signal_payload(s, trade_iso), subs)
        for k in ("sent", "gone", "failed"):
            res[k] += r[k]
        res["errors"] += r["errors"]
    return res


def scan(hist: dict, items: list[dict], trade_date: date, cfg: dict, stats: dict) -> tuple[list[dict], list[dict], list[str], dict]:
    """Quét mọi mã: (tín hiệu hôm nay, bảng 39 mã, mã nến cũ, dữ liệu biểu đồ)."""
    idx_bars = store_mod.bars(hist, INDEX_SYMBOL)
    signals, board, stale = [], [], []
    chart = {"bars": {}, "marks": {}, "tr": {}}
    for it in items:
        sym = it["symbol"]
        bars = store_mod.bars(hist, sym)
        if len(bars) < W.MIN_BARS + 5:
            continue
        if bars[-1]["d"] != trade_date:
            stale.append(sym)
            continue
        R = W.analyze(bars)
        last = len(bars) - 1
        for e in W.signals_at(R, last):
            signals.append(build_signal(sym, it, bars, R, e, stats, cfg))
        board.append(build_board(sym, it, bars, R, idx_bars))
        chart["bars"][sym], chart["marks"][sym], chart["tr"][sym] = chart_payload(sym, bars, R)
    order = {"buy": 0, "exit": 1, "watch": 2}
    signals.sort(key=lambda s: (order.get(s["direction"], 3), s["priority"], s["symbol"]))
    board.sort(key=lambda r: r["symbol"])
    return signals, board, stale, chart


def run(force: bool = False, dry_run: bool = False, no_push: bool = False) -> int:
    now = datetime.now(TZ)
    st = _load(STATE, {})
    if not dry_run and not no_push:
        _welcome_new_devices(st, now)
    cfg = settings.load()
    stats = _load(STATS, {})

    items, wl_source = watchlist.load()
    if not items:
        log.error("Không có danh mục: KingStock không trả lời và chưa có docs/data/watchlist.json")
        st.update({"last_run": now.isoformat(timespec="seconds"), "watchlist_error": "không có danh mục"})
        _dump(STATE, st)
        return 2
    tickers = sorted(it["symbol"] for it in items)
    log.info("Danh mục %d mã (nguồn %s)", len(tickers), wl_source)

    hist = store_mod.load(HISTORY)
    with dnse.DnseClient(days=FETCH_DAYS) as client:
        fetched = store_mod.ensure(hist, items, client)
        if fetched:
            log.info("Tải trọn lịch sử cho mã mới: %s", ", ".join(fetched))
        idx_bars = client.index(INDEX_SYMBOL)       # trước fetch_bars: hàm đó đóng client khi xong (with … as c)
        bars, unsettled = fetch_bars(tickers, client)
    if not bars:
        log.error("DNSE không trả về gì: %s", dnse.last_error)
        st.update({"dnse_error": dnse.last_error, "last_run": now.isoformat(timespec="seconds")})
        _dump(STATE, st)
        return 3
    trade_date = max(b[-1]["d"] for b in bars.values())
    trade_iso = trade_date.isoformat()
    daily_file = DAILY / f"{trade_iso}.json"
    if daily_file.exists() and not force:
        log.info("Đã có %s — không chạy lại (dùng --force nếu muốn)", daily_file.name)
        return 0
    if unsettled and not force:
        msg = (f"Nguồn chưa chốt phiên {trade_iso}: {len(unsettled)}/{len(bars)} mã chưa có nến ATC "
               f"({', '.join(unsettled[:8])}{'…' if len(unsettled) > 8 else ''}) — chờ cron sau")
        log.warning(msg)
        st.update({"last_run": now.isoformat(timespec="seconds"),
                   "unsettled": {"trade_date": trade_iso, "tickers": unsettled, "at": now.isoformat(timespec="seconds")}})
        _dump(STATE, st)
        return 0
    late = bool(st.pop("unsettled", None))
    if (now.date() - trade_date).days > 4:
        log.warning("Phiên gần nhất %s cách hôm nay quá 4 ngày — DNSE có thể chưa cập nhật", trade_iso)

    changed = sum(store_mod.merge(hist, sym, b) for sym, b in bars.items()) + store_mod.merge(hist, INDEX_SYMBOL, idx_bars)
    log.info("Kho: nối %d nến mới/đổi", changed)

    signals, board, stale, chart = scan(hist, items, trade_date, cfg, stats)
    n_push = sum(1 for s in signals if s["push"])
    n_tr = sum(1 for r in board if r["phase"] not in ("-", "E", "E↓"))
    log.info("Phiên %s: %d tín hiệu (%d push), %d mã trong vùng, %d mã nến cũ", trade_iso, len(signals), n_push, n_tr, len(stale))
    for s in signals:
        log.info("  %s %-5s %-8s %s · giá %.2f · KL %.2f× · GĐ %s%s", "▲" if s["direction"] == "buy" else ("▼" if s["direction"] == "exit" else "•"),
                 s["symbol"], s["event"], s["name"], s["price"], s["vol_ratio"] or 0, s["phase"], " · PUSH" if s["push"] else "")

    push_res: dict = {"skipped": True}
    if not dry_run and not no_push:
        subs, src = push.subscriptions()
        push_res = {"source": src, "n_devices": len(subs)}
        if subs and push.configured():
            push_res.update(_send(signals, trade_iso, subs))
            if cfg.get("heartbeat") and now.weekday() == 0:
                push_res["heartbeat"] = push.send(push.heartbeat_payload(n_tr, trade_iso), subs)["sent"]
            if push.test_requested():
                push_res["test"] = push.send(push.test_payload(), subs)["sent"]
        elif not push.configured():
            push_res["errors"] = ["Thiếu khoá VAPID"]
        if push_res.get("gone"):
            st["push_gone_at"] = now.isoformat(timespec="seconds")

    latest = {
        "generated_at": now.isoformat(timespec="seconds"), "trade_date": trade_iso,
        "watchlist": {"n": len(tickers), "source": wl_source},
        "source": {"dnse_ok": bool(dnse.last_ok), "dnse_error": dnse.last_error, "n_priced": len(bars),
                   "unsettled": unsettled, "late": late},
        "settings": {k: v for k, v in cfg.items() if not k.startswith("_")},
        "events": {k: {kk: vv for kk, vv in v.items()} for k, v in W.EVENTS.items()},
        "stats_generated_at": stats.get("generated_at"),
        "signals": signals, "board": board, "stale": stale,
        "summary": {"buy": sum(1 for s in signals if s["direction"] == "buy"), "exit": sum(1 for s in signals if s["direction"] == "exit"),
                    "watch": sum(1 for s in signals if s["direction"] == "watch"),
                    "acc": sum(1 for r in board if r["phase"] in ("A", "B", "C", "D")), "dist": sum(1 for r in board if r["phase"] == "PP"),
                    "markup": sum(1 for r in board if r["phase"] == "E"), "none": sum(1 for r in board if r["phase"] in ("-", "E↓"))},
        "push": push_res,
    }
    if dry_run:
        print(json.dumps({k: v for k, v in latest.items() if k in ("trade_date", "source", "summary", "stale")}, ensure_ascii=False, indent=1, default=str))
        return 0

    _dump(daily_file, {"trade_date": trade_iso, "generated_at": latest["generated_at"], "late": late,
                       "signals": [{"symbol": s["symbol"], "event": s["event"], "name": s["name"], "direction": s["direction"],
                                    "price": s["price"], "push": s["push"], "grade": s["grade"]} for s in signals],
                       "stale": stale})
    latest["history"] = history(int(cfg.get("history_days") or 30), hist)
    _dump(LATEST, latest)
    BARS.write_text(json.dumps({"trade_date": trade_iso, **chart}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    if changed:
        store_mod.save(hist, HISTORY)
    st.update({"last_run": now.isoformat(timespec="seconds"), "last_trade_date": trade_iso, "dnse_error": dnse.last_error,
               "push": push_res, "watchlist": {"n": len(tickers), "source": wl_source},
               "last_signals": [f"{s['symbol']}:{s['event']}" for s in signals]})
    _dump(STATE, st)
    log.info("Xong: %d mã, %d tín hiệu, push %s", len(board), len(signals), push_res)
    return 0


def _welcome_new_devices(st: dict, now: datetime) -> None:
    """Máy mới đăng ký → gửi ngay một thông báo chào mừng, TRƯỚC bước idempotent. Chép từ price-path."""
    subs, src = push.subscriptions()
    st["devices"] = {"n": len(subs), "source": src, "vapid": push.configured(), "checked_at": now.isoformat(timespec="seconds")}
    if not subs or not push.configured():
        _dump(STATE, st)
        return
    known = set(st.get("known_subs") or [])
    new = [s for s in subs if push._sub_id(s) not in known]
    if new:
        payload = {"kind": "welcome", "title": "Đã kết nối — máy này sẽ nhận thông báo",
                   "body": "Tín hiệu Wyckoff sau phiên 15:45 các ngày T2–T6: mặc định chỉ SC (bán tháo cao trào) — sự kiện đã đo đạt.",
                   "url": "./#today", "tag": "wr-welcome"}
        r = push.send(payload, new)
        log.info("Chào mừng %d máy mới (nguồn %s): %s", len(new), src, r)
        st["welcome"] = {"at": now.isoformat(timespec="seconds"), **r}
    st["known_subs"] = sorted(known | {push._sub_id(s) for s in subs})
    _dump(STATE, st)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="chạy lại dù hôm nay đã có file")
    ap.add_argument("--dry-run", action="store_true", help="in kết quả, không ghi file, không push")
    ap.add_argument("--no-push", action="store_true", help="ghi file nhưng không gửi thông báo")
    a = ap.parse_args()
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(run(force=a.force, dry_run=a.dry_run, no_push=a.no_push))


if __name__ == "__main__":
    main()
