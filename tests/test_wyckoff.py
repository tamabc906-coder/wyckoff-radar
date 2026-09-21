"""Test lõi Wyckoff bằng chuỗi nến tổng hợp: một chu kỳ tích lũy đầy đủ (giảm → SC → AR → ST → Spring #3 →
SOS → LPS), biến thể Spring #2 + Test, phân phối (BC → AR → UTAD → SOW), và các trường hợp âm."""
from datetime import date, timedelta

from job import wyckoff as W


def _bars(rows):
    """rows: (o, h, l, c, v). Ngày tăng dần từ 2024-01-01 (bỏ T7/CN cho giống thật)."""
    out, d = [], date(2024, 1, 1)
    for o, h, l, c, v in rows:
        while d.weekday() >= 5:
            d += timedelta(days=1)
        out.append({"d": d, "o": float(o), "h": float(h), "l": float(l), "c": float(c), "v": int(v), "t": 0})
        d += timedelta(days=1)
    return out


def flat(n, px=30.0, v=100, rng=0.6):
    return [(px, px + rng / 2, px - rng / 2, px, v) for _ in range(n)]


def decline(n, start, step, v=120, rng=0.6):
    rows, c = [], start
    for _ in range(n):
        o = c
        c = round(c - step, 3)
        rows.append((o, o + rng / 3, c - rng / 3, c, v))
    return rows


