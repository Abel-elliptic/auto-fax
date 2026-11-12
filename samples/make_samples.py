"""デモ用のテストデータを作る。

  python samples/make_samples.py [出力先フォルダ]

既定では samples/送信 に、判定パターンを一通り含むファイルを作る。
必要: reportlab, Pillow, pypdfium2（PDFの回転設定に使用）
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import A3, A4, landscape
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas

pdfmetrics.registerFont(UnicodeCIDFont("HeiseiKakuGo-W5"))
FONT = "HeiseiKakuGo-W5"


def _page(c: canvas.Canvas, title: str, lines: list[str]) -> None:
    w, h = c._pagesize
    c.setLineWidth(2)
    c.rect(20, 20, w - 40, h - 40)  # 端までの枠：縮小・余白の確認用
    c.setFont(FONT, 28)
    c.drawString(50, h - 80, title)
    c.setFont(FONT, 14)
    y = h - 120
    for line in lines:
        c.drawString(50, y, line)
        y -= 22
    c.setFont(FONT, 10)
    c.drawString(50, 40, f"ページ寸法 {w / 72 * 25.4:.0f}×{h / 72 * 25.4:.0f}mm  ↑上")
    # 表（罫線の見え方確認用）
    top = y - 20
    for r in range(8):
        for col in range(5):
            c.rect(50 + col * 90, top - r * 24, 90, 24)
    c.showPage()


def make_pdf(path: Path, pages: list[tuple[tuple[float, float], str, list[str]]]) -> None:
    c = canvas.Canvas(str(path))
    for size, title, lines in pages:
        c.setPageSize(size)
        _page(c, title, lines)
    c.save()


def rotate_page(path: Path, index: int, degrees: int) -> None:
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(str(path))
    doc[index].set_rotation(degrees)
    tmp = path.with_suffix(".tmp")
    doc.save(str(tmp))
    doc.close()
    tmp.replace(path)


def make_image(path: Path, size: tuple[int, int], title: str, transparent: bool = False) -> None:
    mode = "RGBA" if transparent else "RGB"
    img = Image.new(mode, size, (0, 0, 0, 0) if transparent else (255, 255, 255))
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("NotoSansCJK-Regular.ttc", size[0] // 20)
    except OSError:
        font = ImageFont.load_default(size=size[0] // 20)
    d.rectangle([10, 10, size[0] - 11, size[1] - 11], outline=(0, 0, 0, 255), width=6)
    d.text((40, 40), title, fill=(0, 0, 0, 255), font=font)
    for i in range(12):  # グラデーション（写真モード比較用）
        g = int(255 * i / 11)
        x0 = 40 + i * (size[0] - 80) // 12
        d.rectangle([x0, size[1] // 2, x0 + (size[0] - 80) // 12, size[1] // 2 + 80], fill=(g, g, g, 255))
    img.save(path)


def main(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for p in out.iterdir():
        if p.is_file():
            p.unlink()

    make_pdf(out / "請求書.pdf", [
        (A4, "請求書 1/2", ["A4縦・2ページのPDF", "マスタ: A4 縦"]),
        (A4, "請求書 2/2", ["2ページ目"]),
    ])
    make_image(out / "請求書.png", (1240, 1754), "請求書(PNG) ← PDFを優先するので送らない")

    make_pdf(out / "月次報告.pdf", [
        (landscape(A3), "月次報告 1/2", ["A3横のPDF", "マスタ: A3 横"]),
        (A3, "月次報告 2/2", ["A3縦で作り /Rotate 90 を設定", "→ 見た目は横向き"]),
    ])
    rotate_page(out / "月次報告.pdf", 1, 90)

    make_pdf(out / "売上明細.PDF", [
        (A4, "売上明細", ["拡張子が大文字(.PDF)", "マスタは A4 横 だが PDF は A4 縦", "→ PDFに合わせて縦で出す（警告表示）"]),
    ])

    make_image(out / "配置図.jpg", (2480, 3508), "配置図(JPEG) マスタ: A3 縦")

    make_pdf(out / "混在サンプル.pdf", [
        (A4, "混在 1/3", ["A4縦"]),
        (landscape(A4), "混在 2/3", ["A4横"]),
        ((72 * 400 / 25.4, 72 * 600 / 25.4), "混在 3/3", ["400×600mm（A3より大きい）", "→ A3に縮小"]),
    ])
    make_image(out / "ロゴ.png", (900, 600), "透過PNG", transparent=True)

    make_pdf(out / "請求書_控え.pdf", [(A4, "請求書_控え", ["マスタ未登録 → 送らない"])])
    (out / "メモ.docx").write_bytes(b"dummy")
    (out / "readme.txt").write_text("対象外の拡張子", encoding="utf-8")
    print(f"サンプルを作成しました: {out}")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "送信")
