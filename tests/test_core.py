import unicodedata
from pathlib import Path

import pytest
from PIL import Image

from faxjob.layout import Paper, fit_center, paper_for_pdf_page
from faxjob.master import load_master
from faxjob.render import RenderOptions, render_image
from faxjob import scanner

MM = 72 / 25.4  # 1mm あたりの pt


def write_master(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "master.csv"
    p.write_text("ファイル名,用紙サイズ,印刷方向,有効\n" + body, encoding="utf-8-sig")
    return p


# ---- layout ----

@pytest.mark.parametrize("w,h,expected", [
    (210, 297, Paper("A4", "縦")),
    (297, 210, Paper("A4", "横")),
    (297, 420, Paper("A3", "縦")),
    (420, 297, Paper("A3", "横")),
    (215.9, 279.4, Paper("A3", "縦")),   # レター: 幅がA4を超えるのでA3
    (209.5, 296.5, Paper("A4", "縦")),   # 端数はA4扱い
    (100, 100, Paper("A4", "縦")),       # 正方形は縦
])
def test_paper_for_pdf_page(w, h, expected):
    paper, warn = paper_for_pdf_page(w * MM, h * MM)
    assert paper == expected and warn is None


def test_paper_for_oversize_page_warns():
    paper, warn = paper_for_pdf_page(600 * MM, 400 * MM)
    assert paper == Paper("A3", "横") and "縮小" in warn


def test_paper_px():
    assert Paper("A4", "縦").px(200) == (1654, 2339)
    assert Paper("A3", "横").px(200) == (3307, 2339)


def test_fit_center_keeps_aspect():
    p = fit_center(1000, 500, 800, 800)
    assert (p.w, p.h, p.x, p.y) == (800, 400, 0, 200)
    p = fit_center(100, 400, 1000, 1000)  # 拡大もする
    assert (p.w, p.h, p.x, p.y) == (250, 1000, 375, 0)


# ---- master ----

def test_master_validation(tmp_path):
    m = load_master(write_master(tmp_path,
        "請求書,A4,縦,1\n月次報告,a3,横,1\n悪い用紙,B4,縦,1\n悪い向き,A4,ななめ,1\n"
        "請求書,A3,横,1\n停止,A4,縦,0\n,A4,縦,1\n"))
    assert set(m.entries) == {"請求書", "月次報告"}
    assert m.entries["月次報告"].paper == Paper("A3", "横")
    assert m.entries["請求書"].paper == Paper("A4", "縦")  # 重複は先勝ち
    assert len(m.problems) == 4


def test_master_lookup_is_exact_and_nfc(tmp_path):
    m = load_master(write_master(tmp_path, "ガイド,A4,縦,1\n"))
    nfd = unicodedata.normalize("NFD", "ガイド")
    assert m.lookup(nfd) is not None          # macOS等の濁点分解形でも一致
    assert m.lookup("ガイド_控え") is None
    assert m.lookup("ガイド ") is None


# ---- scanner ----

def touch(folder: Path, *names: str):
    for n in names:
        (folder / n).write_bytes(b"x")


def by_name(results):
    return {c.path.name: c for c in results}


def test_scan_extension_and_master(tmp_path):
    src = tmp_path / "in"; src.mkdir()
    touch(src, "請求書.PDF", "請求書_控え.pdf", "メモ.docx", "月次報告.Jpeg")
    m = load_master(write_master(tmp_path, "請求書,A4,縦,1\n月次報告,A3,横,1\n"))
    r = by_name(scanner.scan(src, m))
    assert r["請求書.PDF"].status == scanner.SEND and r["請求書.PDF"].kind == "PDF"
    assert r["月次報告.Jpeg"].status == scanner.SEND and r["月次報告.Jpeg"].kind == "JPEG"
    assert r["請求書_控え.pdf"].status == scanner.SKIP_UNREGISTERED
    assert r["メモ.docx"].status == scanner.SKIP_EXT
    assert len(r["請求書.PDF"].sha256) == 64


def test_scan_same_stem_prefers_pdf_then_jpeg(tmp_path):
    src = tmp_path / "in"; src.mkdir()
    touch(src, "a.pdf", "a.png", "a.jpg", "b.png", "b.jpeg")
    m = load_master(write_master(tmp_path, "a,A4,縦,1\nb,A4,縦,1\n"))
    r = by_name(scanner.scan(src, m))
    assert r["a.pdf"].will_send
    assert r["a.png"].status == r["a.jpg"].status == scanner.SKIP_DUPLICATE
    assert r["b.jpeg"].will_send and r["b.png"].status == scanner.SKIP_DUPLICATE


def test_scan_jpg_and_jpeg_conflict_sends_neither(tmp_path):
    src = tmp_path / "in"; src.mkdir()
    touch(src, "a.jpg", "a.jpeg", "a.png")
    m = load_master(write_master(tmp_path, "a,A4,縦,1\n"))
    r = by_name(scanner.scan(src, m))
    assert r["a.jpg"].status == r["a.jpeg"].status == scanner.SKIP_CONFLICT
    assert r["a.png"].status == scanner.SKIP_DUPLICATE


def test_scan_unstable_file_is_skipped(tmp_path, monkeypatch):
    src = tmp_path / "in"; src.mkdir()
    touch(src, "a.pdf")
    m = load_master(write_master(tmp_path, "a,A4,縦,1\n"))
    monkeypatch.setattr(scanner, "is_stable", lambda p, w: False)
    assert scanner.scan(src, m)[0].status == scanner.SKIP_UNSTABLE


# ---- render ----

def test_render_image_keeps_aspect_and_paper(tmp_path):
    p = tmp_path / "x.png"
    Image.new("RGB", (400, 200), "black").save(p)
    opt = RenderOptions(dpi=100, margin_mm=0)
    [page] = render_image(p, Paper("A4", "縦"), opt)
    assert page.image.mode == "1"
    assert page.image.size == Paper("A4", "縦").px(100)
    bbox = page.image.point(lambda v: 255 - v).getbbox()  # 黒い部分の範囲
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    assert abs(w / h - 2.0) < 0.02                 # 縦横比 2:1 を保つ
    assert any("横長" in n for n in page.notes)     # 向き不一致の注意
