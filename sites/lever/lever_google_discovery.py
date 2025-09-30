"""Utilities for building and parsing Google SERP queries for Lever."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable, List
from urllib.parse import parse_qsl, quote_plus, urlencode, urlparse, urlunparse

from html import unescape


WINDOW_MAP = {"h": "qdr:h", "d": "qdr:d", "w": "qdr:w", "m": "qdr:m", "y": "qdr:y"}

_HOST_ALLOWLIST = {"jobs.lever.co"}


def build_google_query(
    terms: Iterable[str],
    location: str | None,
    *,
    time_window: str = "d",
    include_udm: bool = True,
) -> str:
    """Return a Google search URL constrained to Lever apply pages."""

    q_parts: List[str] = ["site:jobs.lever.co"]
    for term in terms:
        normalized = (term or "").strip()
        if normalized:
            q_parts.append(normalized)
    if location:
        location = location.strip()
        if location:
            q_parts.append(location)

    query = quote_plus(" ".join(q_parts))
    tbs = WINDOW_MAP.get(time_window, WINDOW_MAP["d"])

    url = f"https://www.google.com/search?q={query}&tbs={tbs}"
    if include_udm:
        url += "&udm=14"
    return url


def paginate(url: str, *, page: int) -> str:
    """Return a SERP URL with the `start` query parameter set for the given page."""

    page = max(page, 0)
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["start"] = str(page * 10)
    new_query = urlencode(query, doseq=True)
    return urlunparse(parsed._replace(query=new_query))


@dataclass(slots=True)
class LeverGooglePlan:
    """Container describing the discovery pages to fetch."""

    base_url: str
    pages: int

    def urls(self) -> List[str]:
        return [paginate(self.base_url, page=i) for i in range(self.pages)]

    def to_payload(self) -> dict[str, object]:
        return {"baseUrl": self.base_url, "pages": self.pages, "urls": self.urls()}


@dataclass(slots=True)
class LeverSerpResult:
    """Normalized representation of a Lever link discovered via Google."""

    title: str
    href: str
    mode: str

    @property
    def is_apply(self) -> bool:
        return self.mode == "apply_direct"


def _is_apply_path(path: str) -> bool:
    sanitized = path.rstrip("/")
    return sanitized.endswith("/apply") or "/apply/" in sanitized


_ANCHOR_RE = re.compile(
    r"<a[^>]+href=[\"'](?P<href>[^\"'>]+)[\"'][^>]*>(?P<label>.*?)</a>",
    re.IGNORECASE | re.DOTALL,
)


def _strip_tags(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", unescape(text)).strip()


def parse_serp_html(html: str) -> list[LeverSerpResult]:
    """Extract Lever results from a Google SERP HTML snapshot."""

    results: list[LeverSerpResult] = []
    seen: set[str] = set()

    for match in _ANCHOR_RE.finditer(html):
        href = unescape(match.group("href")).strip()
        if not href:
            continue
        parsed = urlparse(href)
        host = parsed.netloc.lower()
        if host not in _HOST_ALLOWLIST:
            continue
        key = parsed.path.rstrip("/")
        if key in seen:
            continue
        seen.add(key)

        title = _strip_tags(match.group("label"))
        mode = "apply_direct" if _is_apply_path(parsed.path) else "job_page"
        cleaned = urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))
        results.append(LeverSerpResult(title=title or cleaned, href=cleaned, mode=mode))

    return results


class LeverGoogleDiscovery:
    """Planning and parsing helpers for Google SERP → Lever apply discovery."""

    @staticmethod
    def plan(
        terms: Iterable[str],
        location: str | None,
        *,
        time_window: str = "d",
        pages: int = 1,
    ) -> LeverGooglePlan:
        base = build_google_query(list(terms), location, time_window=time_window)
        pages = max(pages, 1)
        return LeverGooglePlan(base_url=base, pages=pages)

    @staticmethod
    def extract_results(html: str) -> list[LeverSerpResult]:
        """Return Lever SERP results (apply URLs preferred when available)."""

        return parse_serp_html(html)

