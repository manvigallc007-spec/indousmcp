# Data Sources for the Indian-American Directory

Curated answer to `INDIAN_USA_DATA_PROMPT.md`. All Tier-1/Tier-2 sources are **free, public, or
openly licensed**. Tier-3 are freemium/paid — listed for *later* (once we have a base + funding),
not used now. We never scrape sites that forbid it, never store data a source's ToS prohibits
caching, and only use public/aggregated/business-directory data (no private PII).

Verticals today: restaurants, groceries, temples, professionals, salons, sweets, studios,
services, apparel, community, events.

---

## Already integrated
| Source | Data | Notes |
|---|---|---|
| OpenStreetMap / Overpass | POIs (restaurants, temples, groceries, shops…) | Free, ODbL (we attribute). Our main scraper. |
| Wikidata SPARQL | Notable places/orgs | Free, CC0. |
| Website enrichment (schema.org / OpenGraph) | rating, photo, socials, hours | From each listing's own site. |
| Public iCal (.ics) feeds + feed-discovery | events | Org calendars. |
| Nominatim (OSM) | forward geocoding | Free; 1 req/s. |

---

## Tier 1 — Free & public, high-impact (recommend wiring next)

### 1. NPPES NPI Registry (CMS) — **professionals**
- **URL:** https://npiregistry.cms.gov/api/ (live API) · bulk file: https://download.cms.gov/nppes/NPI_Files.html
- **Data:** every US healthcare provider — legal/DBA name, NPI, **taxonomy/specialty**, practice
  address, phone. Searchable by name, taxonomy, city/state.
- **Free/open:** ✅ Public US government registry, **no API key**.
- **API/feed:** ✅ JSON API + free monthly bulk download.
- **Restrictions:** Public provider *business* info — use as business listings, not personal PII.
- **Schema → `professionals`:** name, `profession_type`/`speciality` ← taxonomy, address→geo,
  phone; match Indian surnames (we already have a surname list) + relevant taxonomies.
- **Why:** far more complete & authoritative than OSM for doctors/dentists/clinics.

### 2. U.S. Census Bureau API (ACS) — **demographics / prioritization**
- **URL:** https://api.census.gov/data (free key: https://api.census.gov/data/key_signup.html)
- **Data:** "Asian Indian" population, ancestry, income, education, and **languages spoken at home**
  (Hindi, Telugu, Tamil, Gujarati, Punjabi, Bengali, Urdu, Malayalam, Kannada, Marathi) by
  state/county/**metro/ZCTA**.
- **Free/open:** ✅ Public domain, aggregated (no PII).
- **API/feed:** ✅ REST API + bulk.
- **Restrictions:** none material (cite Census).
- **Schema → new `demographics` reference table** (not a listing vertical): use it to (a) **rank
  which metros/cities to scrape next** (where Indian-Americans actually concentrate — e.g. add
  metros we're missing), and (b) power a public **"Indian America by the numbers" insights page**
  (great for SEO + engagement).

### 3. U.S. Census Geocoder — **geocoding**
- **URL:** https://geocoding.geo.census.gov/geocoder/
- **Data:** US address → lat/lng + census geographies; **batch up to 10k** addresses.
- **Free/open:** ✅ No key, official.
- **API/feed:** ✅ REST + batch CSV.
- **Use:** complement/replace Nominatim for US forward-geocoding (faster, no 1/s limit, official).
  Drop-in for our `geocode.coords_for` / `backfill-geo`.

### 4. City / State Open-Data business licenses (Socrata / data.gov) — **businesses**
- **URL:** https://www.data.gov + city portals (NYC Open Data, DataSF, Chicago, LA, Seattle…),
  most on the **Socrata SODA API** (`https://<portal>/resource/<id>.json`).
- **Data:** licensed businesses — name, address, category/license type.
- **Free/open:** ✅ Open data (typically public domain / CC0).
- **API/feed:** ✅ SODA JSON API + CSV export.
- **Restrictions:** open; rate-limit politely (app token optional, free).
- **Schema → restaurants/groceries/services raw** with `source_name='socrata_<city>'`; filter by
  category (e.g. eating establishments, food stores) **+** our Indian name-match, then run through
  the same clean/approve pipeline. Strongest in the dense metros we care about.

### 5. OpenCorporates — **business verification**
- **URL:** https://opencorporates.com (API: https://api.opencorporates.com)
- **Data:** registered company name, address, status, officers (business registry).
- **Free/open:** ⚠️ Open-data mission; **free API tier (key, rate-limited)**; reuse under
  share-alike/attribution — verify terms.
- **Use:** confirm a business exists / fill address; not a primary discovery source.

---

## Tier 2 — Free but per-site / no central API (→ submissions + feed-discovery)
These have no clean bulk API; grow via our **/submit** flow, owner claims, and the events
feed-discovery agent — *only where the site permits automated access*.
- **University student-org directories** (Indian Students Assoc., Telugu/Tamil/Gujarati groups, ASA)
  — public per-campus lists → student communities.
- **Temple / association directories** (e.g. regional sangam/samaj sites, Hindu temple lists on
  **Wikipedia/Wikidata** — those we *can* ingest, CC-BY-SA/CC0).
- **Harvard Pluralism Project** religious-center directory — reference only (research use; not bulk).
- **DBpedia** (SPARQL over Wikipedia) — structured lists, free.

---

## Tier 3 — Freemium / paid (LATER, once we have a base + funding)
Listed for the roadmap. **Not used now** — each either bills after a free credit or has ToS that
block storing data in our own directory.
| Source | Data | Why it's "later" |
|---|---|---|
| Google Places API | rich POI, ratings, hours, photos | Free monthly credit, then **bills**; best accuracy when funded. |
| Yelp Fusion API | reviews, ratings, categories | Free tier exists **but ToS forbids caching/storing** Yelp content in our DB — display-only. Avoid for our stored directory. |
| Foursquare Places | POI + attributes | Freemium; check caching terms. |
| Eventbrite / (Meetup) | events | Free tiers restricted/changed; revisit for events. |

---

## Recommended build order (all Tier-1, all free/public)
1. **NPPES** scraper → instantly upgrades the Professionals vertical (real doctors + specialty).
2. **Census Geocoder** → swap into forward-geocoding (faster, official, batch).
3. **Census ACS demographics** → a `demographics` table that (a) tells the Discovery/Recommendation
   agents **which metros to scrape next**, and (b) a `/insights` SEO page ("Indian America by the
   numbers"). Closes the loop with the discovery/learning work already shipped.
4. **Socrata business licenses** for our top metros → more restaurants/groceries/services, name-matched.

Each plugs into the existing pipeline (new scraper in `pipeline/scrapers/` or a vertical's
`scraper.py` → raw → clean → approve), so no architectural change — just new sources.

> Policy check applied to every entry above: free/open or free-tier only; no prohibited scraping;
> no private PII; public/aggregated/business data only; attribution respected (OSM ODbL, Census,
> Socrata). Re-verify each source's current ToS at integration time.
