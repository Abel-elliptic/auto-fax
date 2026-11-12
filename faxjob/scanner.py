"""送信フォルダの走査と、送信対象の判定（送信は行わない）。"""
from __future__ import annotations

import hashlib
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from .master import Master, MasterEntry, normalize_name

# 拡張子 → 種別。大文字小文字は区別しない。
KIND_BY_EXT = {".pdf": "PDF", ".jpg": "JPEG", ".jpeg": "JPEG", ".png": "PNG"}
# 同名で拡張子違いが並んだときの優先順位（小さいほど優先）
PRIORITY = {"PDF": 0, "JPEG": 1, "PNG": 2}

SEND = "送信対象"
SKIP_EXT = "対象外の拡張子"
SKIP_UNREGISTERED = "マスタ未登録"
SKIP_DUPLICATE = "同名重複のため未送信"
SKIP_CONFLICT = "同名重複（判断不能）"
SKIP_UNSTABLE = "ファイル変更中"


@dataclass
class Candidate:
    path: Path
    kind: str | None
    status: str
    reason: str = ""
    entry: MasterEntry | None = None
    sha256: str = ""
    notes: list[str] = field(default_factory=list)

    @property
    def will_send(self) -> bool:
        return self.status == SEND


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def is_stable(path: Path, wait_seconds: float) -> bool:
    """一定時間おいてサイズと更新時刻が変わらなければ安定とみなす。"""
    try:
        before = path.stat()
        if wait_seconds > 0:
            time.sleep(wait_seconds)
        after = path.stat()
        with open(path, "rb"):
            pass
    except OSError:
        return False
    return (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns)


def scan(folder: Path, master: Master, stable_wait: float = 0.0) -> list[Candidate]:
    files = sorted(p for p in folder.iterdir() if p.is_file() and not p.name.startswith("."))
    results: list[Candidate] = []
    by_stem: dict[str, list[Candidate]] = defaultdict(list)

    for p in files:
        kind = KIND_BY_EXT.get(p.suffix.lower())
        if kind is None:
            results.append(Candidate(p, None, SKIP_EXT, f"拡張子「{p.suffix or '(なし)'}」は送信しない"))
            continue
        entry = master.lookup(p.stem)
        if entry is None:
            results.append(Candidate(p, kind, SKIP_UNREGISTERED, f"「{p.stem}」はマスタに登録されていない"))
            continue
        c = Candidate(p, kind, SEND, entry=entry)
        results.append(c)
        by_stem[normalize_name(p.stem)].append(c)

    # 同名・拡張子違いの整理: PDF > JPEG > PNG。同順位が複数なら判断不能として全部止める。
    for stem, group in by_stem.items():
        if len(group) < 2:
            continue
        best = min(PRIORITY[c.kind] for c in group)
        winners = [c for c in group if PRIORITY[c.kind] == best]
        if len(winners) > 1:
            names = "、".join(c.path.name for c in winners)
            for c in winners:
                c.status, c.reason = SKIP_CONFLICT, f"{names} が同時にあり、どれを送るか決められない"
            winners = []
        for c in group:
            if c not in winners and c.status == SEND:
                keep = winners[0].path.name if winners else "なし"
                c.status, c.reason = SKIP_DUPLICATE, f"同名の {keep} を優先"

    for c in results:
        if c.status != SEND:
            continue
        if not is_stable(c.path, stable_wait):
            c.status, c.reason = SKIP_UNSTABLE, "処理中に変更された、または開けない"
            continue
        c.sha256 = sha256_of(c.path)
    return results
