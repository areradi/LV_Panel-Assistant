from unittest.mock import patch

from lv_assist import gui


def test_open_local_file_windows_style_path():
    """A path with backslashes and spaces is converted to a valid file URI."""
    with patch("webbrowser.open", return_value=True) as mock_open:
        result = gui._open_local_file(r"C:\Users\Test User\report.html")
    assert result is True
    uri = mock_open.call_args.args[0]
    assert uri.startswith("file:///")
    assert "\\" not in uri
    assert " " not in uri
    assert "%20" in uri


def test_open_local_file_unicode_path():
    """Non-ASCII path characters are accepted and encoded in the file URI."""
    with patch("webbrowser.open", return_value=True) as mock_open:
        result = gui._open_local_file(r"C:\Users\کاربر\گزارش.html")
    assert result is True
    uri = mock_open.call_args.args[0]
    assert uri.startswith("file:///")
    assert "\\" not in uri


def test_open_local_file_handles_exception():
    with patch("webbrowser.open", side_effect=RuntimeError("Browser not found")):
        result = gui._open_local_file("C:/test.html")
    assert result is False
