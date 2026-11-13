"""送信時に出るFAXドライバーの画面の「構造」を読み取る（読み取り専用。クリック・入力は一切しない）。

FAXドライバーへ印刷すると宛先を選ぶ画面が出る。その画面を自動操作できるかを判断するため、
画面上の部品（ボタン・リスト・入力欄など）の種類・名前・ID・有効/無効・位置をテキストに書き出す。
pywinauto の 2 つの方式（uia と win32）で読み、どちらが使いやすいかも比べられるようにする。

Windows専用の部分は関数の中で import するので、Linuxでも整形部分（テスト対象）は読み込める。
"""
from __future__ import annotations

import re
from dataclasses import dataclass

DEFAULT_TITLE_PATTERN = r"fax|ファクス|ファックス|宛先|apeos"
MAX_CONTROLS = 3000


def title_matches(title: str, pattern: str = DEFAULT_TITLE_PATTERN) -> bool:
    return bool(title) and re.search(pattern, title, re.IGNORECASE) is not None


@dataclass(frozen=True)
class ControlInfo:
    depth: int
    control_type: str
    name: str
    automation_id: str
    class_name: str
    enabled: bool | None
    visible: bool | None
    rect: tuple[int, int, int, int] | None


def format_control(c: ControlInfo) -> str:
    """1つの部品を1行にする。"""
    flags = []
    if c.enabled is False:
        flags.append("無効")
    if c.visible is False:
        flags.append("非表示")
    rect = f" @({c.rect[0]},{c.rect[1]})-({c.rect[2]},{c.rect[3]})" if c.rect else ""
    name = c.name.replace("\r", " ").replace("\n", " ")
    if len(name) > 80:
        name = name[:77] + "..."
    parts = [f"{'  ' * c.depth}[{c.control_type or '?'}]", f'"{name}"']
    if c.automation_id:
        parts.append(f"id={c.automation_id}")
    if c.class_name:
        parts.append(f"class={c.class_name}")
    if flags:
        parts.append("(" + "・".join(flags) + ")")
    return " ".join(parts) + rect


def _info(wrapper, depth: int) -> ControlInfo:
    ei = wrapper.element_info

    def safe(fn, default=None):
        try:
            return fn()
        except Exception:
            return default

    r = safe(lambda: wrapper.rectangle())
    rect = (r.left, r.top, r.right, r.bottom) if r is not None else None
    ctype = safe(lambda: ei.control_type) or ""
    if not ctype:  # win32 方式には control_type が無いので、クラス名と control_id で代用
        cid = safe(lambda: ei.control_id)
        ctype = f"ctrl{cid}" if cid else ""
    return ControlInfo(
        depth=depth,
        control_type=str(ctype),
        name=str(safe(lambda: wrapper.window_text(), "") or ""),
        automation_id=str(safe(lambda: ei.automation_id, "") or ""),
        class_name=str(safe(lambda: wrapper.class_name(), "") or ""),
        enabled=safe(lambda: wrapper.is_enabled()),
        visible=safe(lambda: wrapper.is_visible()),
        rect=rect,
    )


def _walk(wrapper, depth: int, out: list[ControlInfo]) -> None:
    if len(out) >= MAX_CONTROLS:
        return
    out.append(_info(wrapper, depth))
    try:
        children = wrapper.children()
    except Exception:
        return
    for ch in children:
        _walk(ch, depth + 1, out)


def dump(title_pattern: str, screenshot_path=None) -> list[str]:
    """条件に合うトップレベル画面の構造を、uia と win32 の両方式で読み取って行のリストで返す。"""
    from pywinauto import Desktop

    lines: list[str] = []
    found_any = False
    for backend in ("uia", "win32"):
        lines.append(f"===== 方式: {backend} =====")
        try:
            windows = Desktop(backend=backend).windows(visible_only=True)
        except Exception as exc:
            lines.append(f"  画面一覧を取得できません: {type(exc).__name__}: {exc}")
            continue
        targets = []
        for w in windows:
            try:
                title = w.window_text()
            except Exception:
                title = ""
            if title_matches(title, title_pattern):
                targets.append(w)
        if not targets:
            lines.append(f"  条件（{title_pattern}）に合う画面がありません。表示中の画面タイトル一覧:")
            for w in windows:
                try:
                    t = w.window_text()
                    if t:
                        lines.append(f"    - {t}  (class={w.class_name()}, pid={w.process_id()})")
                except Exception:
                    pass
            continue
        found_any = True
        for i, w in enumerate(targets, 1):
            try:
                head = f"--- 画面{i}: 「{w.window_text()}」 class={w.class_name()} pid={w.process_id()}"
            except Exception:
                head = f"--- 画面{i}"
            lines.append(head)
            controls: list[ControlInfo] = []
            _walk(w, 0, controls)
            lines.extend(format_control(c) for c in controls)
            if len(controls) >= MAX_CONTROLS:
                lines.append(f"（部品が多いため {MAX_CONTROLS} 個で打ち切り）")
            if screenshot_path is not None and backend == "uia":
                try:
                    p = screenshot_path.with_name(f"{screenshot_path.stem}_{i}{screenshot_path.suffix}")
                    w.capture_as_image().save(p)
                    lines.append(f"（画面の画像: {p}）")
                except Exception as exc:
                    lines.append(f"（画面の画像を保存できません: {exc}）")
    if not found_any:
        lines.append("")
        lines.append("FAXの宛先画面が見つかりませんでした。画面を開いたまま実行したか、上のタイトル一覧に該当する画面があるか確認してください。")
        lines.append("タイトルが違う場合は --title で指定できます（例: --title \"送信\"）。")
    return lines
