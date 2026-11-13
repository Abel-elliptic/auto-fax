from faxjob.layout import Paper
from faxjob.printer_win import DeviceGeometry, check_geometry, dest_rect, looks_like_fax


def geom_mm(w_mm, h_mm, off_mm=0.0, dpi=600):
    px = lambda mm: round(mm / 25.4 * dpi)
    return DeviceGeometry(dpi, dpi, px(w_mm), px(h_mm), px(off_mm), px(off_mm))


def test_looks_like_fax():
    assert looks_like_fax("FUJIFILM Apeos C2360 FAX", "")
    assert looks_like_fax("事務所", "FUJIFILM ART EX Direct Fax Driver")
    assert looks_like_fax("ダイレクトファクス", "x")
    assert not looks_like_fax("Microsoft Print to PDF", "Microsoft Print To PDF")


def test_dest_rect_covers_physical_page():
    g = DeviceGeometry(600, 600, 4960, 7016, 100, 120)
    assert dest_rect(g) == (-100, -120, 4860, 6896)


def test_check_geometry_ok():
    assert check_geometry(Paper("A4", "縦"), geom_mm(210, 297, 4), margin_mm=5) == []
    assert check_geometry(Paper("A3", "横"), geom_mm(420, 297, 0), margin_mm=5) == []


def test_check_geometry_detects_orientation_size_and_edge():
    [msg] = check_geometry(Paper("A4", "横"), geom_mm(210, 297), margin_mm=5)
    assert "向き" in msg
    [msg] = check_geometry(Paper("A3", "縦"), geom_mm(210, 297), margin_mm=5)
    assert "用紙サイズ" in msg
    [msg] = check_geometry(Paper("A4", "縦"), geom_mm(210, 297, 6.5), margin_mm=5)
    assert "端が欠ける" in msg


def test_settings_print_section(tmp_path):
    from faxjob.config import load_settings
    p = tmp_path / "s.toml"
    p.write_text("[print]\nmode='test'\nprinter_name='X'\n", encoding="utf-8")
    s = load_settings(p)
    assert (s.mode, s.printer_name) == ("test", "X")
    p.write_text("[print]\nmode='prod'\n", encoding="utf-8")
    import pytest
    with pytest.raises(ValueError):
        load_settings(p)
    # 例の設定ファイルがそのまま読めること
    from pathlib import Path
    ex = load_settings(Path(__file__).parent.parent / "config" / "settings.example.toml")
    assert ex.mode == "demo" and ex.printer_name == "Microsoft Print to PDF"


def test_format_inspection():
    from faxjob.printer_win import Inspection, format_inspection
    ins = Inspection(
        printer="FUJIFILM Apeos C2360 FAX", driver="FF Direct Fax Driver", port="10.203.101.230",
        default_paper=9, default_orientation=1, default_quality="200×200dpi",
        papers=[(9, "A4", (2100, 2970)), (8, "A3", (2970, 4200)), (12, "B4", None)],
        resolutions=[(200, 100), (200, 200)], landscape_rotation=90,
        trials=[(Paper("A4", "縦"), 9, 1, ""), (Paper("A4", "横"), 9, 2, ""),
                (Paper("A3", "縦"), 8, 1, ""), (Paper("A3", "横"), 9, 2, "")],
    )
    text = "\n".join(format_inspection(ins))
    assert "FAXドライバー判定: はい" in text
    assert "A4: 対応" in text and "A3: 対応" in text
    assert "200×100、200×200" in text
    assert "A3 横: → 用紙 A4 / 向き 横  ← 指定どおりにならない" in text
    assert "要確認" in text.splitlines()[-1]


def test_format_inspection_missing_a3():
    from faxjob.printer_win import Inspection, format_inspection
    ins = Inspection("P", "D", "X", None, None, "不明", [(9, "A4", None)], [], None, [])
    text = "\n".join(format_inspection(ins))
    assert "A3: 一覧に無い（要確認）" in text and "既定の設定: 用紙 不明" in text


def test_pair_of_handles_pywin32_shapes():
    from faxjob.printer_win import pair_of
    assert pair_of({"x": 2100, "y": 2970}) == (2100, 2970)       # DC_PAPERSIZE
    assert pair_of({"xdpi": 200, "ydpi": 100}) == (200, 100)     # DC_ENUMRESOLUTIONS
    assert pair_of({"cx": 1, "cy": 2}) == (1, 2)
    assert pair_of((300, 300)) == (300, 300)
    assert pair_of({"h": 1}) is None and pair_of(None) is None


def test_fax_request_problems():
    from faxjob.printer_win import fax_request_problems
    assert fax_request_problems("請求書.pdf", 2, 3) == []
    assert fax_request_problems("請求書.pdf", None, 3) == []
    [msg] = fax_request_problems(None, 1, 3)
    assert "--only" in msg
    [msg] = fax_request_problems("a.pdf", 4, 3)
    assert "上限 3" in msg
    assert len(fax_request_problems("", 9, 3)) == 2


def test_format_printer_list():
    from faxjob.printer_win import format_printer_list
    lines = format_printer_list([("FUJIFILM Apeos C2360", "FF Apeos C2360"),
                                 ("FAX", "FF Direct Fax Driver"),
                                 ("Microsoft Print to PDF", "Microsoft Print To PDF")])
    assert "  * 名前: FAX  （ドライバー: FF Direct Fax Driver）" in lines
    assert "    名前: FUJIFILM Apeos C2360  （ドライバー: FF Apeos C2360）" in lines
