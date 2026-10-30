from passbook.normalize import to_amount


def test_won_sign_and_comma():
    assert to_amount("₩736,000") == 736000


def test_dot_and_won_suffix():
    assert to_amount("736.000원") == 736000


def test_plain_digits():
    assert to_amount("21") == 21


def test_none_and_empty():
    assert to_amount(None) == 0
    assert to_amount("") == 0
