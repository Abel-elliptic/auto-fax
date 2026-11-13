"""ページ画像をWindowsのプリンターへ出力する（Step 2: まず「Microsoft Print to PDF」で確認）。

ページごとに用紙（A4/A3）と向きをプリンターに指定し、白黒ページ画像を用紙いっぱい（実寸）に描く。
FAXドライバーへの出力は、テスト宛先が決まるまで既定で拒否する（--allow-fax が必要）。

Windows専用の部分（pywin32）は関数の中で import するので、Linuxでもこのモジュールの
純粋な計算部分（テスト対象）は読み込める。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .layout import MM_PER_INCH, Paper
from .render import RenderedPage

# Windows の DEVMODE 定数（wingdi.h）
DMPAPER = {"A4": 9, "A3": 8}
DMORIENT = {"縦": 1, "横": 2}
DM_ORIENTATION = 0x00000001
DM_PAPERSIZE = 0x00000002
DM_IN_BUFFER = 8
DM_OUT_BUFFER = 2
# GetDeviceCaps の項目（wingdi.h）
LOGPIXELSX, LOGPIXELSY = 88, 90
PHYSICALWIDTH, PHYSICALHEIGHT = 110, 111
PHYSICALOFFSETX, PHYSICALOFFSETY = 112, 113

FAX_PATTERN = re.compile(r"fax|ファクス|ファックス|art ex", re.IGNORECASE)


def looks_like_fax(printer_name: str, driver_name: str) -> bool:
    return bool(FAX_PATTERN.search(printer_name) or FAX_PATTERN.search(driver_name))


@dataclass(frozen=True)
class DeviceGeometry:
    """プリンターが実際に用意した用紙の情報（デバイス座標）。"""
    dpi_x: int
    dpi_y: int
    phys_w: int
    phys_h: int
    off_x: int
    off_y: int

    @property
    def mm(self) -> tuple[float, float]:
        return (self.phys_w / self.dpi_x * MM_PER_INCH, self.phys_h / self.dpi_y * MM_PER_INCH)

    @property
    def unprintable_mm(self) -> tuple[float, float]:
        return (self.off_x / self.dpi_x * MM_PER_INCH, self.off_y / self.dpi_y * MM_PER_INCH)


def dest_rect(geom: DeviceGeometry) -> tuple[int, int, int, int]:
    """ページ画像（用紙全体を表す）を描く位置。印刷可能領域の原点は物理的な用紙の端から off だけずれている。"""
    return (-geom.off_x, -geom.off_y, geom.phys_w - geom.off_x, geom.phys_h - geom.off_y)


def check_geometry(paper: Paper, geom: DeviceGeometry, margin_mm: float, tol_mm: float = 3.0) -> list[str]:
    """要求した用紙とプリンターが用意した用紙を比べ、問題を日本語で返す。"""
    problems = []
    want_w, want_h = paper.mm
    got_w, got_h = geom.mm
    if (want_w > want_h) != (got_w > got_h) and abs(got_w - got_h) > tol_mm:
        problems.append(f"向きが反映されていない（要求 {paper.label()}、実際 {got_w:.0f}×{got_h:.0f}mm）")
    elif abs(want_w - got_w) > tol_mm or abs(want_h - got_h) > tol_mm:
        problems.append(f"用紙サイズが違う（要求 {paper.label()} {want_w:.0f}×{want_h:.0f}mm、実際 {got_w:.0f}×{got_h:.0f}mm）")
    ux, uy = geom.unprintable_mm
    if max(ux, uy) > margin_mm:
        problems.append(f"プリンターの印刷できない端（{ux:.1f}/{uy:.1f}mm）が余白 {margin_mm:g}mm より広く、端が欠ける可能性")
    return problems


@dataclass
class PageResult:
    number: int
    paper: Paper
    device_mm: tuple[float, float]
    unprintable_mm: tuple[float, float]
    problems: list[str] = field(default_factory=list)


class PrinterError(RuntimeError):
    pass


def printer_driver_name(printer: str) -> str:
    import win32print

    h = win32print.OpenPrinter(printer)
    try:
        return win32print.GetPrinter(h, 2)["pDriverName"]
    finally:
        win32print.ClosePrinter(h)


def _devmode_for(printer: str, paper: Paper):
    import win32print

    h = win32print.OpenPrinter(printer)
    try:
        dm = win32print.GetPrinter(h, 2)["pDevMode"]
        if dm is None:
            raise PrinterError(f"プリンター「{printer}」の設定（DEVMODE）を取得できません")
        dm.PaperSize = DMPAPER[paper.size]
        dm.Orientation = DMORIENT[paper.orientation]
        dm.Fields = dm.Fields | DM_PAPERSIZE | DM_ORIENTATION
        # ドライバーに設定を検証・反映させる
        win32print.DocumentProperties(0, h, printer, dm, dm, DM_IN_BUFFER | DM_OUT_BUFFER)
        return dm
    finally:
        win32print.ClosePrinter(h)


def _geometry(hdc) -> DeviceGeometry:
    import win32print

    cap = lambda i: win32print.GetDeviceCaps(hdc, i)
    return DeviceGeometry(cap(LOGPIXELSX), cap(LOGPIXELSY), cap(PHYSICALWIDTH), cap(PHYSICALHEIGHT),
                          cap(PHYSICALOFFSETX), cap(PHYSICALOFFSETY))


def print_pages(printer: str, pages: list[RenderedPage], doc_name: str,
                margin_mm: float, output_file: Path | None = None) -> list[PageResult]:
    """1ファイル分のページを1つの印刷ジョブとして出力する。

    output_file を指定すると、出力先をファイルにする（Microsoft Print to PDF で保存ダイアログを出さないため）。
    """
    import win32gui
    import win32print
    from PIL import ImageWin

    if not pages:
        return []
    results: list[PageResult] = []
    current = pages[0].paper
    hdc = win32gui.CreateDC("WINSPOOL", printer, _devmode_for(printer, current))
    if not hdc:
        raise PrinterError(f"プリンター「{printer}」を開けません")
    try:
        win32print.StartDoc(hdc, (doc_name, str(output_file) if output_file else None, None, 0))
        try:
            for page in pages:
                if page.paper != current:
                    current = page.paper
                    win32gui.ResetDC(hdc, _devmode_for(printer, current))
                win32print.StartPage(hdc)
                geom = _geometry(hdc)
                ImageWin.Dib(page.image.convert("L")).draw(hdc, dest_rect(geom))
                win32print.EndPage(hdc)
                results.append(PageResult(page.number, page.paper, geom.mm, geom.unprintable_mm,
                                          check_geometry(page.paper, geom, margin_mm)))
        except BaseException:
            win32print.AbortDoc(hdc)
            raise
        win32print.EndDoc(hdc)
    finally:
        win32gui.DeleteDC(hdc)
    return results
