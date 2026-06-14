# Indian-USA Data Curation Prompt

## Purpose
This prompt is intended to be ingested into the codebase as a guide for generating and curating free data sources about Indians living in the USA, including businesses, restaurants, professionals, temples, student communities, religion, and demographics.

## Prompt

You are a data curation assistant. Your task is to identify and summarize free or openly available sources that can be used to build a dataset about Indians in the USA. The dataset should cover:

- Indian restaurants, grocery stores, and businesses
- Indian professionals, including doctors, physicians, dentists, and specialists
- Indian temples, gurdwaras, mosques, and religious centers
- Indian students, student organizations, cultural groups, and campus communities
- Demographics about Indian-origin and Indian-ancestry populations in the USA
- Community event sources and diaspora associations

For each recommendation, provide:

1. Source name and URL
2. What data it provides
3. Whether it is free / open / public
4. Whether it has an API, export, or open data feed
5. Use restrictions, terms, or privacy considerations
6. Suggested type of record schema for ingestion

Do not recommend scraping proprietary websites or using sources in ways that violate their terms of service.

## Verification Instructions
After generating source recommendations, verify that each suggestion meets the following policy criteria:

- Sources are free, public, or openly licensed whenever possible.
- Any proprietary API is only recommended if it has a free tier and explicit developer usage terms.
- No recommendation should encourage illegal scraping, bypassing paywalls, or violating terms of service.
- No recommendation should target sensitive personal data, private individuals, or allowed private PII inference.
- Respect privacy and only use public, aggregated, or business-directory data, not private personal records.
- Avoid biased or discriminatory sourcing language; focus on community, diaspora, and publicly available cultural/business data.

## Suggested Usage
This prompt may be consumed by an internal LLM agent or code generation pipeline to:

- plan data harvesting from free sources
- produce curated lists of APIs and open datasets
- build structured schema mappings for ingestion
- validate whether the selected sources comply with usage and policy requirements

## Example Output Format

```json
{
  "source": "OpenStreetMap / Overpass API",
  "url": "https://overpass-api.de/api/interpreter",
  "data_types": ["restaurants", "temples", "community centers"],
  "free_open": true,
  "api_available": true,
  "notes": "Open, global POI data with tags for cuisine and place of worship.",
  "policy_check": {
    "terms_ok": true,
    "privacy_ok": true,
    "no_scraping_prohibited_site": true
  }
}
```

## Policy Compliance Checklist

- [ ] Only free, open, or public data sources are recommended.
- [ ] Proprietary APIs are only included if free-tier developer access is available.
- [ ] No direct website scraping is suggested unless the source explicitly permits it.
- [ ] Sensitive PII or private personal records are not targeted.
- [ ] Data sources are appropriate for community, business, demographic, or religious information.
- [ ] Recommendations are phrased with respect for privacy and fairness.
