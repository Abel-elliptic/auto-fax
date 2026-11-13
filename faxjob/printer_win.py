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


CONFIRM_WORD = "送信"


def fax_request_problems(only: str | None, page_count: int | None, max_pages: int) -> list[str]:
    """FAXドライバーへ出力してよいかの事前チェック（テスト送信用の安全装置）。問題があれば日本語で返す。"""
    problems = []
    if not only:
        problems.append("FAXへ出力するときは --only で1ファイルだけ指定してください（例: --only 請求書.pdf）")
    if page_count is not None and page_count > max_pages:
        problems.append(f"ページ数 {page_count} が上限 {max_pages} を超えています（--max-pages で変更可）")
    return problems


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


def format_printer_list(printers: list[tuple[str, str]]) -> list[str]:
    """インストール済みプリンター（名前, ドライバー名）の一覧を、FAXドライバーに印を付けて行にする。"""
    lines = ["インストール済みのプリンター（* = FAXドライバー。--printer にはこの「名前」を指定）:"]
    for name, driver in sorted(printers):
        mark = "*" if looks_like_fax(name, driver) else " "
        lines.append(f"  {mark} 名前: {name}  （ドライバー: {driver}）")
    return lines


def list_printers() -> list[tuple[str, str]]:
    import win32print

    flags = 2 | 4  # PRINTER_ENUM_LOCAL | PRINTER_ENUM_CONNECTIONS
    return [(p["pPrinterName"], p["pDriverName"]) for p in win32print.EnumPrinters(flags, None, 2)]


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


# ---- 調査（inspect）: 印刷ジョブを作らずにドライバーの対応状況を読む ----

DC_PAPERS, DC_PAPERSIZE, DC_ENUMRESOLUTIONS, DC_PAPERNAMES, DC_ORIENTATION = 2, 3, 13, 16, 17
PAPER_CODE_NAMES = {8: "A3", 9: "A4", 11: "A5", 12: "B4", 13: "B5", 1: "Letter", 5: "Legal"}
ORIENT_NAMES = {1: "縦", 2: "横"}


@dataclass
class Inspection:
    printer: str
    driver: str
    port: str
    default_paper: int | None
    default_orientation: int | None
    default_quality: str
    papers: list[tuple[int, str, tuple[int, int] | None]]   # (コード, 名前, 寸法0.1mm)
    resolutions: list[tuple[int, int]]
    landscape_rotation: int | None
    trials: list[tuple[Paper, int | None, int | None, str]]  # 要求 → 受け入れ値(用紙コード, 向き), エラー


def pair_of(value) -> tuple[int, int] | None:
    """pywin32 が返す2つ組の値を (横, 縦) にする。

    pywin32 は用紙寸法を {"x":..,"y":..}、解像度を {"xdpi":..,"ydpi":..} の辞書で返す（版によって形が違う可能性もあるため幅広く受ける）。
    """
    if isinstance(value, dict):
        for kx, ky in (("x", "y"), ("xdpi", "ydpi"), ("cx", "cy")):
            if kx in value and ky in value:
                return (int(value[kx]), int(value[ky]))
        return None
    try:
        a, b = value
        return (int(a), int(b))
    except (TypeError, ValueError):
        return None