def oscillate(n, lo, hi, v=90, rng=0.5):
    """Dao động răng cưa giữa lo..hi (đóng cửa), chạm cả hai biên nhiều lần."""
    rows = []
    for k in range(n):
        t = (k % 6) / 5
        c = lo + (hi - lo) * (t if (k // 6) % 2 == 0 else 1 - t)
        rows.append((c, c + rng / 2, c - rng / 2, c, v))
    return rows


def ids(R):
    return [e["id"] for e in R.events if e["id"] not in ("er_absorb", "no_demand")]


def accumulation_rows(spring=("spring3",)):
    rows = flat(40) + decline(15, 30.0, 0.3)                       # → ~25.5
    rows += [(25.4, 25.6, 24.0, 24.8, 350)]                        # SC: KL 3,5×, spread rộng, đóng 50 % từ đáy
    rows += [(24.9, 25.2, 24.7, 25.0, 200), (25.0, 25.5, 24.9, 25.4, 180), (25.4, 25.9, 25.3, 25.8, 160),
             (25.8, 26.3, 25.7, 26.2, 140), (26.2, 26.7, 26.1, 26.5, 120),   # AR high 26.7
             (26.5, 26.6, 26.1, 26.3, 100), (26.3, 26.4, 25.9, 26.0, 90), (26.0, 26.1, 25.7, 25.8, 90)]
    rows += oscillate(12, 24.6, 26.3)                              # Phase B
    rows += [(24.6, 24.8, 24.2, 24.5, 60)]                         # ST: về gần đáy, KL < 0,7×SC, spread hẹp
    rows += oscillate(12, 24.6, 26.3)
    if "spring3" in spring:
        rows += [(24.4, 24.6, 23.85, 24.45, 55)]                   # Spring #3: phá 0,6 %, KL 0,6×, đóng 80 %
    if "spring2" in spring:
        rows += [(24.4, 24.6, 23.5, 24.3, 120)]                    # Spring #2: phá 2,1 %, KL 1,3×
        rows += [(24.3, 24.9, 24.2, 24.8, 95), (24.8, 25.2, 24.6, 25.0, 90)]
        rows += [(24.7, 24.9, 24.4, 24.8, 40)]                     # Test: KL < ½ spring, spread hẹp, giữ trên đáy spring
    rows += oscillate(6, 24.8, 26.2, v=85)
    rows += [(25.5, 27.6, 25.4, 27.5, 250)]                        # SOS: thân 2,0 ≥ 1,5×ATR, KL ≥ 1,5×, vượt 26,7
    rows += [(27.3, 27.4, 26.9, 27.0, 70), (27.0, 27.1, 26.6, 26.7, 60), (26.7, 26.9, 26.5, 26.8, 50)]  # lùi KL thấp
    rows += [(26.9, 27.6, 26.8, 27.5, 130)]                        # LPS: nến tăng đóng trên đỉnh nhịp lùi
    return rows


def test_accumulation_full_cycle():
    R = W.analyze(_bars(accumulation_rows()))
    seq = ids(R)
    for eid in ("sc", "ar", "st", "spring3", "sos", "lps"):
        assert eid in seq, (eid, seq)
    assert seq.index("sc") < seq.index("ar") < seq.index("st") < seq.index("spring3") < seq.index("sos") < seq.index("lps")
    tr = next(t for t in R.trs if t.origin == "sc")
    assert tr.kind == "acc" and R.tr is None and R.markup is not None and R.markup.tr is tr
    assert abs(tr.lo - 24.0) < 1e-9 and abs(tr.hi - 26.7) < 1e-9
    assert len(tr.st_i) <= 3 and all(j < tr.spring_i for j in tr.st_i)
    sp = next(e for e in R.events if e["id"] == "spring3")
    assert 0 < sp["break_pct"] < 0.01 and sp["vol_ratio"] < 0.7 and sp["stop"] < 23.85
    sos = next(e for e in R.events if e["id"] == "sos")
    assert sos["target"]["min"] > 26.7 and sos["age"] >= 20
    lps = next(e for e in R.events if e["id"] == "lps")
    assert abs(lps["low"] - 26.5) < 1e-9 and lps["pull_bars"] == 3
    # AR là nhãn hồi tố: at > i
    ar = next(e for e in R.events if e["id"] == "ar")
    assert ar["at"] > ar["i"]


def test_spring2_needs_test_then_buy():
    R = W.analyze(_bars(accumulation_rows(spring=("spring2",))))
    seq = ids(R)
    assert "spring3" not in seq and "spring2" in seq and "test" in seq
    assert seq.index("spring2") < seq.index("test")
    t = next(e for e in R.events if e["id"] == "test")
    assert t["spring"] == "spring2" and W.EVENTS["test"]["direction"] == "buy"


def test_signals_at_only_today_and_sorted():
    bars = _bars(accumulation_rows())
    R = W.analyze(bars)
    last = len(bars) - 1
    today = W.signals_at(R, last)
    assert [e["id"] for e in today] == ["lps"]
    assert W.signals_at(R, last - 1) == []
    st = W.board_state(R, last)
    assert st["phase"] == "E" and st["last_event"] == "lps" and st["tr"]["sos"] is not None


def test_no_sos_when_range_too_young():
    rows = flat(40) + decline(15, 30.0, 0.3) + [(25.4, 25.6, 24.0, 24.8, 350)]
    rows += [(24.9, 25.2, 24.7, 25.0, 200), (25.0, 25.5, 24.9, 25.4, 180), (25.4, 25.9, 25.3, 25.8, 160),
             (25.8, 26.3, 25.7, 26.2, 140), (26.2, 26.7, 26.1, 26.5, 120),
             (26.5, 26.6, 26.1, 26.3, 100), (26.3, 26.4, 25.9, 26.0, 90), (26.0, 26.1, 25.7, 25.8, 90)]
    rows += oscillate(6, 24.6, 26.3)
    rows += [(25.5, 27.6, 25.4, 27.5, 250)]                        # bứt phá khi vùng mới ~15 phiên
    R = W.analyze(_bars(rows))
    assert "sos" not in ids(R)


def test_high_volume_break_is_not_spring3():
    rows = accumulation_rows(spring=())
    # thay Spring #3 bằng cú phá 0,6 % nhưng KL 2×
    rows.insert(len(flat(40) + decline(15, 30.0, 0.3)) + 1 + 8 + 12 + 1 + 12, (24.4, 24.6, 23.85, 24.45, 180))
    R = W.analyze(_bars(rows))
    seq = ids(R)
    assert "spring3" not in seq and "spring2" in seq


def test_distribution_bc_utad_sow():
    rows = flat(40, px=20.0)
    rows += [(c, c + 0.3, c - 0.2, c + 0.25, 120) for c in [20 + 0.3 * k for k in range(15)]]   # tăng 15 phiên → ~24.5
    rows += [(24.6, 26.0, 24.4, 24.9, 400)]                        # BC: KL 4×, spread rộng, đóng xa đỉnh
    rows += [(24.8, 24.9, 24.3, 24.4, 200), (24.4, 24.5, 23.9, 24.0, 180), (24.0, 24.1, 23.5, 23.6, 150),
             (23.6, 23.7, 23.2, 23.3, 130), (23.3, 23.5, 23.0, 23.2, 120),   # AR low 23.0
             (23.2, 23.6, 23.1, 23.5, 100), (23.5, 23.9, 23.4, 23.8, 90), (23.8, 24.1, 23.7, 24.0, 90)]
    rows += oscillate(24, 23.4, 25.6, v=90)
    rows += [(25.5, 26.4, 25.2, 25.4, 150)]                        # UTAD: phá 26,0 lên 26,4 (1,5 %) rồi đóng trong
    rows += oscillate(4, 24.0, 25.0, v=85)
    rows += [(24.0, 24.1, 22.3, 22.4, 260)]                        # SOW: nến giảm rộng, KL lớn, phá đáy 23,0
    R = W.analyze(_bars(rows))
    seq = ids(R)
    for eid in ("bc", "ar", "utad", "sow"):
        assert eid in seq, (eid, seq)
    tr = next(t for t in R.trs if t.kind == "dist")
    assert abs(tr.hi - 26.0) < 1e-9 and abs(tr.lo - 23.0) < 1e-9
    assert W.EVENTS["sow"]["direction"] == "exit"


def test_range_origin_needs_prior_decline():
    # đi ngang 28–31 sau khi giảm từ 36 → có vùng gốc "range", tuổi tính từ lúc phát hiện
    rows = flat(40, px=36.0) + decline(15, 36.0, 0.4) + oscillate(30, 28.0, 31.0, v=100)
    R = W.analyze(_bars(rows))
    t = next((t for t in R.trs if t.origin == "range"), None)
    assert t is not None and t.kind == "acc" and t.phase == "B"
    assert 27.5 <= t.lo <= 28.0 and 31.0 <= t.hi <= 32.5 and t.start >= 55 + 14
    # cùng dao động nhưng KHÔNG có đợt giảm dẫn vào → không lập vùng
    R2 = W.analyze(_bars(flat(60, px=29.5) + oscillate(30, 28.0, 31.0, v=100)))
    assert not any(t.origin == "range" for t in R2.trs)


def test_phase_d_keeps_range_until_lps_or_timeout():
    rows = accumulation_rows()
    R = W.analyze(_bars(rows))
    tr = next(t for t in R.trs if t.origin == "sc")
    lps = next(e for e in R.events if e["id"] == "lps")
    assert tr.end == lps["i"] and tr.end_reason == "up" and R.markup is not None and R.markup.lps_low == lps["low"]
    # không có LPS: vùng đóng sau 20 phiên kể từ SOS
    rows2 = rows[:-4] + [(27.6 + 0.2 * k, 27.9 + 0.2 * k, 27.4 + 0.2 * k, 27.8 + 0.2 * k, 200) for k in range(22)]
    R2 = W.analyze(_bars(rows2))
    tr2 = next(t for t in R2.trs if t.origin == "sc")
    assert tr2.lps_i is None and tr2.end == tr2.sos_i + 20 and tr2.end_reason == "up"


def test_limit_flags_and_helpers():
    bars = _bars([(10, 10.5, 9.5, 10, 100), (10, 10.1, 9.2, 9.3, 100), (9.3, 10.0, 9.3, 9.95, 100)])
    assert W.limit_flags(bars, 1, 0.065) == (True, False)
    assert W.limit_flags(bars, 2, 0.065) == (False, True)
    assert W.close_pos(bars[0]) == 0.5 and abs(W.body(bars[1]) - 0.7) < 1e-9
    atr = W.atr_wilder(bars, 2)
    assert atr[0] is None and atr[1] is not None
    assert W.analyze(bars).events == []          # < MIN_BARS → không sự kiện


def test_relative_strength():
    b = _bars([(1, 1, 1, 10 + k * 0.1, 1) for k in range(25)])
    idx = _bars([(1, 1, 1, 100 + k * 0.5, 1) for k in range(25)])
    rs = W.relative_strength(b, idx, 20)
    assert rs is not None and rs > 0                  # mã tăng 20 % vs chỉ số 10 %
    assert W.relative_strength(b[:10], idx, 20) is None
