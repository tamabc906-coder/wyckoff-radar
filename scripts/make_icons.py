r"""Vẽ PNG icon PWA từ toạ độ logo (docs/icons/logo.svg) — không cần cairosvg. Chép khuôn price-path.
Chạy: venv\Scripts\python -m scripts.make_icons   (cần Pillow, chỉ dùng trên máy dev; Actions không gọi).

Logo: chữ W vàng cát (đường gấp khúc 4 đoạn, nét tròn) trên nền nâu đất, dưới chân là 4 cột khối lượng
cao thấp khác nhau — "đọc dấu chân qua khối lượng". Nâu để khác candle-radar (xanh rêu), price-path (tím),
Candle Watch trên màn hình điện thoại. Toạ độ trong hệ 120×120 khớp logo.svg.
"""
from pathlib import Path

from PIL import Image, ImageDraw

BROWN, GOLD, CREAM = (0x5A, 0x3E, 0x2B), (0xD9, 0xB3, 0x6A), (0xF4, 0xEF, 0xE4)
OUT = Path(__file__).resolve().parent.parent / "docs" / "icons"

# Chữ W: 5 đỉnh trong hệ 120×120 (khớp logo.svg). Cột KL: (x, y_top, w, h).
W_POINTS = [(20, 30), (37, 80), (60, 45), (83, 80), (100, 30)]
BARS = [(24, 92, 12, 10), (44, 86, 12, 16), (64, 95, 12, 7), (84, 82, 12, 20)]
STROKE = 11


def draw(size: int, maskable: bool) -> Image.Image:
    # Vẽ ở 4× rồi thu nhỏ để nét mượt. Maskable: nền phủ kín, hình thu vào vùng an toàn 80 %.
    S = size * 4
    img = Image.new("RGBA", (S, S), BROWN if maskable else (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if not maskable:
        d.rounded_rectangle((0, 0, S - 1, S - 1), radius=int(S * 28 / 120), fill=BROWN)
    k = (S * 0.8 / 120) if maskable else (S / 120)
    off = (S - 120 * k) / 2

    def P(x, y):
        return (off + x * k, off + y * k)

    pts = [P(x, y) for x, y in W_POINTS]
    w = STROKE * k
    d.line(pts, fill=GOLD, width=int(w), joint="curve")
    for x, y in pts:  # đầu nét tròn
        d.ellipse((x - w / 2, y - w / 2, x + w / 2, y + w / 2), fill=GOLD)
    for x, y, bw, bh in BARS:
        x1, y1 = P(x, y)
        x2, y2 = P(x + bw, y + bh)
        d.rounded_rectangle((x1, y1, x2, y2), radius=int(2 * k), fill=GOLD)
    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    draw(192, False).save(OUT / "icon-192.png")
    draw(512, False).save(OUT / "icon-512.png")
    draw(512, True).convert("RGB").save(OUT / "icon-maskable.png")
    draw(48, False).save(OUT / "preview-48.png")
    print("wrote icon-192.png, icon-512.png, icon-maskable.png, preview-48.png ->", OUT)


if __name__ == "__main__":
    main()
