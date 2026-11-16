from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

import pytest


def _browser_supports_headless_pdf(browser: str, tmp_path_factory) -> bool:
    probe_dir = tmp_path_factory.mktemp("pdf-browser-probe")
    html_path = probe_dir / "probe.html"
    pdf_path = probe_dir / "probe.pdf"
    html_path.write_text("<html><body>PDF capability check</body></html>", encoding="utf-8")
    try:
        with tempfile.TemporaryDirectory(prefix="edge-profile-", dir=str(probe_dir)) as profile:
            subprocess.run(
                [browser, "--headless=new", "--disable-gpu", "--no-first-run",
                 "--no-default-browser-check", "--no-pdf-header-footer",
                 f"--user-data-dir={profile}", f"--print-to-pdf={pdf_path}",
                 html_path.resolve().as_uri()],
                check=True, capture_output=True, timeout=30,
            )
        return pdf_path.is_file() and pdf_path.read_bytes().startswith(b"%PDF-")
    except (OSError, subprocess.SubprocessError):
        return False


@pytest.fixture(scope="module")
def generated_pdf(tmp_path_factory):
    try:
        from pypdf import PdfReader  # noqa: F401
    except ImportError:
        pytest.skip("pypdf is not installed — PDF content test skipped")

    from lv_assist.outputs import PdfExporter

    browser = PdfExporter._find_browser()
    if browser is None:
        pytest.skip("Chrome/Edge not available — PDF integration test skipped")
    if not _browser_supports_headless_pdf(browser, tmp_path_factory):
        pytest.skip("Chrome/Edge is installed but headless PDF printing is unavailable in this runner")

    from lv_assist.catalog import CatalogRepository
    from lv_assist.engine import EngineeringEngine
    from lv_assist.exporters import PrintableReportExporter
    from lv_assist.gui import build_demo_project
    from lv_assist.i18n import i18n

    previous_language = i18n.get_language()
    i18n._language = "en"
    try:
        project, feeders = build_demo_project()
        outputs, summary, validations = EngineeringEngine(
            CatalogRepository.get_default_catalog()
        ).process_project(project, feeders)
        temp_dir = tmp_path_factory.mktemp("pdf-independent")
        html_path = temp_dir / "engineering-report.html"
        pdf_path = temp_dir / "engineering-report.pdf"
        PrintableReportExporter.generate_html_report(
            str(html_path), project, outputs, summary, validations
        )
        assert PdfExporter.export_html_to_pdf(str(html_path), str(pdf_path)), (
            "A browser was detected but failed to generate the integration PDF"
        )
        assert pdf_path.is_file() and pdf_path.stat().st_size > 1000
        return pdf_path
    finally:
        i18n._language = previous_language


def _page_text(page) -> str:
    return re.sub(r"\s+", " ", page.extract_text() or "").strip()


def test_pdf_opens(generated_pdf):
    from pypdf import PdfReader

    reader = PdfReader(str(generated_pdf), strict=False)
    assert len(reader.pages) >= 3


def test_page_count_reasonable(generated_pdf):
    from pypdf import PdfReader

    page_count = len(PdfReader(str(generated_pdf), strict=False).pages)
    assert 8 <= page_count <= 20, f"Unexpected demo report page count: {page_count}"


def test_page_size_a4_landscape(generated_pdf):
    from pypdf import PdfReader

    page = PdfReader(str(generated_pdf), strict=False).pages[0]
    width = float(page.mediabox.width)
    height = float(page.mediabox.height)
    assert width > height
    assert abs(width - 842.0) <= 5.0, f"Unexpected page width: {width} pt"
    assert abs(height - 595.0) <= 5.0, f"Unexpected page height: {height} pt"


def test_project_name_in_pages(generated_pdf):
    from pypdf import PdfReader

    pages = [_page_text(page) for page in PdfReader(str(generated_pdf), strict=False).pages]
    expected = "MCC Pump Station Demo Project".casefold()
    matching = sum(expected in page.casefold() for page in pages)
    assert matching / len(pages) >= 0.8, f"Project name found on {matching}/{len(pages)} pages"


def test_disclaimer_in_footer(generated_pdf):
    from pypdf import PdfReader

    pages = [_page_text(page).casefold() for page in PdfReader(str(generated_pdf), strict=False).pages]
    assert pages
    assert all("preliminary" in page for page in pages), "Localized short disclaimer missing from a page"


def test_preliminary_in_body(generated_pdf):
    from pypdf import PdfReader

    first_page = _page_text(PdfReader(str(generated_pdf), strict=False).pages[0]).casefold()
    assert "preliminary" in first_page, "PRELIMINARY marker not found in first-page body text"


def test_feeder_tags_present(generated_pdf):
    from pypdf import PdfReader

    text = " ".join(_page_text(page) for page in PdfReader(str(generated_pdf), strict=False).pages)
    for tag in ("=PUMP1+MCC1", "=COMP1+MCC1", "=PUMP2+MCC1", "=LGT1+MCC1"):
        assert tag in text, f"Feeder tag missing from extracted PDF text: {tag}"


def test_extraction_not_empty(generated_pdf):
    from pypdf import PdfReader

    text = " ".join(_page_text(page) for page in PdfReader(str(generated_pdf), strict=False).pages)
    assert len(text) > 1000, f"Extracted only {len(text)} characters from PDF"
