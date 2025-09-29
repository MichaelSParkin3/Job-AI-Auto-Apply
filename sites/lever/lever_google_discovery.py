from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Dict


WINDOW_MAP = {"h": "qdr:h", "d": "qdr:d", "w": "qdr:w", "m": "qdr:m", "y": "qdr:y"}


def _encode_q(query: str) -> str:
    # very small encoder; Typer/requests will do proper encoding when needed
    return query.replace(" ", "+")


def build_google_query(terms: Iterable[str], location: str | None, *, time_window: str = "d") -> str:
    """Return the Google search URL constrained to Lever apply pages.

    Example:
      https://www.google.com/search?q=site:jobs.lever.co/apply+front+end+remote+us&tbs=qdr:d
    """

    q_parts: List[str] = ["site:jobs.lever.co/apply"]
    for t in terms:
        t = (t or "").strip()
        if t:
            q_parts.append(t)
    if location and location.strip():
        q_parts.append(location.strip())
    q = _encode_q(" ".join(q_parts))
    tbs = WINDOW_MAP.get(time_window, "qdr:d")
    return f"https://www.google.com/search?q={q}&tbs={tbs}"


def paginate(url: str, *, page: int) -> str:
    """Return a paginated SERP URL by adding start=10*page."""

    start = page * 10
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}start={start}"


@dataclass(slots=True)
class LeverGooglePlan:
    base_url: str
    pages: int

    def urls(self) -> List[str]:
        return [paginate(self.base_url, page=i) for i in range(self.pages)]

    def to_payload(self) -> Dict[str, object]:
        return {"baseUrl": self.base_url, "pages": self.pages, "urls": self.urls()}


class LeverGoogleDiscovery:
    """Planning helper for Google SERP → Lever apply discovery."""

    @staticmethod
    def plan(terms: Iterable[str], location: str | None, *, time_window: str = "d", pages: int = 1) -> LeverGooglePlan:
        base = build_google_query(list(terms), location, time_window=time_window)
        if pages < 1:
            pages = 1
        return LeverGooglePlan(base_url=base, pages=pages)

