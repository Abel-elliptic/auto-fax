"""ファイル名別 設定マスタ（CSV）の読み込みと検証。

CSV列: ファイル名,用紙サイズ,印刷方向,有効
Excelで編集できるよう UTF-8 (BOM付き可) を想定する。
"""
from __future__ import annotations

import csv
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from .layout import ORIENTATIONS, PAPER_MM, Paper

REQUIRED_COLUMNS = ("ファイル名", "用紙サイズ", "印刷方向")
FORBIDDEN_CHARS = set('\\/:*?"<>|')


def normalize_name(name: str) -> str:
    """照合用の正規化。NFC のみ行い、空白の除去や大小変換はしない（完全一致）。"""
    return unicodedata.normalize("NFC", name)


@dataclass(frozen=True)
class MasterEntry:
    name: str
    paper: Paper


@dataclass
class Master:
    entries: dict[str, MasterEntry]
    problems: list[str]

    def lookup(self, stem: str) -> MasterEntry | None:
        return self.entries.get(normalize_name(stem))


def load_master(path: Path) -> Master:
    entries: dict[str, MasterEntry] = {}
    problems: list[str] = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        missing = [c for c in REQUIRED_COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"マスタ {path} に必須列がありません: {', '.join(missing)}")
        for lineno, row in enumerate(reader, start=2):
            name = normalize_name(row.get("ファイル名") or "")
            size = (row.get("用紙サイズ") or "").strip().upper()
            orient = (row.get("印刷方向") or "").strip()
            enabled = (row.get("有効") or "1").strip()
            where = f"{path.name} {lineno}行目"
            if not name:
                problems.append(f"{where}: ファイル名が空のため無視")
                continue
            if name != name.strip():
                problems.append(f"{where}: 「{name}」の前後に空白があります（完全一致で照合するため注意）")
            if FORBIDDEN_CHARS & set(name):
                problems.append(f"{where}: 「{name}」にファイル名に使えない文字が含まれるため無視")
                continue
            if size not in PAPER_MM:
                problems.append(f"{where}: 用紙サイズ「{size}」は A4/A3 以外のため無視")
                continue
            if orient not in ORIENTATIONS:
                problems.append(f"{where}: 印刷方向「{orient}」は 縦/横 以外のため無視")
                continue
            if enabled not in ("1", "0"):
                problems.append(f"{where}: 有効「{enabled}」は 1/0 以外のため無視")
                continue
            if name in entries:
                problems.append(f"{where}: 「{name}」が重複しています。後の行は無視")
                continue
            if enabled == "0":
                continue
            entries[name] = MasterEntry(name, Paper(size, orient))
    return Master(entries, problems)
