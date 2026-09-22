# Wyckoff Radar

App cảnh báo điểm **MUA / THOÁT** theo phương pháp Wyckoff trên nến ngày cho 39 mã (danh mục KingStock),
chạy sau phiên trên GitHub Actions, giao diện PWA tĩnh trên GitHub Pages, báo tới điện thoại bằng Web Push.
Không máy chủ. Khuôn kỹ thuật chép từ `price-path`; lõi tín hiệu viết mới.

Kế hoạch duyệt 21/09/2026: `C:\Users\IT\.claude\plans\b-n-l-1-trader-abstract-fountain.md`.
Thiết kế giao diện: https://claude.ai/artifact/Kv3gudduQb4R8YR1Jk8A63

## Nguyên tắc

- **Đo trước, bật sau.** Mọi sự kiện Wyckoff được đo trên kho nến 11 năm (`scripts/measure.py`) so với mốc
  "mua đại rồi giữ", tách theo năm. Chỉ sự kiện đạt ★ mới push mặc định; sự kiện đo kém vẫn gắn nhãn trên
  Bảng/Biểu đồ và có công tắc bật tay (thẻ mang dòng cảnh báo).
- VN không bán khống → nhánh phân phối (BC/UT/UTAD/SOW/LPSY) chỉ là cảnh báo **THOÁT / không mua đuổi**.
- Chỉ nến đã chốt ATC. Giá DNSE là giá điều chỉnh, đơn vị nghìn đồng.

## Lộ trình

| GĐ | Việc | Trạng thái |
|---|---|---|
| G0 | Khung: common/, job/push+watchlist+settings, workflow, docs khung, venv, kho nến, icon | ✅ 21/09/2026 |
| G1 | `job/wyckoff.py` — máy trạng thái vùng đi ngang + 15 sự kiện; `tests/test_wyckoff.py`; `scripts/inspect.py` soi mắt | ✅ 21/09/2026 |
| G2 | `scripts/measure.py` — đo 11 năm → `reports/measure-2026-09-21.md`, `docs/data/stats.json`; chốt `events_disabled` | ✅ 21/09/2026 |
| G3 | `job/run_daily.py`, `scripts/replay.py` (30 phiên lịch sử), `latest.json`/`bars.json`/`daily/` | ✅ 21/09/2026 |
| G4 | `docs/` 5 tab theo thiết kế (Hôm nay · Bảng · Biểu đồ · Lịch sử · Cài đặt); `scripts/shot.py` chụp headless → `reports/shots/` | ✅ 22/09/2026 |
| G5 | Lên GitHub `tamabc906-coder/wyckoff-radar`, Pages `/docs`, 4 Secrets; điện thoại nhận "Đã kết nối" | ✅ 22/09/2026 — chạy thật từ phiên 22/09, cron 15:45 |

## Lõi Wyckoff (`job/wyckoff.py`) — điều đã chỉnh so với kế hoạch khi soi dữ liệu thật (21/09/2026)

- **SC không đòi "đóng cửa hồi khỏi đáy"**: điều kiện `close_pos ≥ 0,3` loại 259/295 ứng viên vì ngày cao trào ở VN
  thường đóng sát sàn, hôm sau mới bật. Bỏ → 212 SC/11 năm, đỉnh 2022 (47) và 2025 (38) đúng hai đợt sập; nhãn rơi
  đúng đáy HPG 10/11/2022, HPG 09/04/2025, FPT 08/04/2025. SC "hụt" (giá sập tiếp) vẫn phát tín hiệu — đo ở G2.
