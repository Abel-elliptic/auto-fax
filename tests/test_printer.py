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
