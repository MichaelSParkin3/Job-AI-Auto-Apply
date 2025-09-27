from pathlib import Path

from sites.simplyhired.search_readiness import SearchReadinessDetector

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SELECTOR_SOURCE = (
    PROJECT_ROOT / "sites" / "simplyhired" / "selectors" / "search-readiness.json"
)
FIXTURES_DIR = PROJECT_ROOT / "core" / "tests" / "fixtures" / "simplyhired" / "search"


def _load_html(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


def test_detector_identifies_baseline_ready():
    detector = SearchReadinessDetector.load(SELECTOR_SOURCE)
    html = _load_html("baseline.html")
    result = detector.evaluate(html)
    assert result.ok is True
    assert result.variant_id == "serp-default"
    assert result.job_card_count >= detector.config.min_cards
    assert result.detail_found is True


def test_detector_uses_compact_variant():
    detector = SearchReadinessDetector.load(SELECTOR_SOURCE)
    html = _load_html("alternate.html")
    result = detector.evaluate(html)
    assert result.ok is True
    assert result.variant_id == "compact-iframe"
    assert result.detail_found is True


def test_detector_reports_missing_detail():
    detector = SearchReadinessDetector.load(SELECTOR_SOURCE)
    html = _load_html("missing_detail.html")
    result = detector.evaluate(html)
    assert result.ok is False
    assert result.detail_found is False
    assert result.diagnostics["reason"] == "missing_detail"


def test_detector_reports_insufficient_cards():
    detector = SearchReadinessDetector.load(SELECTOR_SOURCE)
    html = _load_html("spinner.html")
    result = detector.evaluate(html)
    assert result.ok is False
    assert result.job_card_count < detector.config.min_cards
    assert result.diagnostics["reason"] == "insufficient_cards"
