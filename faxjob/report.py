"""デモ結果をHTMLで出力する（ブラウザで開いて確認する画面）。"""
from __future__ import annotations

import html
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .render import RenderedPage, RenderOptions
from .scanner import Candidate


@dataclass
class FileResult:
    candidate: Candidate
    pages: list[RenderedPage] = field(default_factory=list)
    image_names: list[str] = field(default_factory=list)
    error: str = ""


CSS = """
:root{--bg:#f6f7f9;--card:#fff;--text:#1d2329;--muted:#5b6672;--line:#d9dee4;
--ok:#1a7f37;--okbg:#e6f4ea;--warn:#9a6700;--warnbg:#fff4d6;--ng:#b42318;--ngbg:#fde8e7;--paper:#fff}
@media (prefers-color-scheme:dark){:root{--bg:#14171a;--card:#1d2226;--text:#e6e9ec;--muted:#9aa5b1;
--line:#323a42;--ok:#6fdd8b;--okbg:#17321f;--warn:#e9c46a;--warnbg:#3a3015;--ng:#ff8a80;--ngbg:#3d1d1b;--paper:#fff}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:15px/1.6 "Yu Gothic UI","Meiryo",system-ui,sans-serif}
main{max-width:1100px;margin:0 auto;padding:24px 16px 64px}
h1{font-size:22px;margin:0 0 4px}h2{font-size:17px;margin:0}
.muted{color:var(--muted)}.banner{background:var(--warnbg);color:var(--warn);border-radius:8px;padding:10px 14px;margin:16px 0}
.stats{display:flex;gap:12px;flex-wrap:wrap;margin:16px 0}
.stat{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:10px 16px;min-width:120px}
.stat b{display:block;font-size:24px}
table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:8px;overflow:hidden}
th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line);vertical-align:top}
th{font-weight:600;color:var(--muted);font-size:13px}
.tablewrap{overflow-x:auto}
.tag{display:inline-block;border-radius:999px;padding:1px 10px;font-size:13px;white-space:nowrap}
.tag.ok{background:var(--okbg);color:var(--ok)}.tag.ng{background:var(--ngbg);color:var(--ng)}.tag.warn{background:var(--warnbg);color:var(--warn)}
section.file{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:16px;margin:20px 0}
.pages{display:flex;flex-wrap:wrap;gap:16px;margin-top:12px}
figure{margin:0;width:260px}
figure a{display:flex;align-items:center;justify-content:center;height:260px;background:var(--bg);border-radius:6px}
figure img{max-width:240px;max-height:240px;background:var(--paper);box-shadow:0 0 0 1px #888,0 2px 6px rgba(0,0,0,.25)}
figcaption{font-size:13px;margin-top:6px}
ul.notes{margin:6px 0 0;padding-left:18px;color:var(--warn);font-size:13px}
"""


def _tag(c: Candidate) -> str:
    cls = "ok" if c.will_send else ("warn" if "重複" in c.status or "変更" in c.status else "ng")
    return f'<span class="tag {cls}">{html.escape(c.status)}</span>'


def write_report(out_dir: Path, results: list[FileResult], master_problems: list[str],
                 opt: RenderOptions, source_dir: Path, master_path: Path) -> Path:
    send = [r for r in results if r.candidate.will_send and not r.error]
    total_pages = sum(len(r.pages) for r in send)
    e = html.escape
    rows = []
    for r in results:
        c = r.candidate
        setting = c.entry.paper.label() if c.entry else "—"
        out = "、".join(sorted({p.paper.label() for p in r.pages})) or "—"
        reason = e(r.error or c.reason)
        rows.append(f"<tr><td>{e(c.path.name)}</td><td>{e(c.kind or '—')}</td><td>{_tag(c)}</td>"
                    f"<td>{e(setting)}</td><td>{e(out)}</td><td>{len(r.pages) or '—'}</td><td>{reason}</td></tr>")

    sections = []
    for r in send:
        c = r.candidate
        figs = []
        for p, name in zip(r.pages, r.image_names):
            notes = "".join(f"<li>{e(n)}</li>" for n in p.notes)
            figs.append(
                f'<figure><a href="{e(name)}" target="_blank"><img src="{e(name)}" alt="{e(c.path.name)} {p.number}ページ"></a>'
                f"<figcaption><b>{p.number}ページ：{e(p.paper.label())}</b><br>"
                f'<span class="muted">元 {e(p.source_desc)} ／ {e(p.scale_desc)}</span>'
                f'{f"<ul class=notes>{notes}</ul>" if notes else ""}</figcaption></figure>')
        sections.append(
            f'<section class="file"><h2>{e(c.path.name)}</h2>'
            f'<div class="muted">マスタ設定：{e(c.entry.paper.label())} ／ SHA-256：{e(c.sha256[:16])}…</div>'
            f'<div class="pages">{"".join(figs)}</div></section>')

    problems = ""
    if master_problems:
        items = "".join(f"<li>{e(p)}</li>" for p in master_problems)
        problems = f'<div class="banner"><b>マスタの注意</b><ul>{items}</ul></div>'

    doc = f"""<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>FAX送信デモ結果</title>
<style>{CSS}</style></head><body><main>
<h1>FAX送信デモ結果</h1>
<div class="muted">{e(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))} 作成 ／ 送信フォルダ：{e(str(source_dir))} ／ マスタ：{e(str(master_path))}</div>
<div class="banner">これはデモです。<b>FAXは送信していません。</b>下の画像は、FAXドライバーへ渡す予定の白黒ページ画像です（{opt.dpi}dpi、余白{opt.margin_mm:g}mm、{'文字' if opt.mono_mode == 'text' else '写真'}モード、PDFの用紙：{'PDFのページに合わせる' if opt.pdf_layout == 'auto' else 'マスタに合わせる'}）。</div>
{problems}
<div class="stats"><div class="stat"><span class="muted">ファイル数</span><b>{len(results)}</b></div>
<div class="stat"><span class="muted">送信対象</span><b>{len(send)}</b></div>
<div class="stat"><span class="muted">送信しない</span><b>{len(results) - len(send)}</b></div>
<div class="stat"><span class="muted">合計ページ</span><b>{total_pages}</b></div></div>
<div class="tablewrap"><table><thead><tr><th>ファイル</th><th>形式</th><th>判定</th><th>マスタ設定</th><th>出力用紙</th><th>ページ</th><th>理由・備考</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></div>
{''.join(sections)}
</main></body></html>"""
    path = out_dir / "index.html"
    path.write_text(doc, encoding="utf-8")
    return path
