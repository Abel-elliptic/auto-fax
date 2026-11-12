"""用紙サイズ・向き・拡大縮小の計算（OSに依存しない純粋な計算のみ）。"""
from __future__ import annotations

from dataclasses import dataclass

MM_PER_INCH = 25.4
PT_PER_INCH = 72.0

# 縦向きの寸法 (幅mm, 高さmm)。JIS/ISO A列。
PAPER_MM = {
    "A4": (210.0, 297.0),
    "A3": (297.0, 420.0),
}
ORIENTATIONS = ("縦", "横")

# 実寸の誤差（PDF作成ソフトによる端数）を吸収する許容量
SIZE_TOLERANCE_MM = 2.0


@dataclass(frozen=True)
class Paper:
    size: str          # "A4" | "A3"
    orientation: str   # "縦" | "横"

    @property
    def mm(self) -> tuple[float, float]:
        w, h = PAPER_MM[self.size]
        return (h, w) if self.orientation == "横" else (w, h)

    def px(self, dpi: int) -> tuple[int, int]:
        w, h = self.mm
        return (round(w / MM_PER_INCH * dpi), round(h / MM_PER_INCH * dpi))

    def label(self) -> str:
        return f"{self.size} {self.orientation}"


def pt_to_mm(pt: float) -> float:
    return pt / PT_PER_INCH * MM_PER_INCH


def paper_for_pdf_page(width_pt: float, height_pt: float) -> tuple[Paper, str | None]:
    """PDFページの見た目の寸法（回転反映後）から用紙を決める。

    - 横長なら「横」、それ以外は「縦」
    - A4に収まればA4、A3に収まればA3、それより大きければA3（縮小）
    戻り値の2番目は注意メッセージ（無ければ None）。
    """
    w_mm, h_mm = pt_to_mm(width_pt), pt_to_mm(height_pt)
    orientation = "横" if w_mm > h_mm else "縦"
    short, long_ = sorted((w_mm, h_mm))
    tol = SIZE_TOLERANCE_MM
    a4s, a4l = PAPER_MM["A4"]
    a3s, a3l = PAPER_MM["A3"]
    if short <= a4s + tol and long_ <= a4l + tol:
        return Paper("A4", orientation), None
    if short <= a3s + tol and long_ <= a3l + tol:
        return Paper("A3", orientation), None
    return Paper("A3", orientation), f"ページがA3より大きい ({w_mm:.0f}×{h_mm:.0f}mm) ためA3に縮小"


@dataclass(frozen=True)
class Placement:
    scale: float   # 元画像ピクセル → 出力ピクセルの倍率
    x: int
    y: int
    w: int
    h: int


def fit_center(src_w: int, src_h: int, box_w: int, box_h: int) -> Placement:
    """縦横比を保ったまま枠に収まる最大倍率で中央配置する。"""
    if min(src_w, src_h, box_w, box_h) <= 0:
        raise ValueError("寸法は正の値である必要があります")
    scale = min(box_w / src_w, box_h / src_h)
    w = max(1, round(src_w * scale))
    h = max(1, round(src_h * scale))
    return Placement(scale, (box_w - w) // 2, (box_h - h) // 2, w, h)
