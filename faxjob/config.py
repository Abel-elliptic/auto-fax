"""settings.toml の読み込み。項目が無ければ既定値を使う。"""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .render import RenderOptions


@dataclass
class Settings:
    base_dir: Path = Path(r"C:\FAX")
    master_file: Path | None = None
    stable_wait_seconds: float = 3.0
    mode: str = "demo"               # demo / test / production
    printer_name: str = ""
    fax_test_number: str = "1860528244773"   # Brother FAXテストサービス（186=番号通知）
    fax_group_name: str = "一斉2"
    fax_dialog_timeout: float = 60.0
    render: RenderOptions = field(default_factory=RenderOptions)

    @property
    def send_dir(self) -> Path:
        return self.base_dir / "送信"

    @property
    def preview_dir(self) -> Path:
        return self.base_dir / "ログ" / "preview"

    @property
    def master_path(self) -> Path:
        return self.master_file or (self.base_dir / "設定" / "master.csv")


def load_settings(path: Path | None) -> Settings:
    s = Settings()
    if path is None:
        return s
    with open(path, "rb") as f:
        data = tomllib.load(f)
    folders = data.get("folders", {})
    if "base_dir" in folders:
        s.base_dir = Path(folders["base_dir"])
    if "master_file" in folders:
        mf = Path(folders["master_file"])
        s.master_file = mf if mf.is_absolute() else path.parent / mf
    scan = data.get("scan", {})
    s.stable_wait_seconds = float(scan.get("stable_wait_seconds", s.stable_wait_seconds))
    pr = data.get("print", {})
    s.mode = str(pr.get("mode", s.mode))
    s.printer_name = str(pr.get("printer_name", s.printer_name))
    if s.mode not in ("demo", "test", "production"):
        raise ValueError(f"print.mode は demo/test/production のどれか: {s.mode}")
    fx = data.get("fax", {})
    s.fax_test_number = str(fx.get("test_number", s.fax_test_number))
    s.fax_group_name = str(fx.get("group_name", s.fax_group_name))
    s.fax_dialog_timeout = float(fx.get("dialog_timeout", s.fax_dialog_timeout))
    r = data.get("render", {})
    opt = s.render
    opt.dpi = int(r.get("dpi", opt.dpi))
    opt.margin_mm = float(r.get("margin_mm", opt.margin_mm))
    opt.mono_mode = str(r.get("mono_mode", opt.mono_mode))
    opt.threshold = int(r.get("threshold", opt.threshold))
    opt.pdf_layout = str(r.get("pdf_layout", opt.pdf_layout))
    if opt.mono_mode not in ("text", "photo"):
        raise ValueError(f"render.mono_mode は text/photo のどちらか: {opt.mono_mode}")
    if opt.pdf_layout not in ("auto", "master"):
        raise ValueError(f"render.pdf_layout は auto/master のどちらか: {opt.pdf_layout}")
    if opt.dpi not in range(100, 601):
        raise ValueError(f"render.dpi は 100〜600: {opt.dpi}")
    return s
