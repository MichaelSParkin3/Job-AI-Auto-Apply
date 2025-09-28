"""Quick Apply discovery helpers for SimplyHired search pages."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence

from bs4 import BeautifulSoup

from apps.browser import BrowserActionStatus, BrowserUseController
from apps.cli.utils import log_event


@dataclass(slots=True)
class QuickApplySelectors:
    """Normalized selector configuration used by discovery."""

    job_cards: tuple[str, ...]
    quick_apply_markers: tuple[str, ...]
    job_links: tuple[str, ...]
    job_key_attributes: tuple[str, ...]
    detail_quick_apply: tuple[str, ...]
    detail_inline: tuple[str, ...]
    detail_close: tuple[str, ...]
    pagination_next: tuple[str, ...]

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "QuickApplySelectors":
        def ensure_tuple(value: Any, field: str) -> tuple[str, ...]:
            if isinstance(value, str):
                values = [value]
            elif isinstance(value, Sequence):
                values = [str(item) for item in value if str(item).strip()]
            else:
                values = []
            values = [item.strip() for item in values if item.strip()]
            if not values:
                raise ValueError(f"{field} must be a non-empty sequence")
            # Remove duplicates while preserving order
            return tuple(dict.fromkeys(values))

        def ensure_attr_tuple(value: Any, field: str) -> tuple[str, ...]:
            if isinstance(value, str):
                attrs = [value]
            elif isinstance(value, Sequence):
                attrs = [str(item).strip() for item in value if str(item).strip()]
            else:
                attrs = []
            if not attrs:
                raise ValueError(f"{field} must be a non-empty sequence")
            return tuple(dict.fromkeys(attrs))

        return cls(
            job_cards=ensure_tuple(data.get("jobCardSelectors"), "jobCardSelectors"),
            quick_apply_markers=ensure_tuple(
                data.get("jobCardQuickApplySelectors"), "jobCardQuickApplySelectors"
            ),
            job_links=ensure_tuple(data.get("jobCardLinkSelectors"), "jobCardLinkSelectors"),
            job_key_attributes=ensure_attr_tuple(
                data.get("jobKeyAttributes"), "jobKeyAttributes"
            ),
            detail_quick_apply=ensure_tuple(
                data.get("detailQuickApplySelectors"), "detailQuickApplySelectors"
            ),
            detail_inline=ensure_tuple(
                data.get("detailInlineSelectors"), "detailInlineSelectors"
            ),
            detail_close=ensure_tuple(
                data.get("detailCloseSelectors"), "detailCloseSelectors"
            ),
            pagination_next=ensure_tuple(
                data.get("paginationNextSelectors"), "paginationNextSelectors"
            ),
        )


@dataclass(slots=True)
class QuickApplyCandidateResult:
    """Represents a processed candidate posting."""

    job_key: str
    title: str | None
    url: str | None
    status: str
    page_index: int
    sequence: int
    mode: str | None
    artifact_path: str | None

    def to_payload(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "jobKey": self.job_key,
            "status": self.status,
            "pageIndex": self.page_index,
            "sequence": self.sequence,
        }
        if self.title:
            payload["title"] = self.title
        if self.url:
            payload["url"] = self.url
        if self.mode:
            payload["mode"] = self.mode
        if self.artifact_path:
            payload["artifact"] = self.artifact_path
        return payload


@dataclass(slots=True)
class QuickApplyDiscoverySummary:
    """Aggregated outcome returned by discovery."""

    limit_requested: int
    candidates: list[QuickApplyCandidateResult] = field(default_factory=list)
    opened_count: int = 0
    missing_count: int = 0
    duplicate_count: int = 0
    visited_keys: set[str] = field(default_factory=set)
    pagination_events: list[str] = field(default_factory=list)
    pages_visited: int = 0
    limit_reached: bool = False
    artifacts: list[str] = field(default_factory=list)

    def record_candidate(
        self,
        candidate: QuickApplyCandidateResult,
        *,
        opened: bool,
        duplicate: bool = False,
    ) -> None:
        if duplicate:
            self.duplicate_count += 1
            return
        self.candidates.append(candidate)
        self.visited_keys.add(candidate.job_key)
        if opened:
            self.opened_count += 1
        else:
            self.missing_count += 1
        if candidate.artifact_path:
            self.artifacts.append(candidate.artifact_path)

    def limit_remaining(self) -> int:
        return max(self.limit_requested - self.opened_count, 0)

    def to_payload(self) -> Dict[str, Any]:
        return {
            "summary": {
                "processedCount": len(self.candidates),
                "openedCount": self.opened_count,
                "missingCount": self.missing_count,
                "duplicateCount": self.duplicate_count,
                "limitRequested": self.limit_requested,
                "limitRemaining": self.limit_remaining(),
                "visitedCount": len(self.visited_keys),
                "pagesVisited": self.pages_visited,
                "paginationEvents": list(self.pagination_events),
                "limitReached": self.limit_reached,
            },
            "candidates": [candidate.to_payload() for candidate in self.candidates],
            "artifacts": list(self.artifacts),
        }

    def telemetry_payload(self) -> Dict[str, Any]:
        return {
            "processed": len(self.candidates),
            "opened": self.opened_count,
            "missing": self.missing_count,
            "duplicates": self.duplicate_count,
            "visited": len(self.visited_keys),
            "pages": self.pages_visited,
            "limitRequested": self.limit_requested,
            "limitRemaining": self.limit_remaining(),
            "limitReached": self.limit_reached,
            "paginationEvents": list(self.pagination_events),
        }


class QuickApplyDiscovery:
    """Encapsulates SimplyHired Quick Apply discovery behaviour."""

    def __init__(self, selectors: QuickApplySelectors) -> None:
        self.selectors = selectors

    @classmethod
    def load(
        cls,
        path: Path,
        *,
        overrides: Sequence[Path] | None = None,
        inline_overrides: Sequence[Mapping[str, Any]] | None = None,
    ) -> "QuickApplyDiscovery":
        data = _load_json(path)
        for override in overrides or ():
            if override and override.exists():
                data = _merge_mapping(data, _load_json(override))
        for mapping in inline_overrides or ():
            data = _merge_mapping(data, mapping)
        return cls(QuickApplySelectors.from_mapping(data))

    def run(
        self,
        controller: BrowserUseController,
        *,
        run_dir: Path,
        limit: int,
        wait_timeout: float = 5.0,
    ) -> QuickApplyDiscoverySummary:
        summary = QuickApplyDiscoverySummary(limit_requested=max(0, limit))
        run_dir.mkdir(parents=True, exist_ok=True)

        initial = controller.get_page_html()
        if initial.status is BrowserActionStatus.ERROR:
            log_event(
                {
                    "level": "error",
                    "event": "quick_apply.discovery.capture_failed",
                    "message": "Failed to capture initial search HTML for discovery.",
                    "error": initial.details.get("error"),
                }
            )
            return summary

        page_html = initial.details.get("html", "")
        page_index = 0
        summary.pages_visited = 1 if page_html.strip() else 0

        while page_html:
            candidates = self._extract_candidates(page_html)
            if not candidates:
                log_event(
                    {
                        "event": "END_OF_RESULTS",
                        "page": page_index,
                    }
                )
                summary.pagination_events.append("END_OF_RESULTS")
                break

            for candidate_index, candidate in enumerate(candidates, start=1):
                if candidate.job_key in summary.visited_keys:
                    log_event(
                        {
                            "event": "QA_SKIPPED_DUPLICATE",
                            "jobKey": candidate.job_key,
                            "page": page_index,
                            "sequence": candidate_index,
                        }
                    )
                    summary.record_candidate(
                        QuickApplyCandidateResult(
                            job_key=candidate.job_key,
                            title=candidate.title,
                            url=candidate.url,
                            status="duplicate",
                            page_index=page_index,
                            sequence=candidate_index,
                            mode=None,
                            artifact_path=None,
                        ),
                        opened=False,
                        duplicate=True,
                    )
                    continue

                log_event(
                    {
                        "event": "QA_CANDIDATE",
                        "jobKey": candidate.job_key,
                        "title": candidate.title,
                        "url": candidate.url,
                        "page": page_index,
                        "sequence": candidate_index,
                    }
                )

                opened, mode, artifact_path = self._process_candidate(
                    controller,
                    candidate,
                    run_dir=run_dir,
                    sequence=len(summary.candidates) + 1,
                    wait_timeout=wait_timeout,
                )

                status = "opened" if opened else "missing"
                summary.record_candidate(
                    QuickApplyCandidateResult(
                        job_key=candidate.job_key,
                        title=candidate.title,
                        url=candidate.url,
                        status=status,
                        page_index=page_index,
                        sequence=len(summary.candidates) + 1,
                        mode=mode,
                        artifact_path=artifact_path,
                    ),
                    opened=opened,
                )

                if opened:
                    log_event(
                        {
                            "event": "QUICK_APPLY_OPENED",
                            "jobKey": candidate.job_key,
                            "mode": mode,
                            "artifact": artifact_path,
                            "page": page_index,
                        }
                    )
                    if summary.opened_count >= summary.limit_requested > 0:
                        summary.limit_reached = True
                        log_event(
                            {
                                "event": "QUICK_APPLY_LIMIT_REACHED",
                                "limit": summary.limit_requested,
                                "opened": summary.opened_count,
                            }
                        )
                        break
                else:
                    log_event(
                        {
                            "level": "warning",
                            "event": "QUICK_APPLY_MISSING",
                            "jobKey": candidate.job_key,
                            "page": page_index,
                        }
                    )

                self._close_quick_apply(controller, wait_timeout=wait_timeout)

            if summary.limit_reached:
                break

            next_selector = self._find_next_selector(page_html)
            if not next_selector:
                log_event(
                    {
                        "event": "END_OF_RESULTS",
                        "page": page_index,
                    }
                )
                summary.pagination_events.append("END_OF_RESULTS")
                break

            click_result = controller.safe_click(next_selector, timeout=wait_timeout)
            if click_result.status is BrowserActionStatus.ERROR:
                log_event(
                    {
                        "level": "error",
                        "event": "PAGINATION_FAILED",
                        "message": "Failed to click pagination control.",
                        "selector": next_selector,
                        "error": click_result.details.get("error"),
                        "page": page_index,
                    }
                )
                summary.pagination_events.append("PAGINATION_FAILED")
                break

            controller.wait_for_idle(timeout=wait_timeout)
            next_page = controller.get_page_html()
            if next_page.status is BrowserActionStatus.ERROR:
                log_event(
                    {
                        "level": "error",
                        "event": "PAGINATION_CAPTURE_FAILED",
                        "message": "Failed to capture next page HTML after pagination.",
                        "error": next_page.details.get("error"),
                    }
                )
                summary.pagination_events.append("PAGINATION_CAPTURE_FAILED")
                break

            log_event(
                {
                    "event": "PAGINATED_NEXT",
                    "fromPage": page_index,
                    "selector": next_selector,
                }
            )
            summary.pagination_events.append("PAGINATED_NEXT")
            page_html = next_page.details.get("html", "")
            page_index += 1
            if page_html.strip():
                summary.pages_visited += 1
        return summary

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    @dataclass(slots=True)
    class _Candidate:
        job_key: str
        title: str | None
        url: str | None
        selector: str

    def _extract_candidates(self, html: str) -> List["QuickApplyDiscovery._Candidate"]:
        soup = BeautifulSoup(html, "html.parser")
        candidates: List[QuickApplyDiscovery._Candidate] = []
        base_selector = self.selectors.job_cards[0]

        for card in soup.select(base_selector):
            if not self._has_quick_apply_marker(card):
                continue
            url = self._extract_link(card)
            job_key, attr = self._extract_job_key(card, url=url)
            if not job_key:
                continue
            selector = base_selector
            if attr:
                selector = f"{base_selector}[{attr}='{job_key}']"
            title = self._extract_title(card)
            candidates.append(self._Candidate(job_key=job_key, title=title, url=url, selector=selector))
        return candidates

    def _has_quick_apply_marker(self, card: Any) -> bool:
        for selector in self.selectors.quick_apply_markers:
            if card.select_one(selector):
                return True
        return False

    def _extract_link(self, card: Any) -> str | None:
        for selector in self.selectors.job_links:
            node = card.select_one(selector)
            if node and node.get("href"):
                return node.get("href")
        return None

    def _extract_title(self, card: Any) -> str | None:
        for selector in self.selectors.job_links:
            node = card.select_one(selector)
            if node:
                text = node.get_text(strip=True)
                if text:
                    return text
        return None

    def _extract_job_key(self, card: Any, *, url: str | None) -> tuple[str | None, str | None]:
        for attr in self.selectors.job_key_attributes:
            value = card.get(attr)
            if value:
                return str(value), attr
        if url:
            return url, None
        text = card.get_text(strip=True)
        return text or None, None

    def _process_candidate(
        self,
        controller: BrowserUseController,
        candidate: "QuickApplyDiscovery._Candidate",
        *,
        run_dir: Path,
        sequence: int,
        wait_timeout: float,
    ) -> tuple[bool, str | None, str | None]:
        click_result = controller.safe_click(candidate.selector, timeout=wait_timeout)
        if click_result.status is BrowserActionStatus.ERROR:
            log_event(
                {
                    "level": "error",
                    "event": "QUICK_APPLY_OPEN_ERROR",
                    "jobKey": candidate.job_key,
                    "selector": candidate.selector,
                    "error": click_result.details.get("error"),
                }
            )
            return False, None, None

        controller.wait_for_idle(timeout=wait_timeout)
        detail_result = controller.get_page_html()
        if detail_result.status is BrowserActionStatus.ERROR:
            log_event(
                {
                    "level": "error",
                    "event": "QUICK_APPLY_CAPTURE_FAILED",
                    "jobKey": candidate.job_key,
                    "error": detail_result.details.get("error"),
                }
            )
            return False, None, None

        html = detail_result.details.get("html", "")
        mode = self._detect_mode(html)
        artifact_path = None
        if html.strip():
            artifact_path = self._write_artifact(run_dir, sequence, html)
        return mode is not None, mode, artifact_path

    def _detect_mode(self, html: str) -> str | None:
        soup = BeautifulSoup(html, "html.parser")
        for selector in self.selectors.detail_quick_apply:
            if soup.select_one(selector):
                return "modal"
        for selector in self.selectors.detail_inline:
            if soup.select_one(selector):
                return "inline"
        return None

    def _close_quick_apply(
        self, controller: BrowserUseController, *, wait_timeout: float
    ) -> None:
        for selector in self.selectors.detail_close:
            result = controller.safe_click(selector, timeout=wait_timeout)
            if result.status is BrowserActionStatus.OK:
                controller.wait_for_idle(timeout=wait_timeout)
                log_event(
                    {
                        "event": "QUICK_APPLY_CLOSED",
                        "selector": selector,
                    }
                )
                return
        log_event(
            {
                "level": "warning",
                "event": "QUICK_APPLY_CLOSE_MISSING",
                "message": "No close selector succeeded after opening Quick Apply.",
            }
        )

    def _find_next_selector(self, html: str) -> str | None:
        soup = BeautifulSoup(html, "html.parser")
        for selector in self.selectors.pagination_next:
            node = soup.select_one(selector)
            if node:
                return selector
        return None

    def _write_artifact(self, directory: Path, sequence: int, html: str) -> str:
        path = directory / f"candidate-{sequence:02d}.html"
        path.write_text(html, encoding="utf-8")
        return str(path)


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _merge_mapping(base: Mapping[str, Any], override: Mapping[str, Any]) -> Dict[str, Any]:
    merged: Dict[str, Any] = dict(base)
    for key, value in override.items():
        if isinstance(value, Mapping) and isinstance(merged.get(key), Mapping):
            merged[key] = _merge_mapping(merged[key], value)  # type: ignore[arg-type]
        else:
            merged[key] = value
    return merged
