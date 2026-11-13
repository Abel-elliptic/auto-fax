"""コマンド入口。

  python -m faxjob demo  [--settings 設定.toml] [--input フォルダ] [--master マスタ.csv] [--out 出力先]
  python -m faxjob print [--settings 設定.toml] [--printer プリンター名] [--only ファイル名] [--output-dir 出力先]
  python -m faxjob inspect --printer プリンター名 [--out 結果ファイル]

demo  は送信フォルダを読み、判定とFAX用ページ画像を作ってHTMLで表示する。FAXは送信しない。
print は同じページ画像を、ページごとに用紙・向きを指定してプリンターへ出力する（Windowsのみ）。
      Step 2 では「Microsoft Print to PDF」に出力し、PDFで用紙・向き・余白を確認する。
      FAXドライバーらしいプリンターへの出力は、mode=test かつ --allow-fax の時だけ許可する。
inspect はプリンタードライバーの対応用紙・解像度・用紙/向きの指定可否を読むだけ（印刷ジョブを作らない＝FAXは出ない）。
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


def _render_all(settings, src: Path, master, stable_check: bool, only: str | None = None):
    """送信フォルダを判定し、送信対象をページ画像にする。FileResult を順に返す。"""
    for c in scan(src, master, stable_wait=settings.stable_wait_seconds if stable_check else 0):
        if only and c.path.name != only:
            continue
        r = FileResult(c)
        if c.will_send:
            try:
                r.pages = render_file(c.path, c.kind, c.entry.paper, settings.render)
            except Exception as exc:  # 壊れたファイル等。送信対象から外す
                r.error = f"画像化に失敗: {exc}"
                c.status = "読み込みエラー"
        yield r


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
    for r in _render_all(settings, src, master, args.stable_check):
        c = r.candidate
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


def cmd_print(args: argparse.Namespace) -> int:
    settings = load_settings(Path(args.settings) if args.settings else None)
    printer = args.printer or settings.printer_name
    if not printer:
        print("出力先プリンターを --printer か settings.toml の print.printer_name で指定してください", file=sys.stderr)
        return 2
    if sys.platform != "win32":
        print("print コマンドは Windows でのみ動きます", file=sys.stderr)
        return 2
    from .printer_win import looks_like_fax, print_pages, printer_driver_name

    try:
        driver = printer_driver_name(printer)
    except Exception as exc:
        print(f"プリンター「{printer}」が見つかりません: {exc}", file=sys.stderr)
        return 2
    if looks_like_fax(printer, driver):
        if not args.allow_fax or settings.mode != "test":  # 本番送信の仕組み（Step 4以降）ができるまでは test のみ
            print(f"「{printer}」（ドライバー: {driver}）はFAXドライバーの可能性があるため出力しません。\n"
                  "テスト宛先が決まり、settings.toml の print.mode を test にしたうえで --allow-fax を付けた時だけ出力します。\n"
                  "（宛先グループ「一斉2」は社外の複数社に届くため、テストでは絶対に使わないでください）", file=sys.stderr)
            return 3
        print(f"[注意] FAXドライバー「{printer}」へ出力します（mode={settings.mode}）。宛先がテスト宛先であることを確認してください。")

    src = Path(args.input) if args.input else settings.send_dir
    master = load_master(Path(args.master) if args.master else settings.master_path)
    is_pdf_printer = printer.lower() == "microsoft print to pdf"
    out_dir = Path(args.output_dir) if args.output_dir else settings.preview_dir.parent / "print_test"
    if is_pdf_printer:
        out_dir.mkdir(parents=True, exist_ok=True)

    summary: list[str] = [f"プリンター: {printer}（ドライバー: {driver}）", f"送信フォルダ: {src}", ""]
    printed = problems = 0
    for r in _render_all(settings, src, master, args.stable_check, args.only):
        c = r.candidate
        if not r.pages:
            summary.append(f"[出力しない] {c.path.name}: {r.error or c.status + ' ' + c.reason}")
            continue
        output_file = (out_dir / f"{c.path.stem}.pdf").resolve() if is_pdf_printer else None
        try:
            results = print_pages(printer, r.pages, f"FAX {c.path.name}", settings.render.margin_mm, output_file)
        except Exception as exc:  # PrinterError やドライバーのエラー
            summary.append(f"[失敗] {c.path.name}: {exc}")
            problems += 1
            continue
        printed += 1
        summary.append(f"[出力] {c.path.name}" + (f" → {output_file}" if output_file else ""))
        for pr in results:
            w, h = pr.device_mm
            ux, uy = pr.unprintable_mm
            line = f"    {pr.number}ページ: 要求 {pr.paper.label()} / プリンターの用紙 {w:.0f}×{h:.0f}mm / 印刷できない端 {ux:.1f}×{uy:.1f}mm"
            summary.append(line + ("  ← 問題: " + "、".join(pr.problems) if pr.problems else "  OK"))
            problems += bool(pr.problems)

    summary += ["", f"出力 {printed} ファイル、問題 {problems} 件"]
    text = "\n".join(summary)
    print(text)
    if out_dir.exists():
        (out_dir / "print_result.txt").write_text(text + "\n", encoding="utf-8")
        print(f"\n結果: {(out_dir / 'print_result.txt').resolve()}")
    return 1 if problems else 0


def cmd_inspect(args: argparse.Namespace) -> int:
    if sys.platform != "win32":
        print("inspect コマンドは Windows でのみ動きます", file=sys.stderr)
        return 2
    from .printer_win import format_inspection, inspect_printer

    try:
        ins = inspect_printer(args.printer)
    except Exception as exc:
        print(f"プリンター「{args.printer}」を調べられません: {exc}", file=sys.stderr)
        return 2
    text = "\n".join(["（読み取りのみ。印刷ジョブは作っていません＝FAXは送信されていません）", ""] + format_inspection(ins))
    print(text)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text + "\n", encoding="utf-8")
    print(f"\n結果: {out.resolve()}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="faxjob", description="FAX定期自動送信（開発中：demo / print / inspect のみ。定期送信は未実装）")
    sub = parser.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("demo", help="送信せずに判定とページ画像を確認する")
    d.add_argument("--settings", help="settings.toml のパス")
    d.add_argument("--input", help="送信フォルダ（既定: 設定の base_dir\\送信）")
    d.add_argument("--master", help="マスタCSV（既定: 設定の base_dir\\設定\\master.csv）")
    d.add_argument("--out", help="結果の出力先（既定: 設定の base_dir\\ログ\\preview）")
    d.add_argument("--stable-check", action="store_true", help="書き込み中チェックも行う（数秒待つ）")
    d.add_argument("--open", action="store_true", help="終わったらブラウザで開く")
    d.set_defaults(func=cmd_demo)

    pr = sub.add_parser("print", help="ページ画像をプリンターへ出力する（Windowsのみ。Step 2 は Microsoft Print to PDF）")
    pr.add_argument("--settings", help="settings.toml のパス")
    pr.add_argument("--printer", help="出力先プリンター名（既定: 設定の print.printer_name）")
    pr.add_argument("--input", help="送信フォルダ（既定: 設定の base_dir\\送信）")
    pr.add_argument("--master", help="マスタCSV（既定: 設定の base_dir\\設定\\master.csv）")
    pr.add_argument("--only", help="このファイル名だけ出力する（例: 請求書.pdf）")
    pr.add_argument("--output-dir", help="Microsoft Print to PDF の保存先（既定: 設定の base_dir\\ログ\\print_test）")
    pr.add_argument("--stable-check", action="store_true", help="書き込み中チェックも行う（数秒待つ）")
    pr.add_argument("--allow-fax", action="store_true", help="FAXドライバーへの出力を許可する（settings.toml の print.mode が test の時のみ有効）")
    pr.set_defaults(func=cmd_print)

    ins = sub.add_parser("inspect", help="プリンタードライバーの対応状況を読む（Windowsのみ。印刷・送信はしない）")
    ins.add_argument("--printer", required=True, help='例: "FUJIFILM Apeos C2360 FAX"')
    ins.add_argument("--out", default="out/inspect.txt", help="結果の保存先（既定: out/inspect.txt）")
    ins.set_defaults(func=cmd_inspect)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