def format_inspection(ins: Inspection) -> list[str]:
    """調査結果を日本語の行にする（Windowsに依存しない部分。単体テスト対象）。"""
    pname = lambda c: PAPER_CODE_NAMES.get(c, f"コード{c}") if c is not None else "不明"
    lines = [
        f"プリンター: {ins.printer}",
        f"ドライバー: {ins.driver}",
        f"ポート    : {ins.port}",
        f"FAXドライバー判定: {'はい' if looks_like_fax(ins.printer, ins.driver) else 'いいえ'}",
        f"既定の設定: 用紙 {pname(ins.default_paper)} / 向き {ORIENT_NAMES.get(ins.default_orientation, '不明')} / 解像度 {ins.default_quality}",
        "",
        f"対応用紙（{len(ins.papers)}種類）:",
    ]
    for code, name, size in ins.papers:
        dims = f" {size[0] / 10:.0f}×{size[1] / 10:.0f}mm" if size else ""
        mark = "  ← 使用" if code in (8, 9) else ""
        lines.append(f"  [{code:>3}] {name}{dims}{mark}")
    codes = {p[0] for p in ins.papers}
    for code, label in ((9, "A4"), (8, "A3")):
        lines.append(f"{label}: {'対応' if code in codes else '一覧に無い（要確認）'}")
    res = "、".join(f"{x}×{y}" for x, y in ins.resolutions) or "取得できず"
    lines.append(f"対応解像度(dpi): {res}")
    rot = {0: "横向き非対応", 90: "対応（90°）", 270: "対応（270°）"}.get(ins.landscape_rotation, "不明")
    lines.append(f"横向き: {rot}")
    lines += ["", "用紙・向きの指定テスト（設定値をドライバーに渡して返ってきた値。印刷はしていない）:"]
    ok_all = True
    for paper, got_paper, got_orient, err in ins.trials:
        if err:
            lines.append(f"  {paper.label()}: エラー {err}")
            ok_all = False
            continue
        ok = got_paper == DMPAPER[paper.size] and got_orient == DMORIENT[paper.orientation]
        ok_all &= ok
        lines.append(f"  {paper.label()}: → 用紙 {pname(got_paper)} / 向き {ORIENT_NAMES.get(got_orient, '不明')}  {'OK' if ok else '← 指定どおりにならない'}")
    lines += ["", "判定: " + ("A4/A3・縦横の指定はドライバーに受け入れられた" if ok_all else "指定どおりにならない組み合わせがある（要確認）")]
    return lines


def inspect_printer(printer: str) -> Inspection:
    """印刷ジョブを作らずに、プリンタードライバーの設定と対応状況を読む。FAXは送信されない。"""
    import win32print

    h = win32print.OpenPrinter(printer)
    try:
        info = win32print.GetPrinter(h, 2)
    finally:
        win32print.ClosePrinter(h)
    port = info["pPortName"]
    dm = info["pDevMode"]

    def caps(cap):
        try:
            return win32print.DeviceCapabilities(printer, port, cap)
        except Exception:
            return None

    codes = list(caps(DC_PAPERS) or [])
    names = list(caps(DC_PAPERNAMES) or [])
    sizes = list(caps(DC_PAPERSIZE) or [])
    papers = []
    for i, code in enumerate(codes):
        name = str(names[i]).strip("\x00 ") if i < len(names) else ""
        size = pair_of(sizes[i]) if i < len(sizes) else None
        papers.append((int(code), name, size))
    resolutions = [r for r in (pair_of(v) for v in (caps(DC_ENUMRESOLUTIONS) or [])) if r]
    rot = caps(DC_ORIENTATION)

    quality = "不明"
    if dm is not None:
        q, y = getattr(dm, "PrintQuality", 0), getattr(dm, "YResolution", 0)
        quality = f"{q}×{y}dpi" if q > 0 else f"品質コード{q}"

    trials = []
    for paper in (Paper("A4", "縦"), Paper("A4", "横"), Paper("A3", "縦"), Paper("A3", "横")):
        try:
            got = _devmode_for(printer, paper)
            trials.append((paper, got.PaperSize, got.Orientation, ""))
        except Exception as exc:
            trials.append((paper, None, None, str(exc)))

    return Inspection(
        printer=printer, driver=info["pDriverName"], port=port,
        default_paper=getattr(dm, "PaperSize", None) if dm is not None else None,
        default_orientation=getattr(dm, "Orientation", None) if dm is not None else None,
        default_quality=quality, papers=papers, resolutions=resolutions,
        landscape_rotation=rot if isinstance(rot, int) else None, trials=trials,
    )
