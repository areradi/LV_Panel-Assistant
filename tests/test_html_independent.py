from __future__ import annotations

import re

import pytest


@pytest.fixture(scope="module")
def demo_html(tmp_path_factory):
    from lv_assist.catalog import CatalogRepository
    from lv_assist.engine import EngineeringEngine
    from lv_assist.exporters import PrintableReportExporter
    from lv_assist.gui import build_demo_project
    from lv_assist.i18n import i18n, tr

    previous_language = i18n.get_language()
    i18n._language = "en"
    try:
        project, feeders = build_demo_project()
        outputs, summary, validations = EngineeringEngine(
            CatalogRepository.get_default_catalog()
        ).process_project(project, feeders)
        html_path = tmp_path_factory.mktemp("html-independent") / "engineering-report.html"
        PrintableReportExporter.generate_html_report(
            str(html_path), project, outputs, summary, validations
        )
        return html_path.read_text(encoding="utf-8"), project.project_name, feeders, tr("disclaimer_general")
    finally:
        i18n._language = previous_language


def test_html_has_project_name(demo_html):
    html, project_name, _, _ = demo_html
    assert project_name in html


def test_html_has_disclaimer(demo_html):
    html, _, _, disclaimer = demo_html
    assert disclaimer in html


def test_html_has_preliminary_watermark(demo_html):
    html, _, _, _ = demo_html
    assert "PRELIMINARY" in html


def test_html_has_localized_page_counters(demo_html):
    html, _, _, _ = demo_html
    assert "counter(page)" in html
    assert "counter(pages)" in html
    assert '"Page " counter(page) " of " counter(pages)' in html


def test_html_has_feeder_tags(demo_html):
    html, _, feeders, _ = demo_html
    for feeder in feeders:
        assert f"{feeder.func_tag}{feeder.loc_tag}" in html


def test_html_closes_tables(demo_html):
    html, _, _, _ = demo_html
    assert len(re.findall(r"<table\b", html, flags=re.IGNORECASE)) == len(
        re.findall(r"</table\s*>", html, flags=re.IGNORECASE)
    )
