"""Search readiness heuristics for SimplyHired search result pages."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence

from bs4 import BeautifulSoup


@dataclass(slots=True)
class SelectorVariant:
    """Represents a selector variant for SimplyHired layouts."""

    id: str
    job_card_selectors: tuple[str, ...]
    detail_selectors: tuple[str, ...]
    title_selectors: tuple[str, ...]
    description: str | None = None


@dataclass(slots=True)
class SearchReadinessConfig:
    """Configuration for readiness detection."""

    min_cards: int
    variants: tuple[SelectorVariant, ...]

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "SearchReadinessConfig":
        try:
            min_cards = int(data.get("minCardCount", 0))
        except (TypeError, ValueError) as exc:  # pragma: no cover - defensive
            raise ValueError("minCardCount must be an integer") from exc
        if min_cards <= 0:
            raise ValueError("minCardCount must be greater than zero")
        variants_data = data.get("variants")
        if not isinstance(variants_data, Sequence) or not variants_data:
            raise ValueError("variants must be a non-empty list")
        variants: List[SelectorVariant] = []
        for entry in variants_data:
            if not isinstance(entry, Mapping):  # pragma: no cover - defensive
                raise ValueError("Each variant must be a mapping")
            variant_id = str(entry.get("id") or "").strip()
            if not variant_id:
                raise ValueError("variant id is required")
            job_cards = _ensure_selector_tuple(entry.get("jobCardSelectors"), "jobCardSelectors")
            detail = _ensure_selector_tuple(entry.get("detailSelectors"), "detailSelectors")
            title = _ensure_selector_tuple(entry.get("titleSelectors"), "titleSelectors")
            description = entry.get("description")
            variants.append(
                SelectorVariant(
                    id=variant_id,
                    job_card_selectors=job_cards,
                    detail_selectors=detail,
                    title_selectors=title,
                    description=str(description) if description else None,
                )
            )
        return cls(min_cards=min_cards, variants=tuple(variants))


@dataclass(slots=True)
class SearchReadinessResult:
    """Outcome from evaluating a DOM snapshot."""

    ok: bool
    variant_id: str | None
    job_card_count: int
    detail_found: bool
    job_card_selector: str | None
    detail_selector: str | None
    title_selector: str | None
    diagnostics: Dict[str, Any]


class SearchReadinessDetector:
    """Evaluate SimplyHired DOM snapshots for readiness."""

    def __init__(self, config: SearchReadinessConfig) -> None:
        self.config = config

    @classmethod
    def load(
        cls,
        path: Path,
        *,
        overrides: Sequence[Path] | None = None,
    ) -> "SearchReadinessDetector":
        """Load configuration from JSON files, applying overrides if provided."""

        data = _load_json(path)
        for override in overrides or ():
            if override and override.exists():
                data = _merge_mapping(data, _load_json(override))
        return cls(SearchReadinessConfig.from_mapping(data))

    def evaluate(self, html: str) -> SearchReadinessResult:
        """Return readiness result for the provided HTML markup."""

        soup = BeautifulSoup(html, "html.parser")
        diagnostics: Dict[str, Any] = {"minCardCount": self.config.min_cards, "variants": []}
        best_failure: Dict[str, Any] | None = None

        for variant in self.config.variants:
            variant_diag: Dict[str, Any] = {
                "variantId": variant.id,
                "jobCardSelectors": [],
                "detailSelectors": [],
                "titleSelectors": [],
            }
            diagnostics["variants"].append(variant_diag)

            job_card_selector: str | None = None
            job_card_count = 0
            for selector in variant.job_card_selectors:
                matches = soup.select(selector)
                count = len(matches)
                variant_diag["jobCardSelectors"].append({"selector": selector, "count": count})
                if count > job_card_count:
                    job_card_count = count
                if job_card_selector is None and count >= self.config.min_cards:
                    job_card_selector = selector
            detail_selector: str | None = None
            detail_found = False
            for selector in variant.detail_selectors:
                count = len(soup.select(selector))
                variant_diag["detailSelectors"].append({"selector": selector, "count": count})
                if not detail_found and count > 0:
                    detail_found = True
                    detail_selector = selector
            title_selector: str | None = None
            title_found = False
            for selector in variant.title_selectors:
                node = soup.select_one(selector)
                text = node.get_text(strip=True) if node else ""
                count = 1 if node else 0
                variant_diag["titleSelectors"].append(
                    {"selector": selector, "count": count, "text": text[:80]}
                )
                if not title_found and text:
                    title_found = True
                    title_selector = selector

            if job_card_selector and detail_found:
                variant_diag["status"] = "ok"
                variant_diag["jobCardCount"] = job_card_count
                return SearchReadinessResult(
                    ok=True,
                    variant_id=variant.id,
                    job_card_count=job_card_count,
                    detail_found=True,
                    job_card_selector=job_card_selector,
                    detail_selector=detail_selector,
                    title_selector=title_selector,
                    diagnostics=diagnostics,
                )

            variant_diag["status"] = "incomplete"
            variant_diag["jobCardCount"] = job_card_count
            variant_diag["detailFound"] = detail_found
            variant_diag["titleFound"] = title_found
            failure_reason = "insufficient_cards" if job_card_count < self.config.min_cards else "missing_detail"
            if not detail_found and job_card_count >= self.config.min_cards:
                failure_reason = "missing_detail"
            variant_diag["reason"] = failure_reason
            if best_failure is None or job_card_count > best_failure.get("jobCardCount", 0):
                best_failure = {
                    "variant_id": variant.id,
                    "job_card_count": job_card_count,
                    "detail_found": detail_found,
                    "job_card_selector": job_card_selector,
                    "detail_selector": detail_selector,
                    "title_selector": title_selector,
                    "reason": failure_reason,
                }

        best_failure = best_failure or {
            "variant_id": None,
            "job_card_count": 0,
            "detail_found": False,
            "job_card_selector": None,
            "detail_selector": None,
            "title_selector": None,
            "reason": "no_variants_configured",
        }
        diagnostics["reason"] = best_failure["reason"]
        return SearchReadinessResult(
            ok=False,
            variant_id=best_failure["variant_id"],
            job_card_count=best_failure["job_card_count"],
            detail_found=best_failure["detail_found"],
            job_card_selector=best_failure["job_card_selector"],
            detail_selector=best_failure["detail_selector"],
            title_selector=best_failure["title_selector"],
            diagnostics=diagnostics,
        )


def _ensure_selector_tuple(value: Any, field: str) -> tuple[str, ...]:
    if isinstance(value, str):
        selectors = [value]
    elif isinstance(value, Sequence):
        selectors = [str(item) for item in value if str(item).strip()]
    else:
        selectors = []
    selectors = [selector.strip() for selector in selectors if selector.strip()]
    if not selectors:
        raise ValueError(f"{field} must be a non-empty sequence")
    return tuple(dict.fromkeys(selectors))  # remove duplicates while preserving order


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _merge_mapping(base: Mapping[str, Any], override: Mapping[str, Any]) -> Dict[str, Any]:
    merged: Dict[str, Any] = dict(base)
    for key, value in override.items():
        if (
            isinstance(value, Mapping)
            and isinstance(merged.get(key), Mapping)
        ):
            merged[key] = _merge_mapping(merged[key], value)  # type: ignore[arg-type]
        else:
            merged[key] = value
    return merged
