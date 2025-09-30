"""Tests for Google SERP helpers supporting the Lever pivot."""

from __future__ import annotations

import os
import sys
from urllib.parse import parse_qs, urlparse

import pytest

sys.path.insert(0, os.getcwd())

from sites.lever.lever_google_discovery import (  # noqa: E402
    LeverGoogleDiscovery,
    build_google_query,
    paginate,
)


@pytest.mark.parametrize(
    "terms,location,time_window,expected",
    [
        (["front end"], "remote us", "d", "q=site%3Ajobs.lever.co+front+end+remote+us"),
        (["data", "scientist"], None, "w", "q=site%3Ajobs.lever.co+data+scientist"),
    ],
)
def test_build_google_query_encodes_terms(terms, location, time_window, expected):
    """The query builder encodes Lever constrained search terms."""

    url = build_google_query(terms, location, time_window=time_window)
    assert expected in url
    assert f"tbs=qdr:{time_window}" in url
    assert url.endswith("udm=14")


def test_paginate_overwrites_existing_start():
    """Pagination should replace existing start parameters."""

    base = "https://www.google.com/search?q=site%3Ajobs.lever.co&start=0"
    page_two = paginate(base, page=2)
    parsed = urlparse(page_two)
    params = parse_qs(parsed.query)
    assert params["start"] == ["20"]


def test_lever_google_plan_extracts_only_lever_results():
    """Only Lever hosts should be returned and apply URLs are preferred."""

    html = """
    <div class="tF2Cxc">
      <div class="yuRUbf">
        <a class="zReHs" href="https://jobs.lever.co/example/role-123/apply">
          <h3>Example Corp — Frontend Engineer</h3>
        </a>
      </div>
    </div>
    <div class="tF2Cxc">
      <div class="yuRUbf">
        <a class="zReHs" href="https://jobs.lever.co/example/role-456">
          <h3>Example Corp — Backend Engineer</h3>
        </a>
      </div>
    </div>
    <div class="tF2Cxc">
      <div class="yuRUbf">
        <a class="zReHs" href="https://example.com/not-lever">
          <h3>Ignore Me</h3>
        </a>
      </div>
    </div>
    """
    results = LeverGoogleDiscovery.extract_results(html)
    assert len(results) == 2
    assert results[0].href == "https://jobs.lever.co/example/role-123/apply"
    assert results[0].is_apply is True
    assert results[1].href == "https://jobs.lever.co/example/role-456"
    assert results[1].is_apply is False


def test_extract_results_deduplicates_paths():
    """Duplicate Lever entries should be collapsed by path."""

    html = """
    <div class="tF2Cxc">
      <a href="https://jobs.lever.co/example/role-123/apply?lever-source=google">Result A</a>
    </div>
    <div class="tF2Cxc">
      <a href="https://jobs.lever.co/example/role-123/apply">Result B</a>
    </div>
    """
    results = LeverGoogleDiscovery.extract_results(html)
    assert len(results) == 1
    assert results[0].href == "https://jobs.lever.co/example/role-123/apply"

