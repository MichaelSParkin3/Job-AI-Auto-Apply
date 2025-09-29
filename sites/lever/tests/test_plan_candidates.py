from typing import Iterable

from apps.cli.main import _plan_candidates
from sites.lever.lever_google_discovery import LeverSerpResult


class FetchTracker:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def __call__(self, url: str) -> str | None:
        self.calls.append(url)
        raise AssertionError("fetch_html should not be called when cached results exist")


def test_plan_candidates_uses_embedded_results():
    payload = {
        "results": [
            {
                "title": "Frontend Engineer",
                "href": "https://jobs.lever.co/acme/frontend/apply",
                "mode": "apply_direct",
            }
        ]
    }

    tracker = FetchTracker()
    results = _plan_candidates(payload, fetch_html=tracker)

    assert len(results) == 1
    result = results[0]
    assert isinstance(result, LeverSerpResult)
    assert result.href == "https://jobs.lever.co/acme/frontend/apply"
    assert tracker.calls == []


def test_plan_candidates_uses_plan_results_when_present(monkeypatch):
    payload = {
        "plan": {
            "results": [
                {
                    "title": "Backend Engineer",
                    "href": "https://jobs.lever.co/acme/backend/apply",
                    "mode": "apply_direct",
                }
            ]
        }
    }

    tracker = FetchTracker()
    results = _plan_candidates(payload, fetch_html=tracker)

    assert len(results) == 1
    assert results[0].href == "https://jobs.lever.co/acme/backend/apply"
    assert tracker.calls == []


def test_plan_candidates_fetches_when_results_missing(monkeypatch):
    urls = [
        "https://www.google.com/search?q=lever&start=0",
        "https://www.google.com/search?q=lever&start=10",
    ]
    payload = {"plan": {"urls": urls}}

    html_map = {
        urls[0]: "first-page",
        urls[1]: "second-page",
    }

    def fake_fetch(url: str) -> str | None:
        return html_map.get(url)

    result_map: dict[str, Iterable[LeverSerpResult]] = {
        "first-page": [
            LeverSerpResult(
                title="Frontend Engineer",
                href="https://jobs.lever.co/acme/frontend/apply",
                mode="apply_direct",
            ),
            LeverSerpResult(
                title="Frontend Engineer (Duplicate)",
                href="https://jobs.lever.co/acme/frontend/apply",
                mode="apply_direct",
            ),
        ],
        "second-page": [
            LeverSerpResult(
                title="QA Engineer",
                href="https://jobs.lever.co/acme/qa/apply",
                mode="apply_direct",
            )
        ],
    }

    monkeypatch.setattr(
        "apps.cli.main.LeverGoogleDiscovery.extract_results",
        lambda html: list(result_map.get(html, [])),
    )

    results = _plan_candidates(payload, fetch_html=fake_fetch)

    assert [r.href for r in results] == [
        "https://jobs.lever.co/acme/frontend/apply",
        "https://jobs.lever.co/acme/qa/apply",
    ]
    assert len(results) == 2
