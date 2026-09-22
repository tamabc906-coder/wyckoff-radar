"""Test phần dựng dữ liệu của job (không gọi mạng): thẻ tín hiệu, bảng, biểu đồ, chấm lịch sử, ngày T+2."""
from datetime import date

from job import run_daily as J, wyckoff as W
from tests.test_wyckoff import _bars, accumulation_rows

STATS = {"generated_at": "x", "base": {"10": 0.0057},
         "events": {"sc": {"direction": "buy", "n": 244, "mean": {"5": 0.0266, "10": 0.0302, "20": 0.0569}, "win10": 0.61,
                           "t10": 4.2, "years_won": 7, "years_total": 10, "star": True},
                    "lps": {"direction": "buy", "n": 16, "mean": {"5": 0.028, "10": 0.0207, "20": 0.0034}, "win10": 0.44,
                            "t10": 1.2, "years_won": 0, "years_total": 0, "star": False},
                    "st": {"direction": "watch", "n": 851, "mean": {"5": -0.005, "10": -0.002, "20": 0.006}, "win10": 0.45,
                           "t10": -0.7, "years_won": 2, "years_total": 11, "star": False}}}
CFG = {"events_disabled": ["lps"], "buy_only": False}
META = {"symbol": "HPG", "company_name": "Hoà Phát", "exchange": "HOSE"}


def _run():
    bars = _bars(accumulation_rows())
    R = W.analyze(bars)
    return bars, R


def test_build_signal_lps_disabled_and_graded():
    bars, R = _run()
    e = W.signals_at(R, len(bars) - 1)[0]
    s = J.build_signal("HPG", META, bars, R, e, STATS, CFG)
    assert s["event"] == "lps" and s["direction"] == "buy" and s["push"] is False
    assert s["grade"] == "đo kém" and s["stats"]["n"] == 16 and s["stats"]["base10"] == 0.0057
    assert s["stop"] < s["price"] and s["stop_pct"] < 0 and s["rr"] is not None
    assert len(s["candles"]) == J.CANDLES_IN_CARD and s["candles"][-1][4] == bars[-1]["c"]
    assert any(m[1] == "sos" for m in s["marks"]) and all(0 <= m[0] < J.CANDLES_IN_CARD for m in s["marks"])
    assert s["phase"] == "E" and s["t2_date"] > bars[-1]["d"].isoformat()


def test_build_signal_sc_pushed_and_watch_ungraded():
    bars, R = _run()
    sc = next(e for e in R.events if e["id"] == "sc")
    s = J.build_signal("HPG", META, bars, R, sc, STATS, CFG)
    assert s["push"] is True and s["grade"] == "★" and s["stats"]["years_won"] == 7
    st = next(e for e in R.events if e["id"] == "st")
    s2 = J.build_signal("HPG", META, bars, R, st, STATS, CFG)
    assert s2["push"] is False and s2["grade"] is None and s2["stats"]["n"] == 851
    # buy_only chặn THOÁT, không chặn MUA
    s3 = J.build_signal("HPG", META, bars, R, sc, STATS, {"events_disabled": [], "buy_only": True})
    assert s3["push"] is True


def test_spring2_is_exit_and_pushed_when_enabled():
    from tests.test_wyckoff import accumulation_rows as rows_fn
    bars = _bars(rows_fn(spring=("spring2",)))
    R = W.analyze(bars)
    e = next(x for x in R.events if x["id"] == "spring2")
    assert W.EVENTS["spring2"]["direction"] == "exit"
    stats = {"base": {"10": 0.0057}, "events": {"spring2": {"direction": "exit", "n": 151, "mean": {"5": -0.02, "10": -0.0266, "20": -0.023},
                                                             "win10": 0.36, "t10": -4.4, "years_won": 8, "years_total": 10, "star": True},
                                                 "sow": {"direction": "exit", "n": 73, "mean": {"5": -0.022, "10": -0.0339, "20": -0.022},
                                                         "win10": 0.32, "t10": -3.3, "years_won": 5, "years_total": 5, "star": False, "near": True}}}
    s = J.build_signal("HPG", META, bars, R, e, stats, {"events_disabled": ["lps"], "buy_only": False})
    assert s["direction"] == "exit" and s["push"] is True and s["grade"] == "★"
    assert J.build_signal("HPG", META, bars, R, e, stats, {"events_disabled": [], "buy_only": True})["push"] is False
    assert J._grade(stats, "sow")[0] == "gần đạt"


def test_board_and_chart_payload():
    bars, R = _run()
    idx = [{"d": b["d"], "c": 1000.0 + k} for k, b in enumerate(bars)]
    row = J.build_board("HPG", META, bars, R, idx)
    assert row["phase"] == "E" and row["tr_lo"] == 24.0 and row["last_event"] == "lps" and row["rs_20"] is not None
    rows, marks, trs = J.chart_payload("HPG", bars, R)
    assert len(rows) == min(J.BARS_IN_CHART, len(bars)) and marks[-1][1] == "lps"
    assert any(t["origin"] == "sc" and t["lo"] == 24.0 and t["open"] is False for t in trs)


def test_history_scoring_and_t2(tmp_path, monkeypatch):
    bars, _ = _run()
    hist = {"bars": {"HPG": [[b["d"].isoformat(), b["o"], b["h"], b["l"], b["c"], b["v"]] for b in bars]}}
    d = bars[-12]["d"].isoformat()
    monkeypatch.setattr(J, "DAILY", tmp_path)
    J._dump(tmp_path / f"{d}.json", {"trade_date": d, "signals": [{"symbol": "HPG", "event": "x", "direction": "buy", "price": 1}]})
    J._dump(tmp_path / f"{bars[-1]['d'].isoformat()}.json", {"trade_date": bars[-1]["d"].isoformat(), "signals": []})
    h = J.history(30, hist)
    assert h[0]["signals"] == [] and h[1]["date"] == d
    s = h[1]["signals"][0]
    assert s["r5"] is not None and s["r10"] is not None
    exp10 = (bars[-1]["c"] * (1 - J.FEE - J.TAX) / (bars[-11]["o"] * (1 + J.FEE)) - 1) * 100
    assert abs(s["r10"] - round(exp10, 2)) < 1e-9
    assert J._t2(date(2026, 9, 21)) == date(2026, 9, 24)       # T2 → mua T3, bán được T5
    assert J._t2(date(2026, 9, 18)) == date(2026, 9, 23)       # T6 → mua T2, bán được T4
