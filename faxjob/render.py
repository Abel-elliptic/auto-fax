"""PDF・画像を、FAX用のモノクロページ画像（A4/A3・縦横）に変換する。

送信はしない。ここで作った画像を、後の工程でFAXドライバーへ出力する想定。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageOps

from .layout import MM_PER_INCH, PT_PER_INCH, Paper, fit_center, paper_for_pdf_page, pt_to_mm


@dataclass
class RenderOptions:
    dpi: int = 200
    margin_mm: float = 5.0
    mono_mode: str = "text"       # "text"=しきい値で二値化 / "photo"=誤差拡散ディザ
    threshold: int = 160          # text モードのしきい値 (0-255)
    pdf_layout: str = "auto"      # "auto"=PDFのページに合わせる / "master"=マスタに合わせる


@dataclass
class RenderedPage:
    number: int
    paper: Paper
    image: Image.Image            # mode "1"（白黒）
    source_desc: str              # 元ページの寸法など
    scale_desc: str               # 拡大縮小率
    notes: list[str] = field(default_factory=list)


def _box_px(paper: Paper, opt: RenderOptions) -> tuple[int, int, int, int]:
    pw, ph = paper.px(opt.dpi)
    m = round(opt.margin_mm / MM_PER_INCH * opt.dpi)
    return pw, ph, pw - 2 * m, ph - 2 * m


def _to_mono(img: Image.Image, opt: RenderOptions) -> Image.Image:
    gray = img.convert("L")
    if opt.mono_mode == "photo":
        return gray.convert("1")  # Pillow 既定は Floyd–Steinberg ディザ
    t = opt.threshold
    return gray.point(lambda v: 255 if v >= t else 0, mode="1")


def _compose(content: Image.Image, paper: Paper, opt: RenderOptions, x: int, y: int) -> Image.Image:
    pw, ph, bw, _ = _box_px(paper, opt)
    m = (pw - bw) // 2
    canvas = Image.new("L", (pw, ph), 255)
    canvas.paste(content.convert("L"), (m + x, m + y))
    return _to_mono(canvas, opt)


def render_pdf(path: Path, master_paper: Paper, opt: RenderOptions) -> list[RenderedPage]:
    import pypdfium2 as pdfium

    pages: list[RenderedPage] = []
    doc = pdfium.PdfDocument(str(path))
    try:
        for i in range(len(doc)):
            page = doc[i]
            w_pt, h_pt = page.get_size()  # /Rotate 反映後の見た目の寸法
            rotation = page.get_rotation()
            notes: list[str] = []
            auto_paper, warn = paper_for_pdf_page(w_pt, h_pt)
            if warn:
                notes.append(warn)
            if opt.pdf_layout == "master":
                paper = master_paper
                if auto_paper != master_paper:
                    notes.append(f"PDFのページは {auto_paper.label()} 相当だが、マスタ設定 {master_paper.label()} で出力")
            else:
                paper = auto_paper
                if auto_paper != master_paper:
                    notes.append(f"マスタ設定は {master_paper.label()} だが、PDFのページに合わせて {auto_paper.label()} で出力")
            _, _, bw, bh = _box_px(paper, opt)
            # 1pt あたりのピクセル数を直接決めて描画する（再サンプリングを避ける）
            scale = min(bw / w_pt, bh / h_pt)
            bitmap = page.render(scale=scale, grayscale=True, fill_color=(255, 255, 255, 255))
            img = bitmap.to_pil()
            page.close()
            place = fit_center(img.width, img.height, bw, bh)
            real_ratio = scale / (opt.dpi / PT_PER_INCH)
            pages.append(RenderedPage(
                number=i + 1,
                paper=paper,
                image=_compose(img, paper, opt, place.x, place.y),
                source_desc=f"{pt_to_mm(w_pt):.0f}×{pt_to_mm(h_pt):.0f}mm" + (f"（回転{rotation}°）" if rotation else ""),
                scale_desc=f"原寸比 {real_ratio * 100:.0f}%",
                notes=notes,
            ))
    finally:
        doc.close()
    return pages


def render_image(path: Path, master_paper: Paper, opt: RenderOptions) -> list[RenderedPage]:
    notes: list[str] = []
    with Image.open(path) as src:
        img = ImageOps.exif_transpose(src)
        if img.mode in ("RGBA", "LA", "P"):
            rgba = img.convert("RGBA")
            bg = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
            img = Image.alpha_composite(bg, rgba)
            if src.mode != "P" or "transparency" in src.info:
                notes.append("透過部分は白として扱った")
        img = img.convert("L")
    paper = master_paper
    src_landscape = img.width > img.height
    if src_landscape != (paper.orientation == "横") and img.width != img.height:
        notes.append(f"画像は{'横長' if src_landscape else '縦長'}だが、マスタ設定 {paper.label()} で出力（回転しない）")
    _, _, bw, bh = _box_px(paper, opt)
    place = fit_center(img.width, img.height, bw, bh)
    resized = img.resize((place.w, place.h), Image.LANCZOS)
    return [RenderedPage(
        number=1,
        paper=paper,
        image=_compose(resized, paper, opt, place.x, place.y),
        source_desc=f"{img.width}×{img.height}px",
        scale_desc=f"画素倍率 {place.scale * 100:.0f}%",
        notes=notes,
    )]


def render_file(path: Path, kind: str, master_paper: Paper, opt: RenderOptions) -> list[RenderedPage]:
    if kind == "PDF":
        return render_pdf(path, master_paper, opt)
    return render_image(path, master_paper, opt)
