# Growth & reach — features + action checklist

Everything below is built and on `main`. The **code** ships with the next
`git pull && docker compose -f docker-compose.prod.yml up -d --build`. The **actions** at the bottom
are one-time things only you can do (accounts, keys, registry submissions).

> For the full ordered deploy + data-curation pipeline (dedupe, purge-non-usa, enrich-llm,
> backfill-embeddings, kb-seed), see the **Release runbook** in [DEPLOY.md](DEPLOY.md).

## What shipped (this round)

| Feature | What it does | Where |
| --- | --- | --- |
| **FAQPage schema** | `/faq` emits `FAQPage` JSON-LD → Google "People also ask" + AI answer engines quote it | `/faq` |
| **Best-of pages** | Curated "Best Indian `<category>` in `<City>`" ranked by rating; shareable + long-tail SEO | `/best/<vertical>/<state>/<city>` |
| **llms-full.txt** | Full plain-text knowledge export (festivals, culture, newcomer/visa/tax guides) for AI crawlers | `/llms-full.txt` |
| **IndexNow** | Pings Bing/Copilot/Yandex within minutes when listings change (hourly, via the cleaner agent) | needs `INDEXNOW_KEY` |
| **Telegram bot** | Same Dost brain (multilingual search + KB) as a bot people forward in diaspora groups | needs `TELEGRAM_BOT_TOKEN` |

Already present from before: `sitemap.xml`, `robots.txt` (AI-crawler-friendly), `llms.txt`,
`/.well-known/mcp.json`, `Event` / `LocalBusiness` / `AggregateRating` / `ItemList` / WebSite+SearchAction
schema, OG/Twitter tags, PWA.

> Note on `hreflang`: deferred on purpose. The site is content-negotiated from one URL (language via
> the `lang` cookie), so crawlers only ever see the English render and the listing data is English
> regardless. Real per-language indexing would need language-prefixed URLs (`/hi/…`, `/te/…`) — a
> separate, larger project. Not worth cosmetic tags today.

## New `.env` settings (both optional, blank = disabled)

```ini
# IndexNow — random 16-32 char hex string; we serve it at /<key>.txt and ping on changes. Public.
INDEXNOW_KEY=

# Telegram bot token from @BotFather. SECRET — keep in .env only.
TELEGRAM_BOT_TOKEN=
```

## Action checklist (one-time, only you can do these)

1. **Google Search Console** — add the property `namasteamerica.us`, verify (DNS TXT), then
   *Sitemaps → submit* `https://namasteamerica.us/sitemap.xml`.
2. **Bing Webmaster Tools** — add + verify the site (you can import from Search Console), submit the
   same sitemap. This is also what powers IndexNow on the Bing side.
3. **Enable IndexNow** — generate a random key (e.g. `python -c "import secrets;print(secrets.token_hex(16))"`),
   set `INDEXNOW_KEY` in `.env`, redeploy, then confirm `https://namasteamerica.us/<key>.txt`
   returns the key. From then on, changed listings are pushed automatically.
4. **Create the Telegram bot** — message `@BotFather` → `/newbot` → set `TELEGRAM_BOT_TOKEN` in
   `.env` → redeploy → message your bot `/start`. Then drop the bot link in diaspora WhatsApp/Telegram
   groups and add a "Chat on Telegram" link on the site.
5. **List the MCP server in registries** (biggest *agent* reach, free) — submit `https://namasteamerica.us/mcp`
   (+ point at `/.well-known/mcp.json`) to: the Anthropic MCP registry, `mcp.so`, Smithery,
   PulseMCP, and Glama.
6. **Validate rich results** — run Google's Rich Results Test on `/faq`, one `/best/...` page, and one
   `/listing/...` page; confirm FAQ / ItemList / LocalBusiness are detected.
7. **Seed the share loop** — post a few `/best/...` pages in relevant groups; they're the link people
   re-share, and they capture "best ... in ..." searches.
