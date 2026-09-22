/* Wyckoff Radar — giao diện điện thoại. JS thuần, đọc data/latest.json (thẻ, bảng, lịch sử), data/stats.json
   (số đo 11 năm), data/bars.json (biểu đồ). Không tính tín hiệu ở đây: thứ hiện đúng bằng thứ job đã báo.
   Khung tab/toast/push chép từ candle-radar/docs/app.js. */
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const CFG = window.WR_CONFIG || {};
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const dmy = (iso) => iso ? iso.slice(0, 10).split("-").reverse().slice(0, 2).join("/") : "—";
  const dow = (iso) => ["CN", "T2", "T3", "T4", "T5", "T6", "T7"][new Date(iso + "T00:00:00").getDay()];
  const px = (v) => v == null ? "—" : Number(v).toFixed(2);
  const pct = (v, d = 1) => v == null ? "—" : (v > 0 ? "+" : "") + Number(v).toFixed(d).replace(".", ",") + " %";
  const mult = (v) => v == null ? "—" : Number(v).toFixed(2).replace(".", ",") + "×";
  const ABBR = { sc: "SC", ar: "AR", st: "ST", spring1: "Sp#1", spring2: "Sp#2", spring3: "Sp#3", test: "Test", sos: "SOS", lps: "LPS", bu: "BU", ut: "UT", bc: "BC", utad: "UTAD", sow: "SOW", lpsy: "LPSY" };
  const DIR_VN = { buy: "MUA", exit: "THOÁT", watch: "Theo dõi" };
  const PHASE_TXT = { A: "dừng giảm", B: "xây nền", C: "spring/test", D: "SOS/LPS", E: "tăng giá", "E↓": "giảm giá", PP: "phân phối", "-": "không nền" };
  const O = 1, H = 2, L = 3, C = 4, V = 5;

  let D = null, STATS = null;

  // ---------------------------------------------------------------- mini chart trong thẻ
  function miniChart(candles, tr, marks, W, H_) {
    const n = candles.length; if (!n) return "";
    let hi = Math.max(...candles.map((c) => c[H])), lo = Math.min(...candles.map((c) => c[L]));
    if (tr) { hi = Math.max(hi, tr.hi); lo = Math.min(lo, tr.lo); }
    const span = (hi - lo) || 1, pad = 8, y = (v) => pad + (hi - v) / span * (H_ - 2 * pad);
    const step = W / n, w = Math.max(2, step - 2);
    let s = "";
    if (tr) {
      s += `<line x1="0" y1="${y(tr.hi).toFixed(1)}" x2="${W}" y2="${y(tr.hi).toFixed(1)}" stroke="#D9B36A" stroke-dasharray="3 3"/>`;
      s += `<line x1="0" y1="${y(tr.lo).toFixed(1)}" x2="${W}" y2="${y(tr.lo).toFixed(1)}" stroke="#D9B36A" stroke-dasharray="3 3"/>`;
      s += `<text x="${W - 3}" y="${(y(tr.hi) - 2).toFixed(1)}" font-size="8" fill="#8A6A2B" text-anchor="end">${px(tr.hi)}</text>`;
      s += `<text x="${W - 3}" y="${(y(tr.lo) + 9).toFixed(1)}" font-size="8" fill="#8A6A2B" text-anchor="end">${px(tr.lo)}</text>`;
    }
    const mk = new Map((marks || []).map((m) => [m[0], m[1]]));
    candles.forEach((c, i) => {
      const up = c[C] >= c[O], col = up ? "#2E7D4F" : "#B84A3A", x = i * step + 1, cx = x + w / 2;
      const ty = y(Math.max(c[O], c[C])), bh = Math.max(1, y(Math.min(c[O], c[C])) - ty);
      s += `<line x1="${cx.toFixed(1)}" y1="${y(c[H]).toFixed(1)}" x2="${cx.toFixed(1)}" y2="${y(c[L]).toFixed(1)}" stroke="${col}"/>`;
      s += `<rect x="${x.toFixed(1)}" y="${ty.toFixed(1)}" width="${w.toFixed(1)}" height="${bh.toFixed(1)}" fill="${up ? "#fff" : col}" stroke="${i === n - 1 ? "#D9B36A" : col}" stroke-width="${i === n - 1 ? 1.5 : 1}"/>`;
      if (mk.has(i)) {
        const id = mk.get(i), dirn = (D && D.events[id] || {}).direction, below = ["sc", "st", "spring1", "spring2", "spring3", "test", "lps", "bu", "lpsy"].includes(id);
        const fill = dirn === "buy" ? "#2E7D4F" : dirn === "exit" ? "#B84A3A" : "#8A7B66";
        const ly = below ? y(c[L]) + 10 : y(c[H]) - 4;
        s += `<text x="${cx.toFixed(1)}" y="${ly.toFixed(1)}" font-size="7.5" font-weight="700" fill="${fill}" text-anchor="middle">${ABBR[id] || id}</text>`;
      }
    });
    return s;
  }

  // ---------------------------------------------------------------- Hôm nay
  function statLine(s) {
    if (!s.stats) return "";
    const m = s.stats, tag = s.grade === "★" ? `<span class="tag star">★ ${pct(m.mean10 * 100, 1)}/10p</span>` : s.grade ? `<span class="tag poor">Đo kém ${pct(m.mean10 * 100, 1)}/10p</span>` : `<span class="tag">Sau sự kiện ${pct(m.mean10 * 100, 1)}/10p</span>`;
    const yrs = m.years_total != null ? ` · ${m.years_won}/${m.years_total} năm` : "";
    return `${tag}${yrs} · ${m.n} lệnh · mua-đại ${pct(m.base10 * 100, 2)}`;
  }
  function card(s, idx) {
    const tr = s.tr, dir = s.direction, kind = dir === "buy" ? "buy" : dir === "exit" ? "exit" : "watch";
    const cls = s.change_pct > 0 ? "up" : s.change_pct < 0 ? "down" : "flat";
    const lv = [];
    const isTest = s.event === "test";
    lv.push({ k: "KL / TB20", v: mult(s.vol_ratio), ok: isTest || s.event === "spring3" ? s.vol_ratio <= 0.7 : s.vol_ratio >= 1.5 });
    lv.push({ k: "Spread / ATR", v: s.spread_atr == null ? "—" : String(s.spread_atr).replace(".", ","), ok: isTest ? s.spread_atr <= 0.8 : s.spread_atr >= 1.5 });
    lv.push({ k: "Đóng cửa", v: s.close_pos + " %", ok: dir === "exit" ? s.close_pos <= 30 : s.close_pos >= 50 });
    if (tr && s.price) {
      const ref = dir === "exit" || ["sc", "st", "spring1", "spring2", "spring3", "test"].includes(s.event) ? tr.lo : tr.hi;
      lv.push({ k: ref === tr.lo ? "Cách biên dưới" : "Cách creek", v: pct((s.price / ref - 1) * 100, 1), ok: false });
    } else lv.push({ k: "Vùng", v: "chưa có", ok: false });
    const zone = tr ? `${tr.kind === "dist" ? "Phân phối" : "Tích lũy"} ${s.age != null ? s.age + " phiên" : ""} · GĐ ${esc(s.phase)}${tr.origin === "range" ? " · nền không có SC" : ""}` : "Chưa có vùng — chờ AR/ST";
    const kv = [
      ["Vùng", zone],
      s.advice ? ["Gợi ý", esc(s.advice)] : null,
      s.stop ? ["Stop", `${px(s.stop)} (${pct(s.stop_pct, 1)})`] : null,
      s.target ? ["Mục tiêu", s.beyond_target ? `đã vượt mục tiêu tối thiểu ${px(s.target.min)} — chỉ giữ, không mua đuổi` : `${px(s.target.min)} (${pct((s.target.min / s.price - 1) * 100, 1)})${s.rr != null ? " · RR " + String(s.rr).replace(".", ",") : ""}`] : null,
      s.stats ? ["Đã đo", statLine(s)] : null,
      dir === "buy" ? ["Lưu ý", `T+2: bán sớm nhất ${dmy(s.t2_date)}.${s.caution ? " " + esc(s.caution) : ""}`] : s.caution ? ["Lưu ý", esc(s.caution)] : null,
    ].filter(Boolean);
    const warn = s.grade === "đo kém" && s.push ? `<div class="warnbox">Sự kiện này không đạt ★ khi đo 11 năm — hiện vì bạn bật thủ công trong Cài đặt. Coi là nhắc nhở, không phải lệnh.</div>` : "";
    const trLine = tr ? { lo: tr.lo, hi: tr.hi } : null;
    return `<article class="card ${kind}">
      <div class="hd"><span class="no">${idx}</span><h3>${esc(s.symbol)} <small>· ${esc(s.company_name).replace(/^Công ty Cổ phần /i, "")}</small></h3><span class="chip ${kind}">${DIR_VN[dir]} · ${esc(s.name).replace(/\s*\(.*\)$/, "")}</span></div>
      <div class="desc">${esc(s.hint)}</div>
      <div class="chartrow"><svg viewBox="0 0 270 88" preserveAspectRatio="none" aria-hidden="true">${miniChart(s.candles, trLine, s.marks, 270, 88)}</svg>
        <div class="px"><div class="v">${px(s.price)}</div><div class="c ${cls}">${pct(s.change_pct, 1)}</div><div class="k">KL ${(s.volume / 1e6).toFixed(1).replace(".", ",")} tr</div></div></div>
      <div class="lv4">${lv.map((x) => `<div class="${x.ok ? "ok" : ""}"><div class="k">${x.k}</div><div class="v">${x.ok ? "✓ " : ""}${x.v}</div></div>`).join("")}</div>
      <div class="kv">${kv.map(([k, v]) => `<div><span>${k}</span><span>${v}</span></div>`).join("")}</div>
      ${warn}
      <button type="button" class="linkbtn" data-chart="${esc(s.symbol)}">Xem biểu đồ →</button>
    </article>`;
  }
  function renderToday() {
    const sm = D.summary || {}, late = D.source && D.source.late;
    $("todaySub").textContent = `Phiên ${dmy(D.trade_date)} · ${late ? "chốt muộn" : "đã chốt ATC"} · ${D.generated_at ? D.generated_at.slice(11, 16) : ""}`;
    $("strip").innerHTML = `<div class="buy"><div class="n">${sm.buy || 0}</div><div class="k">MUA</div></div><div class="exit"><div class="n">${sm.exit || 0}</div><div class="k">THOÁT</div></div><div><div class="n">${sm.acc || 0}</div><div class="k">Tích lũy</div></div><div><div class="n">${sm.dist || 0}</div><div class="k">Phân phối</div></div>`;
    const sig = D.signals || [];
    let html = "", k = 0;
    const groups = [["buy", "Tín hiệu mua"], ["exit", "Tín hiệu thoát"], ["watch", "Theo dõi — không push, chỉ để hiểu vùng"]];
    for (const [dir, label] of groups) {
      const xs = sig.filter((s) => s.direction === dir);
      if (!xs.length) continue;
      html += `<div class="seclabel">${label} · ${xs.length}</div>` + xs.map((s) => card(s, ++k)).join("");
    }
    if (!sig.length) html = `<div class="empty"><b>Không có sự kiện Wyckoff hôm nay</b>${sm.acc || 0} mã đang trong vùng tích lũy, ${sm.dist || 0} phân phối. Bảng cho biết mã nào ở giai đoạn C/D — nơi tín hiệu hay xuất hiện.</div>`;
    else if (!sig.some((s) => s.push)) html = `<div class="empty"><b>Không có tín hiệu đủ ★ hôm nay</b>Bên dưới là sự kiện theo dõi — máy không rung chuông vì chúng chưa đo đạt.</div>` + html;
    $("todayBody").innerHTML = html;
    if (D.stale && D.stale.length) $("todayBody").insertAdjacentHTML("beforeend", `<div class="foot">Nến cũ, không xét: ${D.stale.join(", ")}</div>`);
  }

  // ---------------------------------------------------------------- Bảng
  let boardFilter = "all";
  const FILTERS = [["all", "Tất cả"], ["acc", "Tích lũy"], ["ready", "Sẵn sàng (C·D)"], ["dist", "Phân phối"], ["markup", "Tăng giá"], ["none", "Không nền"]];
  const inFilter = (r, f) => f === "all" || (f === "acc" && "ABCD".includes(r.phase) && r.phase.length === 1) || (f === "ready" && (r.phase === "C" || r.phase === "D")) || (f === "dist" && r.phase === "PP") || (f === "markup" && r.phase === "E") || (f === "none" && (r.phase === "-" || r.phase === "E↓"));
  function renderBoard() {
    const rows = D.board || [];
    $("boardSub").textContent = `${rows.length} mã · phiên ${dmy(D.trade_date)}`;
    $("boardChips").innerHTML = FILTERS.map(([f, l]) => `<button type="button" data-f="${f}" aria-pressed="${f === boardFilter}">${l} ${rows.filter((r) => inFilter(r, f)).length}</button>`).join("");
    const order = { C: 0, D: 1, A: 2, B: 3, E: 4, PP: 5, "-": 6, "E↓": 7 };
    const xs = rows.filter((r) => inFilter(r, boardFilter)).sort((a, b) => (order[a.phase] ?? 9) - (order[b.phase] ?? 9) || a.symbol.localeCompare(b.symbol));
    let h = `<div class="trow h"><span>Mã</span><span>GĐ</span><span>Vùng · sự kiện gần nhất</span><span>Biên vùng</span><span style="text-align:right">RS20</span></div>`;
    for (const r of xs) {
      const g = r.phase === "C" || r.phase === "D" || r.phase === "E", rr = r.phase === "PP" || r.phase === "E↓", none = r.phase === "-";
      const ev = r.last_event ? (D.events[r.last_event] || {}) : null;
      const evName = ev ? esc(ev.name).replace(/\s*\(.*\)$/, "") : "Không nền";
      const evCls = ev ? (ev.direction === "buy" ? "g" : ev.direction === "exit" ? "r" : "d") : "d";
      const sub = r.tr_age != null ? `${r.tr_kind === "dist" ? "phân phối" : "tích lũy"} ${r.tr_age} phiên${r.tr_origin === "range" ? " · nền" : " · SC"}` : r.phase === "E" ? "đã rời vùng, đang tăng" : r.phase === "E↓" ? "đã rời vùng, đang giảm" : PHASE_TXT[r.phase];
      h += `<div class="trow ${r.phase === "C" || r.phase === "D" ? "hl" : rr ? "pp" : ""}" data-chart="${esc(r.symbol)}">
        <span class="sym">${esc(r.symbol)}</span><span class="ph ${g ? "g" : rr ? "r" : none ? "n" : ""}">${esc(r.phase === "E↓" ? "E" : r.phase)}</span>
        <span class="ev"><b class="${evCls}">${evName}${r.last_event_date ? " · " + dmy(r.last_event_date) : ""}</b><small>${esc(sub)}</small></span>
        <span class="rg">${r.tr_lo != null ? px(r.tr_lo) + " – " + px(r.tr_hi) : "—"}</span>
        <span class="rs ${r.rs_20 > 0 ? "g" : r.rs_20 < 0 ? "r" : ""}">${pct(r.rs_20, 1)}</span></div>`;
    }
    $("boardBody").innerHTML = h;
  }
  $("boardChips").addEventListener("click", (ev) => { const b = ev.target.closest("button"); if (!b) return; boardFilter = b.dataset.f; renderBoard(); });

  // ---------------------------------------------------------------- Lịch sử
  function renderHistory() {
    const hist = D.history || [];
    const scored = hist.flatMap((d) => d.signals.filter((s) => s.direction !== "watch" && s.r10 != null).map((s) => ({ ...s, adj: s.direction === "exit" ? -s.r10 : s.r10 })));
    const pushed = hist.flatMap((d) => d.signals.filter((s) => s.push));
    const avg = scored.length ? scored.reduce((a, s) => a + s.adj, 0) / scored.length : null;
    const hit = scored.length ? scored.filter((s) => s.adj > 0).length : 0;
    $("histSub").textContent = `${hist.length} phiên gần nhất · ${pushed.length} thông báo`;
    $("totals").innerHTML = `<div class="tot"><div class="v">${pushed.length}</div><div class="k">đã báo (push)</div></div><div class="tot"><div class="v ${avg > 0 ? "g" : avg < 0 ? "r" : ""}">${avg == null ? "—" : pct(avg, 2)}</div><div class="k">TB +10p (${scored.length} đủ ngày)</div></div><div class="tot"><div class="v">${scored.length ? hit + "/" + scored.length : "—"}</div><div class="k">đúng hướng</div></div>`;
    const rv = (v, dir) => v == null ? `<b class="n">—</b>` : `<b class="${(dir === "exit" ? -v : v) > 0 ? "g" : "r"}">${pct(v, 1)}</b>`;
    $("days").innerHTML = hist.map((d) => {
      const rows = d.signals.map((s) => `<div class="hrow ${s.direction}" data-chart="${esc(s.symbol)}"><span class="sym">${esc(s.symbol)}</span><span class="ev"><b>${esc(s.name).replace(/\s*\(.*\)$/, "")}${s.push ? " · đã báo" : ""}</b><small>${DIR_VN[s.direction]}${s.grade ? " · " + s.grade : ""} · giá ${px(s.price)}</small></span><span class="r"><small>+5p</small>${rv(s.r5, s.direction)}</span><span class="r"><small>+10p</small>${rv(s.r10, s.direction)}</span></div>`).join("");
      return `<div class="day"><div class="dl">${dow(d.date)} · ${dmy(d.date)}${d.replay ? " <small>· tái lập</small>" : ""}${d.late ? " <small>· chốt muộn</small>" : ""}</div>${rows || '<div class="none">Không có sự kiện.</div>'}</div>`;
    }).join("");
  }

  // ---------------------------------------------------------------- Cài đặt
  const THRESH = [["Vùng tối thiểu", "20 phiên"], ["KL cao", "≥ 1,5× TB20"], ["KL thấp", "≤ 0,7× TB20"], ["SC: KL", "≥ 2× TB20"], ["SC: giảm trước", "≥ 10 %/15p"], ["Spring #3 phá", "< 1 %"], ["Test: KL/spring", "< 0,5"], ["Spread rộng", "≥ 1,5× ATR"], ["Stop", "đáy − 0,5× ATR"], ["Mục tiêu", "creek + biên độ"]];
  function erow(id, meta, on) {
    const st = STATS && STATS.events && STATS.events[id];
    let s = "chưa đo";
    if (st) s = `${pct(st.mean["10"] * 100, 2)}/10p · đúng ${Math.round(st.win10 * 100)} % · ${st.years_total ? st.years_won + "/" + st.years_total + " năm · " : ""}${st.n} lệnh · ${String(st.per_month).replace(".", ",")}/th`;
    const tag = meta.direction === "watch" ? "" : st && st.star ? `<span class="tag star">★ đạt</span>` : st ? `<span class="tag poor">đo kém</span>` : "";
    const canToggle = meta.direction !== "watch";
    return `<div class="erow ${on ? "" : "off"}"><div class="t"><div class="n">${esc(meta.name)} ${tag}</div><div class="s">${s}</div></div>${canToggle ? `<button type="button" class="tg ${on ? "on" : ""}" role="switch" aria-checked="${on}" aria-label="${esc(meta.name)}" data-ev="${id}"></button>` : "<span></span>"}</div>`;
  }
  function renderSettings() {
    const dis = new Set((D.settings && D.settings.events_disabled) || []);
    const ev = D.events || {};
    const by = (dir) => Object.keys(ev).filter((k) => ev[k].direction === dir).sort((a, b) => ev[a].priority - ev[b].priority);
    $("buyRows").innerHTML = by("buy").map((k) => erow(k, ev[k], !dis.has(k))).join("");
    $("exitRows").innerHTML = by("exit").map((k) => erow(k, ev[k], !dis.has(k) && !(D.settings && D.settings.buy_only))).join("");
    $("watchRows").innerHTML = by("watch").map((k) => erow(k, ev[k], false)).join("");
    $("thresholds").innerHTML = THRESH.map(([k, v]) => `<div><span>${k}</span><b>${v}</b></div>`).join("");
    if (STATS) $("buyNote").innerHTML = `Số đo ${STATS.n_symbols} mã, ${STATS.from_year} → ${STATS.generated_at.slice(0, 4)}, so với "mua đại rồi giữ 10 phiên" (${pct(STATS.base["10"] * 100, 2)}). ★ = hơn mua-đại, |t| ≥ 2, thắng ≥ 70 % số năm — bật sẵn. "Đo kém" tắt sẵn; bật thì thẻ mang dòng cảnh báo.`;
    fetch("data/state.json", { cache: "no-cache" }).then((r) => r.ok ? r.json() : {}).then((st) => {
      const dv = st.devices || {}, p = st.push || {};
      let s = `Danh mục ${D.watchlist.n} mã (${D.watchlist.source}) · nguồn DNSE ${D.source.dnse_ok ? "OK" : "LỖI " + esc(D.source.dnse_error || "")} · ${D.source.n_priced} mã có giá<br>Lần chạy cuối ${st.last_run ? st.last_run.slice(0, 16).replace("T", " ") : "—"} · phiên ${dmy(st.last_trade_date)} · ${dv.n || 0} máy đã đăng ký (${dv.source || "—"}) · VAPID ${dv.vapid ? "OK" : "THIẾU"}`;
      if (p.n_signals != null) s += ` · lần báo gần nhất: ${p.n_signals} tín hiệu, gửi ${p.sent || 0}`;
      if (st.push_gone_at) s += `<br><b style="color:var(--down)">có máy đã huỷ đăng ký (${st.push_gone_at.slice(0, 10)}) — bấm Đăng ký lại</b>`;
      s += `<br>Số đo: ${STATS ? STATS.generated_at.slice(0, 10) : "—"} · Wyckoff Radar · GitHub Pages`;
      $("stateFoot").innerHTML = s;
    }).catch(() => {});
  }
  document.addEventListener("click", (ev) => {
    const t = ev.target.closest(".tg[data-ev]"); if (!t) return;
    toast("Công tắc chỉ đọc", `Đổi "${t.dataset.ev}" trong docs/data/settings.json (events_disabled) rồi đẩy lên GitHub — job đọc lại mỗi phiên.`);
  });

  // ---------------------------------------------------------------- tải dữ liệu
  function load() {
    return Promise.all([
      fetch("data/latest.json", { cache: "no-cache" }).then((r) => { if (!r.ok) throw new Error("Chưa có data/latest.json — job chưa chạy."); return r.json(); }),
      fetch("data/stats.json", { cache: "no-cache" }).then((r) => r.ok ? r.json() : null).catch(() => null),
    ]).then(([d, s]) => {
      D = d; STATS = s;
      renderToday(); renderBoard(); renderHistory(); renderSettings();
      if ($("p-chart").classList.contains("on")) renderChart();
    }).catch((err) => { $("todayBody").innerHTML = `<div class="err">${esc(err.message)}</div>`; });
  }

  // ---------------------------------------------------------------- push (chép candle-radar)
  const b64ToU8 = (s) => { const p = "=".repeat((4 - s.length % 4) % 4); const b = atob((s + p).replace(/-/g, "+").replace(/_/g, "/")); return Uint8Array.from(b, (c) => c.charCodeAt(0)); };
  const SW = "sw.js?v=1";
  async function pushStatus() {
    const st = $("pushState");
    if (!("serviceWorker" in navigator) || !("PushManager" in window)) { st.textContent = "Trình duyệt này không hỗ trợ thông báo đẩy."; $("pushBtn").disabled = true; return; }
    if (!CFG.VAPID_PUBLIC) { st.textContent = "Chưa có VAPID_PUBLIC trong config.js."; $("pushBtn").disabled = true; return; }
    const reg = await navigator.serviceWorker.ready;
    const sub = await reg.pushManager.getSubscription();
    if (sub) {
      st.textContent = CFG.WORKER_URL ? "Máy này đã đăng ký · máy chủ tạm của GitHub đánh thức được kể cả khi app đóng." : "Máy này đã tạo địa chỉ nhận · đảm bảo đoạn mã bên dưới đã được dán vào GitHub.";
      $("pushBtn").textContent = "Đăng ký lại"; $("testBtn").hidden = !CFG.WORKER_URL; $("pushPill").classList.add("on");
      if (!CFG.WORKER_URL) showSubCode(sub);
    } else { st.textContent = "Máy này chưa đăng ký nhận thông báo."; $("pushPill").classList.remove("on"); }
  }
  function showSubCode(sub) {
    const code = JSON.stringify([sub.toJSON()]);
    $("subCodeWrap").innerHTML = `<div class="subcode"><b>Đoạn mã đăng ký của máy này.</b> Dán vào GitHub → Settings → Secrets and variables → Actions → <span class="mono">PUSH_SUBS_FALLBACK</span> (nhiều máy thì nối các đoạn trong cùng một mảng JSON). Làm một lần mỗi máy.
      <textarea id="subTxt" readonly></textarea><div class="btns" style="margin-top:6px"><button type="button" class="btn" id="copySub">Sao chép</button></div></div>`;
    $("subTxt").value = code;
    $("copySub").addEventListener("click", async () => {
      try { await navigator.clipboard.writeText(code); toast("Đã sao chép", "Dán vào GitHub Secret PUSH_SUBS_FALLBACK."); }
      catch (_) { $("subTxt").select(); document.execCommand("copy"); toast("Đã sao chép", ""); }
    });
  }
  const swReady = () => Promise.race([navigator.serviceWorker.ready, new Promise((_, rej) => setTimeout(() => rej(new Error("Phần chạy nền chưa sẵn sàng — đóng hẳn app, mở lại rồi bấm lần nữa")), 8000))]);
  $("pushBtn").addEventListener("click", async () => {
    const st = $("pushState"), btn = $("pushBtn");
    btn.disabled = true;
    try {
      if (Notification.permission === "denied") { st.textContent = "Điện thoại đang CHẶN thông báo của trang này. Mở Cài đặt trình duyệt → Cài đặt trang web → Thông báo → bật, rồi bấm lại."; return; }
      st.textContent = "Đang xin quyền thông báo… (nếu hiện hộp thoại, bấm Cho phép)";
      const perm = await Notification.requestPermission();
      if (perm !== "granted") { st.textContent = "Anh chưa cho phép. Bấm lại và chọn Cho phép."; return; }
      st.textContent = "Đang chuẩn bị phần chạy nền…";
      if (!navigator.serviceWorker.controller) { try { await navigator.serviceWorker.register(SW); } catch (_) { /* thử tiếp */ } }
      const reg = await swReady();
      st.textContent = "Đang tạo địa chỉ nhận với Google…";
      let sub = await reg.pushManager.getSubscription();
      if (!sub) sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: b64ToU8(CFG.VAPID_PUBLIC) });
      if (CFG.WORKER_URL) {
        const r = await fetch(CFG.WORKER_URL + "/subscribe", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(Object.assign({ ua: navigator.userAgent.slice(0, 120) }, sub.toJSON())) });
        if (!r.ok) throw new Error("Worker trả lỗi " + r.status);
        toast("Đã đăng ký máy này", "Từ giờ tín hiệu sau phiên sẽ tới đây.");
      } else toast("Đã tạo địa chỉ nhận", "Sao chép đoạn mã bên dưới và dán vào GitHub — một lần cho máy này.");
      await pushStatus();
    } catch (err) {
      st.textContent = "Không đăng ký được: " + (err && err.message ? err.message : err) + " — chụp màn hình dòng này gửi lại.";
    } finally { btn.disabled = false; }
  });
  $("testBtn").addEventListener("click", async () => {
    try { const r = await fetch(CFG.WORKER_URL + "/test", { method: "POST" }); toast(r.ok ? "Đã yêu cầu gửi thử" : "Gửi thử lỗi " + r.status, r.ok ? "Thông báo thật sẽ tới trong vài giây." : ""); }
    catch (err) { alert(err.message); }
  });
  let toastTimer = null;
  function toast(t, b) { $("toastTitle").textContent = t; $("toastBody").textContent = b || ""; $("toast").classList.add("on"); clearTimeout(toastTimer); toastTimer = setTimeout(() => $("toast").classList.remove("on"), 5000); }
  $("toast").addEventListener("click", () => $("toast").classList.remove("on"));

  // ---------------------------------------------------------------- Biểu đồ (canvas)
  let BARSD = null, barsLoading = null;
  const cv = $("cvs"), ctx = cv.getContext("2d"), tip = $("tip");   // id ≠ "chart": hash #chart sẽ cuộn tới phần tử trùng id
  const cur = { sym: "", n: 60, end: 0, hover: -1, bars: null, marks: null, trs: null, layout: null };
  function loadBars() {
    if (BARSD) return Promise.resolve(BARSD);
    if (!barsLoading) barsLoading = fetch("data/bars.json", { cache: "no-cache" }).then((r) => { if (!r.ok) throw new Error("Chưa có data/bars.json — job chưa chạy."); return r.json(); })
      .then((j) => { BARSD = j; return j; }).catch((err) => { $("r-lab").textContent = err.message; barsLoading = null; throw err; });
    return barsLoading;
  }
  function openChart(sym) { cur.sym = sym; cur.end = 0; switchTab("chart"); }
  function renderChart() {
    loadBars().then(() => {
      const syms = Object.keys(BARSD.bars).sort();
      const board = new Map(((D && D.board) || []).map((r) => [r.symbol, r]));
      if (!$("c-sym").options.length) $("c-sym").innerHTML = syms.map((s) => { const r = board.get(s); return `<option value="${s}">${s}${r ? " · " + (r.phase === "E↓" ? "E" : r.phase) : ""}</option>`; }).join("");
      if (!cur.sym || !BARSD.bars[cur.sym]) cur.sym = syms.includes("HPG") ? "HPG" : syms[0];
      $("c-sym").value = cur.sym;
      cur.bars = BARSD.bars[cur.sym]; cur.marks = BARSD.marks[cur.sym] || []; cur.trs = BARSD.tr[cur.sym] || [];
      const total = cur.bars.length, n = Math.min(cur.n, total);
      if (cur.end === 0 || cur.end > total) cur.end = total;
      $("r-off").max = total - n; $("r-off").value = cur.end - n;
      const r = board.get(cur.sym), last = cur.bars[total - 1], prev = cur.bars[total - 2];
      const ch = prev ? (last[C] / prev[C] - 1) * 100 : 0;
      $("cpx").innerHTML = `<div class="v">${px(last[C])} <span style="color:${ch > 0 ? "var(--up)" : ch < 0 ? "var(--down)" : "var(--mute)"}">${pct(ch, 1)}</span></div><div class="k">${r ? (r.tr_age != null ? `${r.tr_kind === "dist" ? "Phân phối" : "Tích lũy"} ${r.tr_age} phiên · GĐ ${esc(r.phase)}` : PHASE_TXT[r.phase]) : ""}</div>`;
      $("chartSub").textContent = `${cur.sym}${r ? " · " + esc(r.company_name).replace(/^Công ty Cổ phần /i, "") : ""} · chạm vào nến để xem giá`;
      draw(n);
      renderTimeline();
    }).catch(() => {});
  }
  function draw(n) {
    const bars = cur.bars, W = cv.clientWidth, Hh = cv.clientHeight, dpr = window.devicePixelRatio || 1;
    if (!W || !bars) return;
    cv.width = W * dpr; cv.height = Hh * dpr; ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const end = cur.end, start = Math.max(0, end - n);
    const padL = 6, padR = 46, padT = 26, padB = 20, volH = 70, pw = W - padL - padR, ph = Hh - padT - padB - volH - 8;
    const trs = cur.trs.map((t) => ({ ...t, a: bars.findIndex((b) => b[0] >= t.from), z: bars.findIndex((b) => b[0] >= t.to) })).filter((t) => t.a >= 0);
    let lo = Infinity, hi = -Infinity;
    for (let i = start; i < end; i++) { lo = Math.min(lo, bars[i][L]); hi = Math.max(hi, bars[i][H]); }
    for (const t of trs) if (t.z < 0 || t.z >= start) { lo = Math.min(lo, t.lo); hi = Math.max(hi, t.hi); }
    const span = (hi - lo) || 1; lo -= span * .05; hi += span * .05;
    const bw = pw / n, x = (i) => padL + (i - start + .5) * bw, y = (v) => padT + (hi - v) / (hi - lo) * ph;
    const vTop = padT + ph + 8, vmax = Math.max(...bars.slice(start, end).map((b) => b[V])) || 1, vy = (v) => vTop + volH - v / vmax * volH;
    cur.layout = { start, end, bw, padL, x, y };
    ctx.clearRect(0, 0, W, Hh); ctx.fillStyle = "#FFFDF8"; ctx.fillRect(0, 0, W, Hh);
    // vùng đi ngang
    for (const t of trs) {
      const a = Math.max(t.a, start), z = t.z < 0 ? end - 1 : Math.min(t.z, end - 1);
      if (z < start || a > end - 1) continue;
      const x1 = x(a) - bw / 2, x2 = x(z) + bw / 2;
      ctx.fillStyle = t.kind === "dist" ? "rgba(201,139,139,.16)" : "rgba(217,179,106,.14)"; ctx.fillRect(x1, y(t.hi), x2 - x1, y(t.lo) - y(t.hi));
      ctx.strokeStyle = t.kind === "dist" ? "#B06A6A" : "#B8902F"; ctx.setLineDash([4, 3]); ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(x1, y(t.hi)); ctx.lineTo(t.open ? padL + pw : x2, y(t.hi)); ctx.moveTo(x1, y(t.lo)); ctx.lineTo(t.open ? padL + pw : x2, y(t.lo)); ctx.stroke(); ctx.setLineDash([]);
      ctx.font = "9px Archivo, Arial, sans-serif"; ctx.fillStyle = t.kind === "dist" ? "#8A4A4A" : "#8A6A2B"; ctx.textAlign = "right";
      ctx.fillText((t.kind === "dist" ? "BC " : "creek ") + px(t.hi), padL + pw - 2, y(t.hi) - 3); ctx.fillText((t.kind === "dist" ? "AR " : "ice ") + px(t.lo), padL + pw - 2, y(t.lo) + 10);
    }
    // lưới giá + tháng
    ctx.font = "10px Archivo, Arial, sans-serif"; ctx.fillStyle = "#6E6152"; ctx.strokeStyle = "#EBE3D2"; ctx.lineWidth = 1;
    for (let k = 0; k <= 4; k++) { const v = lo + (hi - lo) * k / 4, yy = Math.round(y(v)) + .5; ctx.beginPath(); ctx.moveTo(padL, yy); ctx.lineTo(padL + pw, yy); ctx.stroke(); ctx.textAlign = "left"; ctx.fillText(v.toFixed(2), padL + pw + 5, yy + 3); }
    let lastM = ""; ctx.textAlign = "center";
    for (let i = start; i < end; i++) { const ym = bars[i][0].slice(0, 7); if (ym !== lastM) { lastM = ym; const xx = Math.round(x(i)) + .5; ctx.strokeStyle = "#EBE3D2"; ctx.beginPath(); ctx.moveTo(xx, padT); ctx.lineTo(xx, vTop + volH); ctx.stroke(); ctx.fillStyle = "#6E6152"; const m = +ym.slice(5, 7); ctx.fillText(m === 1 ? ym.slice(0, 4) : "T" + m, xx, Hh - 6); } }
    // khối lượng: TB20 tính tại chỗ (20 nến trước)
    const cw = Math.max(1, bw * .66);
    for (let i = start; i < end; i++) {
      const w20 = bars.slice(Math.max(0, i - 20), i), av = w20.length ? w20.reduce((a, b) => a + b[V], 0) / w20.length : 0, vr = av ? bars[i][V] / av : 1;
      ctx.fillStyle = vr >= 1.5 ? "#B84A3A" : vr <= 0.7 ? "#2E7D4F" : "#C9BFA9";
      ctx.fillRect(x(i) - cw / 2, vy(bars[i][V]), cw, vTop + volH - vy(bars[i][V]));
    }
    ctx.strokeStyle = "#EBE3D2"; ctx.beginPath(); ctx.moveTo(padL, vTop - 4); ctx.lineTo(padL + pw, vTop - 4); ctx.stroke();
    // nến
    for (let i = start; i < end; i++) { const b = bars[i], col = b[C] >= b[O] ? "#2E7D4F" : "#B84A3A", xx = x(i); ctx.strokeStyle = col; ctx.fillStyle = b[C] >= b[O] ? "#FFFFFF" : col; ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(xx, y(b[H])); ctx.lineTo(xx, y(b[L])); ctx.stroke(); const yo = y(b[O]), yc = y(b[C]), top = Math.min(yo, yc), hh = Math.max(1, Math.abs(yo - yc)); if (cw >= 3) { ctx.fillRect(xx - cw / 2, top, cw, hh); ctx.strokeRect(xx - cw / 2, top, cw, hh); } else { ctx.beginPath(); ctx.moveTo(xx, top); ctx.lineTo(xx, top + hh); ctx.stroke(); } }
    // nhãn sự kiện
    const idx = new Map(bars.map((b, i) => [b[0], i]));
    ctx.font = "700 9px Archivo, Arial, sans-serif";
    for (const [d, id] of cur.marks) {
      const i = idx.get(d); if (i == null || i < start || i >= end) continue;
      const ev = (D && D.events[id]) || {}, below = ["sc", "st", "spring1", "spring2", "spring3", "test", "lps", "bu", "lpsy"].includes(id);
      const col = ev.direction === "buy" ? "#2E7D4F" : ev.direction === "exit" ? "#B84A3A" : "#8A7B66";
      const txt = ABBR[id] || id, tw = ctx.measureText(txt).width + 8, xx = x(i), yy = below ? y(bars[i][L]) + 6 : y(bars[i][H]) - 18;
      ctx.fillStyle = col; ctx.beginPath(); ctx.roundRect ? ctx.roundRect(xx - tw / 2, yy, tw, 12, 3) : ctx.rect(xx - tw / 2, yy, tw, 12); ctx.fill();
      ctx.fillStyle = "#fff"; ctx.textAlign = "center"; ctx.fillText(txt, xx, yy + 9);
    }
    if (cur.hover >= start && cur.hover < end) { const xx = Math.round(x(cur.hover)) + .5; ctx.strokeStyle = "#6E6152"; ctx.setLineDash([3, 3]); ctx.beginPath(); ctx.moveTo(xx, padT); ctx.lineTo(xx, vTop + volH); ctx.stroke(); ctx.setLineDash([]); }
    $("r-lab").textContent = `${dmy(bars[start][0])} → ${dmy(bars[end - 1][0])} · ${end - start} phiên`;
  }
  function renderTimeline() {
    const ev = D ? D.events : {};
    const xs = [...cur.marks].reverse().slice(0, 8);
    $("timeline").innerHTML = xs.length ? `<div class="lab">Dòng sự kiện gần nhất</div>` + xs.map(([d, id]) => { const m = ev[id] || {}; const cls = m.direction === "buy" ? "g" : m.direction === "exit" ? "r" : ""; return `<div class="it"><span class="d">${dmy(d)}</span><span class="tlt ${cls}">${ABBR[id] || id}</span><span class="x"><b>${esc(m.name || id)}</b> — ${esc(m.hint || "")}</span></div>`; }).join("") : `<div class="lab">Chưa có sự kiện nào trong 120 phiên.</div>`;
  }
  function onMove(cx, cy) {
    const Ly = cur.layout; if (!Ly || !cur.bars) return;
    const rect = cv.getBoundingClientRect(), p = cx - rect.left, i = Math.floor((p - Ly.padL) / Ly.bw) + Ly.start;
    if (i < Ly.start || i >= Ly.end) { cur.hover = -1; tip.style.display = "none"; draw(Ly.end - Ly.start); return; }
    cur.hover = i;
    const b = cur.bars[i], m = cur.marks.find((x) => x[0] === b[0]);
    tip.innerHTML = `<b>${dmy(b[0])}</b><br>M ${px(b[O])} · C ${px(b[H])} · T ${px(b[L])} · Đ <b>${px(b[C])}</b><br>KL ${(b[V] / 1e3).toFixed(0)}k` + (m ? `<br><b>${esc((D.events[m[1]] || {}).name || m[1])}</b>` : "");
    tip.style.display = "block";
    const tw = tip.offsetWidth, left = p + 12 + tw > rect.width ? p - tw - 12 : p + 12;
    tip.style.left = left + "px"; tip.style.top = Math.max(6, Math.min(cy - rect.top - 16, rect.height - tip.offsetHeight - 44)) + "px";
    draw(Ly.end - Ly.start);
  }
  cv.addEventListener("mousemove", (ev) => onMove(ev.clientX, ev.clientY));
  cv.addEventListener("mouseleave", () => { cur.hover = -1; tip.style.display = "none"; if (cur.layout && cur.bars) draw(cur.layout.end - cur.layout.start); });
  cv.addEventListener("touchstart", (ev) => { const t = ev.touches[0]; onMove(t.clientX, t.clientY); }, { passive: true });
  cv.addEventListener("touchmove", (ev) => { const t = ev.touches[0]; onMove(t.clientX, t.clientY); }, { passive: true });
  $("c-sym").addEventListener("change", () => { cur.sym = $("c-sym").value; cur.end = 0; renderChart(); });
  $("c-range").addEventListener("click", (ev) => { const b = ev.target.closest("button"); if (!b) return; cur.n = +b.dataset.n; cur.end = 0; [...$("c-range").children].forEach((x) => x.setAttribute("aria-pressed", x === b ? "true" : "false")); renderChart(); });
  $("r-off").addEventListener("input", (ev) => { if (!cur.bars) return; const total = cur.bars.length, n = Math.min(cur.n, total); cur.end = Math.min(total, +ev.target.value + n); draw(n); });
  window.addEventListener("resize", () => { if (cur.bars && $("p-chart").classList.contains("on")) renderChart(); });
  document.addEventListener("click", (ev) => { const el = ev.target.closest("[data-chart]"); if (!el) return; ev.preventDefault(); openChart(el.dataset.chart); });

  // ---------------------------------------------------------------- tab + boot
  const tabs = document.querySelectorAll('nav[role="tablist"] button');
  function switchTab(name) {
    tabs.forEach((x) => x.setAttribute("aria-selected", x.dataset.tab === name ? "true" : "false"));
    document.querySelectorAll(".panel").forEach((p) => p.classList.toggle("on", p.id === "p-" + name));
    $("main").scrollTop = 0;
    if (name === "chart") renderChart();
  }
  tabs.forEach((b) => b.addEventListener("click", () => switchTab(b.dataset.tab)));
  function applyHash() { const m = /^#(today|board|chart|history|settings)$/.exec(location.hash); if (m) switchTab(m[1]); }
  window.addEventListener("hashchange", applyHash);

  if ("serviceWorker" in navigator) navigator.serviceWorker.register(SW).catch(() => {});
  load().then(() => { applyHash(); pushStatus(); });
  document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible") load(); });
})();
