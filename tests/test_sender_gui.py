from faxjob.sender_gui import check_group_destinations, check_test_destinations, digits, find_group_row

NUM = "1860528244773"


def test_digits():
    assert digits("186-052-824-4773") == NUM


def test_check_test_destinations_ok():
    assert check_test_destinations([["", NUM, "テスト", ""]], NUM, "一斉2") == []


def test_check_test_destinations_rejects():
    assert check_test_destinations([], NUM, "一斉2")                                   # 0件
    assert check_test_destinations([["", NUM, "", ""], ["", NUM, "", ""]], NUM, "一斉2")  # 2件
    assert check_test_destinations([["", "0425135782", "x", ""]], NUM, "一斉2")         # 別番号
    probs = check_test_destinations([["", "(Group)", "一斉2", ""]], NUM, "一斉2")
    assert any("グループ" in p for p in probs)


BOOK = [
    ["", "アパマン福生", "", "0425135782", ""],
    ["", "一斉2", "", "(Group)", "34 件"],
    ["", "一斉", "アアいいっせい", "(Group)", "44 件"],
    ["", "一斉2", "", "0400000000", ""],  # 同名だがグループではない（仮の行）
]


def test_find_group_row_exact_match_only():
    assert find_group_row(BOOK, "一斉2") == [1]   # 「一斉」(44件) や同名の個人宛先は選ばない
    assert find_group_row(BOOK, "一斉") == [2]
    assert find_group_row(BOOK, "一斉3") == []


def test_check_group_destinations():
    assert check_group_destinations([["", "(Group)", "一斉2", ""]], "一斉2") == []
    assert check_group_destinations([["", "(Group)", "一斉", ""]], "一斉2")
    assert check_group_destinations([["", "(Group)", "一斉2", ""], ["", "x", "y", ""]], "一斉2")
