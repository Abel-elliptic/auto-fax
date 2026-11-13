"""FAXドライバーの「ファクス送信の設定／確認」画面を自動操作して送信する。

座標は一切使わない。部品は ID（control id）で特定し、操作は Windows メッセージで行う：
  - ボタン   : 親画面へ WM_COMMAND(BN_CLICKED, ID) を送る（マウス・座標を使わない）
  - 文字入力 : EM_REPLACESEL（pywinauto の set_edit_text）
  - リスト   : LVM_GETITEM で読む／LVM_SETITEMSTATE で選ぶ（pywinauto の ListView 操作）
各操作のあとに画面の状態を読み直して確認し、想定と違えば「送信中止」を押して止める。

部品 ID は 2026-11-13 に実機（FF Direct Fax Driver 3.3.9.1）で uidump して得たもの。
ドライバーを更新したら uidump で ID が変わっていないか確認すること。
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from pathlib import Path

# ---- 部品 ID（FF Direct Fax Driver 3.3.9.1 で確認） ----
MAIN_TITLE_RE = r"^ファクス送信の設定"   # 「ファクス送信の設定／確認：<文書名>」
ID_SEND = 1            # 送信開始（親画面）
ID_ABORT = 2           # 送信中止（親画面）
ID_DEST_LIST = 4002    # 宛先の一覧 (SysListView32)
ID_ADD_TO_LIST = 4003  # 一覧に追加
ID_DEST_TYPE = 4016    # 宛先種別 (ComboBox) 「ファクス」
ID_NUMBER = 4018       # 宛先番号/アドレス (Edit)
ID_NAME = 4019         # 名前 (Edit)
ID_FROM_BOOK = 4049    # 宛先表から追加...
ID_TIMED = 4010        # 時刻を指定して送信する (CheckBox) → 使わない

BOOK_TITLE = "宛先表から追加"
ID_BOOK_LIST = 1010    # 宛先表のデータの一覧
ID_BOOK_ADD = 1014     # 宛先へ追加
ID_BOOK_DEST = 1016    # （宛先表画面内の）宛先の一覧
ID_BOOK_OK = 1
ID_BOOK_CANCEL = 2

GROUP_MARK = "(Group)"

WM_COMMAND = 0x0111
BN_CLICKED = 0
BST_CHECKED = 1


# ---- Windows に依存しない判定（単体テスト対象） ----

def digits(s: str) -> str:
    return re.sub(r"\D", "", s or "")


def check_test_destinations(rows: list[list[str]], number: str, group_name: str) -> list[str]:
    """テスト送信の直前に、宛先の一覧が「テスト番号1件だけ」かを確かめる。問題があれば理由を返す。"""
    problems = []
    if len(rows) != 1:
        problems.append(f"宛先が {len(rows)} 件あります（テストでは1件だけのはず）")
    for r in rows:
        cells = [c.strip() for c in r]
        if GROUP_MARK in cells or group_name in cells:
            problems.append(f"宛先にグループ（{group_name} など）が含まれています: {cells}")
        if not any(digits(c) == digits(number) and digits(c) for c in cells):
            problems.append(f"テスト番号 {number} ではない宛先があります: {cells}")
    return problems


def find_group_row(book_rows: list[list[str]], group_name: str) -> list[int]:
    """宛先表から、名前が group_name と完全一致し、かつグループである行の番号を返す（「一斉」と「一斉2」を区別する）。"""
    hits = []
    for i, r in enumerate(book_rows):
        cells = [c.strip() for c in r]
        if group_name in cells and GROUP_MARK in cells:
            hits.append(i)
    return hits


def check_group_destinations(rows: list[list[str]], group_name: str) -> list[str]:
    """本番送信の直前に、宛先の一覧が「指定グループ1件だけ」かを確かめる。"""
    problems = []
    if len(rows) != 1:
        problems.append(f"宛先が {len(rows)} 件あります（グループ1件だけのはず）")
    for r in rows:
        cells = [c.strip() for c in r]
        if group_name not in cells:
            problems.append(f"「{group_name}」ではない宛先があります: {cells}")
    return problems


@dataclass
class GuiResult:
    sent: bool = False                  # 「送信開始」を押したか
    found_dialog: bool = False
    log: list[str] = field(default_factory=list)
    error: str = ""

    def add(self, msg: str) -> None:
        self.log.append(time.strftime("%H:%M:%S ") + msg)


# ---- Windows 部分 ----

class _Abort(Exception):
    pass


def _list_rows(lv) -> list[list[str]]:
    cols = max(1, lv.column_count())
    rows = []
    for i in range(lv.item_count()):
        rows.append([lv.get_item(i, c).text() or "" for c in range(cols)])
    return rows


def _press(button) -> None:
    """ボタンを座標なしで押す：親画面へ WM_COMMAND(BN_CLICKED) を送る。押せない状態なら止める。"""
    import win32gui

    if not button.is_enabled():
        raise _Abort(f"ボタン「{button.window_text()}」が押せない状態です")
    hwnd = button.handle
    parent = win32gui.GetParent(hwnd)
    cid = win32gui.GetDlgCtrlID(hwnd)
    win32gui.PostMessage(parent, WM_COMMAND, (BN_CLICKED << 16) | (cid & 0xFFFF), hwnd)


def _child(spec, cid: int, cls: str | None = None):
    kw = {"control_id": cid}
    if cls:
        kw["class_name"] = cls
    return spec.child_window(**kw).wrapper_object()


def _snapshot(win, path: Path | None, res: GuiResult, label: str) -> None:
    if path is None:
        return
    try:
        p = path.with_name(f"{path.stem}_{label}.png")
        win.capture_as_image().save(p)
        res.add(f"画面の画像: {p}")
    except Exception as exc:  # 画面ロック中などは撮れない。動作には影響させない
        res.add(f"画面の画像を保存できません（{exc}）")


def _wait_enabled(ctrl, seconds: float = 5.0) -> bool:
    end = time.time() + seconds
    while time.time() < end:
        if ctrl.is_enabled():
            return True
        time.sleep(0.2)
    return False


def operate_dialog(*, mode: str, test_number: str, group_name: str, rehearsal: bool,
                   timeout: float, pid: int, shot: Path | None) -> GuiResult:
    """送信画面が出るのを待ち、宛先を設定して送信（rehearsal=True なら最後に「送信中止」）する。

    mode='test'       : 宛先番号欄にテスト番号を入れて「一覧に追加」
    mode='production' : 「宛先表から追加」でグループ（一斉2）を選ぶ
    """
    from pywinauto import Desktop

    res = GuiResult()
    desk = Desktop(backend="win32")
    main_spec = desk.window(title_re=MAIN_TITLE_RE, process=pid, class_name="#32770")
    try:
        main_spec.wait("exists visible", timeout=timeout)
    except Exception:
        res.error = f"{timeout:.0f}秒待っても「ファクス送信の設定／確認」画面が出ませんでした"
        return res
    res.found_dialog = True
    main = main_spec.wrapper_object()
    res.add(f"送信画面を検出: {main.window_text()}")

    def abort(reason: str) -> GuiResult:
        res.error = reason
        res.add(f"中止: {reason}")
        try:
            _press(_child(main_spec, ID_ABORT, "Button"))
            res.add("「送信中止」を押しました（送信していません）")
        except Exception as exc:
            res.add(f"「送信中止」を押せませんでした。画面を手で閉じてください（{exc}）")
        return res

    try:
        # 事前確認：宛先の一覧が空、宛先種別がファクス、時刻指定なし
        dest = _child(main_spec, ID_DEST_LIST, "SysListView32")
        before = _list_rows(dest)
        if before:
            return abort(f"最初から宛先の一覧に {len(before)} 件入っています（印刷設定の既定宛先を空にしてください）: {before}")
        dtype = _child(main_spec, ID_DEST_TYPE, "ComboBox").window_text()
        if dtype != "ファクス":
            return abort(f"宛先種別が「ファクス」ではありません（{dtype}）")
        timed = _child(main_spec, ID_TIMED, "Button")
        if timed.get_check_state() == BST_CHECKED:
            return abort("「時刻を指定して送信する」がオンになっています")

        if mode == "test":
            num = _child(main_spec, ID_NUMBER, "Edit")
            num.set_edit_text(test_number)
            res.add(f"宛先番号に {test_number} を入力")
            try:
                _child(main_spec, ID_NAME, "Edit").set_edit_text("テスト")
            except Exception:
                pass
            add_btn = _child(main_spec, ID_ADD_TO_LIST, "Button")
            if not _wait_enabled(add_btn):
                return abort("番号を入れても「一覧に追加」が押せる状態になりません")
            _press(add_btn)
            time.sleep(1.0)
            rows = _list_rows(dest)
            res.add(f"宛先の一覧: {rows}")
            problems = check_test_destinations(rows, test_number, group_name)
        elif mode == "production":
            _press(_child(main_spec, ID_FROM_BOOK, "Button"))
            book_spec = desk.window(title=BOOK_TITLE, process=pid, class_name="#32770")
            try:
                book_spec.wait("exists visible", timeout=30)
            except Exception:
                return abort("「宛先表から追加」画面が出ませんでした")
            book_list = _child(book_spec, ID_BOOK_LIST, "SysListView32")
            book_rows = _list_rows(book_list)
            hits = find_group_row(book_rows, group_name)
            if len(hits) != 1:
                _press(_child(book_spec, ID_BOOK_CANCEL, "Button"))
                return abort(f"宛先表で「{group_name}」(Group) がちょうど1件見つかりません（{len(hits)}件）")
            idx = hits[0]
            res.add(f"宛先表の {idx + 1} 行目を選択: {book_rows[idx]}")
            book_list.get_item(idx).select()
            add_btn = _child(book_spec, ID_BOOK_ADD, "Button")
            if not _wait_enabled(add_btn):
                _press(_child(book_spec, ID_BOOK_CANCEL, "Button"))
                return abort("選択しても「宛先へ追加」が押せる状態になりません")
            _press(add_btn)
            time.sleep(1.0)
            picked = _list_rows(_child(book_spec, ID_BOOK_DEST, "SysListView32"))
            res.add(f"宛先表画面の宛先の一覧: {picked}")
            p = check_group_destinations(picked, group_name)
            if p:
                _press(_child(book_spec, ID_BOOK_CANCEL, "Button"))
                return abort("宛先表画面で想定外: " + " / ".join(p))
            _press(_child(book_spec, ID_BOOK_OK, "Button"))
            try:
                book_spec.wait_not("exists", timeout=10)
            except Exception:
                return abort("「宛先表から追加」画面が閉じません")
            time.sleep(1.0)
            rows = _list_rows(dest)
            res.add(f"宛先の一覧: {rows}")
            problems = check_group_destinations(rows, group_name)
        else:
            return abort(f"不明なモード: {mode}")

        if problems:
            return abort("宛先が想定と違います: " + " / ".join(problems))

        _snapshot(main, shot, res, "before_send")
        if rehearsal:
            return _rehearsal_end(main_spec, res)

        _press(_child(main_spec, ID_SEND, "Button"))
        res.sent = True
        res.add("「送信開始」を押しました")
        try:
            main_spec.wait_not("exists", timeout=30)
            res.add("送信画面が閉じました（FAXドライバーへの投入へ進みます）")
        except Exception:
            res.add("送信画面が閉じません。画面を確認してください")
        return res
    except _Abort as exc:
        return abort(str(exc))
    except Exception as exc:
        return abort(f"想定外のエラー: {type(exc).__name__}: {exc}")


def _rehearsal_end(main_spec, res: GuiResult) -> GuiResult:
    """リハーサル：宛先の設定まで確認できたら「送信中止」で閉じる。"""
    res.add("リハーサル：宛先の設定まで成功。送信せずに「送信中止」を押します")
    try:
        _press(_child(main_spec, ID_ABORT, "Button"))
        res.add("「送信中止」を押しました（送信していません）")
    except Exception as exc:
        res.error = f"「送信中止」を押せませんでした。画面を手で閉じてください（{exc}）"
    return res
