from faxjob.uidump_win import ControlInfo, format_control, title_matches


def test_title_matches_default():
    assert title_matches("FUJIFILM Apeos C2360 FAX")
    assert title_matches("ファクス送信")
    assert title_matches("宛先の確認")
    assert not title_matches("無題 - メモ帳")
    assert not title_matches("")
    assert title_matches("送信確認", r"送信")


def test_format_control():
    c = ControlInfo(2, "Button", "送信(S)", "1001", "Button", True, True, (10, 20, 110, 50))
    assert format_control(c) == '    [Button] "送信(S)" id=1001 class=Button @(10,20)-(110,50)'
    c = ControlInfo(0, "", "x" * 100, "", "", False, False, None)
    line = format_control(c)
    assert line.startswith('[?] "' + "x" * 77 + '..."') and "(無効・非表示)" in line
