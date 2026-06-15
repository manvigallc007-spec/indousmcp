"""Per-source scrapers. Each yields source-agnostic candidate dicts."""

from .base import Scraper
from .caterbid import CaterbidScraper
from .osm_overpass import OverpassScraper
from .wikidata import WikidataScraper

# Registry so the CLI and agents can look scrapers up by name.
SCRAPERS: dict[str, type[Scraper]] = {
    OverpassScraper.source_name: OverpassScraper,
    WikidataScraper.source_name: WikidataScraper,
    CaterbidScraper.source_name: CaterbidScraper,
}

__all__ = ["Scraper", "OverpassScraper", "WikidataScraper", "CaterbidScraper", "SCRAPERS"]
