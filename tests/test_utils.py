"""纯函数测试：URL 规范化、日期区间、文件魔数、大小格式化。"""

from __future__ import annotations

import io
from datetime import date, datetime, timedelta

import pytest

from app.utils.dtime import date_range, days_between, parse_date, resolve_range
from app.utils.security import content_disposition, human_size, safe_join, verify_signature
from app.utils.url import InvalidUrlError as UrlError
from app.utils.url import display_url, host_of, normalize_url


class TestNormalizeUrl:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("www.tencent.com", "https://www.tencent.com"),
            ("  https://www.example.com  ", "https://www.example.com"),
            ("HTTP://A.com/x?y=1", "http://a.com/x?y=1"),
            ("example.com/path/a", "https://example.com/path/a"),
            ("", None),
            (None, None),
            ("   ", None),
        ],
    )
    def test_ok(self, raw, expected):
        assert normalize_url(raw) == expected

    @pytest.mark.parametrize(
        "raw",
        [
            "javascript:alert(1)",
            "data:text/html,<script>alert(1)</script>",
            "file:///etc/passwd",
            "ftp://example.com",
            "https://",
            "not a url",
        ],
    )
    def test_rejected(self, raw):
        with pytest.raises(UrlError):
            normalize_url(raw)

    def test_too_long(self):
        with pytest.raises(UrlError):
            normalize_url("https://a.com/" + "x" * 300)

    def test_display_and_host(self):
        assert display_url("https://www.tencent.com") == "www.tencent.com"
        assert host_of("https://www.tencent.com/a/b") == "www.tencent.com"
        assert display_url(None) == ""


class TestDateHelpers:
    def test_parse_date(self):
        assert parse_date("2026-03-18") == date(2026, 3, 18)
        assert parse_date("2026/03/18") is None
        assert parse_date(None, date(2026, 1, 1)) == date(2026, 1, 1)

    def test_resolve_range_defaults_to_30_days(self):
        start, end = resolve_range(None, None, default_days=30)
        assert (end - start).days == 29

    def test_resolve_range_rejects_reversed_and_overlong(self):
        start, end = resolve_range("2026-05-01", "2026-04-01", default_days=7)
        assert (end - start).days == 6  # 回退到默认区间

        start, end = resolve_range("2020-01-01", "2026-01-01", default_days=7, max_days=365)
        assert (end - start).days == 6

    def test_date_range_is_inclusive(self):
        days = date_range(date(2026, 3, 1), date(2026, 3, 5))
        assert len(days) == 5
        assert days[0] == date(2026, 3, 1) and days[-1] == date(2026, 3, 5)

    def test_days_between(self):
        base = datetime(2026, 3, 1, 10, 0)
        assert days_between(base, base + timedelta(days=3)) == 3
        assert days_between(base, base) == 0
        assert days_between(None, base) is None


class TestFileSecurity:
    def test_pdf_signature(self):
        assert verify_signature(io.BytesIO(b"%PDF-1.7 content"), "pdf") is True
        assert verify_signature(io.BytesIO(b"MZ\x90\x00exe"), "pdf") is False

    def test_doc_signature(self):
        ole2 = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 32
        assert verify_signature(io.BytesIO(ole2), "doc") is True
        assert verify_signature(io.BytesIO(b"not a doc"), "doc") is False

    def test_docx_requires_word_document_xml(self):
        import zipfile

        # 普通 zip：有 PK 头但不是 docx
        plain = io.BytesIO()
        with zipfile.ZipFile(plain, "w") as zf:
            zf.writestr("readme.txt", "hi")
        plain.seek(0)
        assert verify_signature(plain, "docx") is False

        real = io.BytesIO()
        with zipfile.ZipFile(real, "w") as zf:
            zf.writestr("word/document.xml", "<w:document/>")
        real.seek(0)
        assert verify_signature(real, "docx") is True

    def test_unknown_extension_rejected(self):
        assert verify_signature(io.BytesIO(b"%PDF-1.4"), "exe") is False

    def test_safe_join_blocks_traversal(self, tmp_path):
        root = tmp_path / "safejoin_root"
        root.mkdir(parents=True, exist_ok=True)
        (root / "1").mkdir(exist_ok=True)
        assert safe_join(root, "1/a.pdf").name == "a.pdf"
        with pytest.raises(ValueError):
            safe_join(root, "../../windows/system32/cmd.exe")

    def test_content_disposition_encodes_chinese(self):
        header = content_disposition("张三-简历.pdf")
        assert "filename*=UTF-8''" in header
        assert "attachment" in header

    def test_human_size(self):
        assert human_size(0) == "0 B"
        assert human_size(1024) == "1.0 KB"
        assert human_size(5 * 1024 * 1024) == "5.0 MB"