- **Vùng gốc "range"** (sơ đồ #2) phải có đợt giảm ≥ 10 % dẫn vào trong 40 phiên trước, biên độ ≥ 6 %, và tuổi tính
  từ lúc phát hiện (phải đi ngang thêm 20 phiên). Không có bối cảnh này thì 793 "spring2" toàn nhiễu.
- **Giai đoạn D giữ vùng** tới khi có LPS/LPSY hoặc 20 phiên sau SOS/SOW — nếu đóng vùng theo quy tắc 2 phiên thì
  không bao giờ thấy LPS (8 → 17 lần).
- SC dưới vùng đang có → ưu tiên SC (mở chu kỳ mới), không ghi SOW cùng nến. ST tối đa 3 lần/vùng, chỉ ở GĐ A/B.
- Soi: `venv\Scripts\python -m scripts.inspect HPG --from 2022-09-15 --to 2023-03-31`, `--count` để xem tần suất.

## Kết quả đo G2 (`reports/measure-2026-09-21.md`, 39 mã, 2016→2026, +10 phiên, mua-đại +0,57 %)

| Sự kiện | n | +10p | t | năm thắng | Kết luận |
|---|---:|---:|---:|---:|---|
| **SC** bán tháo cao trào | 244 | **+3,02 %** | 4,2 | 7/10 | ★ duy nhất — vững cả khi bỏ 2022 (+3,67 %) |
| Spring #3 / Test / LPS / BU | 10 / 55 / 16 / 30 | ≈ 0 … +2 % | < 1,3 | — | không hơn mua-đại; phá đáy vùng < 1 % rồi đóng lại là **rò rỉ** (−2,6 %, 0/8 năm) |
| SOS (vượt creek có KL) | 97 | −0,20 % | −0,2 | 5/11 | thua đối chứng "Trần+KL+phá đỉnh" (+1,69 %); nền ≥ 20 phiên không giúp |
| **SOW** phá đáy có KL | 73 | **−3,39 %** | −3,3 | 5/5 | thoát duy nhất có giá trị; thiếu 1 năm so tiêu chí ★ — bật tay nếu muốn |
| BC / UTAD / LPSY | 622 / 70 / 6 | +2,6 / +0,7 / +9 % | — | — | mẫu đỉnh là tiếp diễn tăng, không dùng |

Mặc định push: chỉ `sc`. Mọi sự kiện khác vẫn gắn nhãn trên Bảng/Biểu đồ. Tách nhóm: `scripts/split.py`.

## Chạy trên máy

```
install.bat                                   # venv + thư viện (một lần)
venv\Scripts\python -m pytest -q
venv\Scripts\python -m scripts.fetch_history  # làm mới kho data/history.json (đã chép sẵn từ price-path)
venv\Scripts\python -m scripts.measure --md   # G2
venv\Scripts\python -m job.run_daily --dry-run
```

## Cấu trúc

```
common/   config.py  dnse.py  store.py         nguồn DNSE + kho nến (chép price-path)
job/      watchlist.py  push.py  settings.py  gen_vapid.py   hạ tầng (chép)
          wyckoff.py  run_daily.py            lõi Wyckoff + job (G1, G3)
scripts/  measure.py  replay.py  fetch_history.py  make_icons.py
data/     history.json                        40 mã × ~2.700 nến từ 2015-10-08 (commit)
docs/     PWA + docs/data/{latest,bars,state,settings,watchlist}.json + daily/
```

## Cách dùng để mua/bán (theo số đã đo, không theo sách)

1. **Chỉ tin chuông SC.** +3,0 %/10p trung bình, đúng 62 %, ~2 tín hiệu/tháng. 4/10 lệnh lỗ → stop bắt buộc.
2. **Đọc thẻ**: KL/TB20 2–3× tốt nhất (≥ 3× mua nửa cỡ); đóng cửa < 20 % → chờ nến xanh AR; stop = đáy SC − 0,5×ATR.
3. **Mua** ATO/15 phút đầu phiên sau; rủi ro ≤ 1 % vốn: số CP = (1 % vốn) ÷ (giá − stop); ≤ 1/3 vị thế; ≤ 3 mã SC cùng lúc.
4. **Thoát** (cái nào đến trước): đóng cửa dưới stop → bán phiên sau; hết 10 phiên → bán hoặc giữ theo vùng nếu đã có
   AR/ST; SOW (nếu bật) → bán. Lãi 5–8 % ở AR → bán 1/3.
5. **Giữ theo vùng** (tab Bảng/Biểu đồ): ST KL thấp = tốt; đóng dưới đáy SC 3 % hai phiên = vùng thất bại → thoát;
   C/D chỉ giữ, không thêm vì Spring/SOS (đo ≈ mua-đại); E → stop nâng dần theo đáy nhịp lùi.
6. **Không bán vì BC/UT/UTAD** (đo ra giá còn tăng). Spring #2 trên mã đang giữ = cảnh báo rò rỉ, siết stop.
7. **Kiểm chứng** ở tab Lịch sử: TB +10p của SC phải > +0,57 % sau ~30 phiên; âm 3 tháng liền → đo lại, không nới ngưỡng.

## Đang chạy thật

Site: https://tamabc906-coder.github.io/wyckoff-radar/ · Actions: workflow `daily` 15:45 VN T2–T6 (+ 3 dự phòng) ·
Push: 1 máy Android qua Secret `PUSH_SUBS_FALLBACK`. Kiểm tra: GitHub API `actions/runs` + `data/state.json` trên
Pages (`last_trade_date` phải tăng mỗi phiên). Sửa giao diện → tăng `?v=` trong `index.html`, bảo điện thoại đóng
hẳn app. Bot commit `docs/data` mỗi ngày → luôn `git pull --ff-only origin main` trước khi push `master:main`.

## Đưa lên GitHub (G5) — đã làm

Repo public `tamabc906-coder/wyckoff-radar` → mời `deptlink2025-bctc` làm collaborator (máy này nhớ tài khoản
đó) → Settings → Pages: branch `main`, thư mục `/docs` → Secrets: `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`,
`VAPID_SUBJECT`, `PUSH_SUBS_FALLBACK` (WORKER_URL để trống) → dán VAPID public vào `docs/config.js` →
Actions → daily → Run workflow với `test_push=true`.
