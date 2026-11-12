"""コマンド入口。

  python -m faxjob demo [--settings 設定.toml] [--input フォルダ] [--master マスタ.csv] [--out 出力先]

demo は送信フォルダを読み、判定とFAX用ページ画像を作ってHTMLで表示する。FAXは送信しない。
"""
from __future__ import annotations

import argparse
import shutil
import sys
import webbrowser
from pathlib import Path

from .config import load_settings
from .master import load_master
from .render import render_file
from .report import FileResult, write_report
from .scanner import scan


def cmd_demo(args: argparse.Namespace) -> int:
    settings = load_settings(Path(args.settings) if args.settings else None)
    src = Path(args.input) if args.input else settings.send_dir
    master_path = Path(args.master) if args.master else settings.master_path
    out = Path(args.out) if args.out else settings.preview_dir
    if not src.is_dir():
        print(f"送信フォルダがありません: {src}", file=sys.stderr)
        return 2

    master = load_master(master_path)
    for p in master.problems:
        print(f"[マスタ注意] {p}")

    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    results: list[FileResult] = []
    for c in scan(src, master, stable_wait=settings.stable_wait_seconds if args.stable_check else 0):
        r = FileResult(c)
        if c.will_send:
            try:
                r.pages = render_file(c.path, c.kind, c.entry.paper, settings.render)
            except Exception as exc:  # 壊れたファイル等。送信対象から外す
                r.error = f"画像化に失敗: {exc}"
                c.status = "読み込みエラー"
            for p in r.pages:
                name = f"{len(results):02d}_{c.path.stem}_p{p.number:03d}.png"
                p.image.save(out / name, optimize=True)
                r.image_names.append(name)
        results.append(r)
        pages = f"{len(r.pages)}ページ " if r.pages else ""
        print(f"{c.status:　<10} {c.path.name}  {pages}{r.error or c.reason}")

    report = write_report(out, results, master.problems, settings.render, src, master_path)
    print(f"\nデモ結果: {report.resolve()}")
    if args.open:
        webbrowser.open(report.resolve().as_uri())
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="faxjob", description="FAX定期自動送信（現在はデモのみ）")
    sub = parser.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("demo", help="送信せずに判定とページ画像を確認する")
    d.add_argument("--settings", help="settings.toml のパス")
    d.add_argument("--input", help="送信フォルダ（既定: 設定の base_dir\\送信）")
    d.add_argument("--master", help="マスタCSV（既定: 設定の base_dir\\設定\\master.csv）")
    d.add_argument("--out", help="結果の出力先（既定: 設定の base_dir\\ログ\\preview）")
    d.add_argument("--stable-check", action="store_true", help="書き込み中チェックも行う（数秒待つ）")
    d.add_argument("--open", action="store_true", help="終わったらブラウザで開く")
    d.set_defaults(func=cmd_demo)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
