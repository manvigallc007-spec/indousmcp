"""Scraper interface. New verticals/sources implement this contract."""

from __future__ import annotations

from typing import Iterator, Protocol, runtime_checkable


@runtime_checkable
class Scraper(Protocol):
    #: Stable identifier stored in restaurant_raw.source_name.
    source_name: str

    def scrape(self, region: str) -> Iterator[dict]:
        """Yield source-agnostic candidate dicts for the given region/metro.

        Each dict should carry whatever the source provides, plus ``source_name``,
        ``source_url`` and ``source_id`` so the pipeline can track provenance and
        deduplicate against prior observations.
        """
        ...
