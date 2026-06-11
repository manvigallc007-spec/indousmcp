# Indian–American Diaspora MCP Server

Agent-first, agent-only data layer for the Indian-American diaspora. **Phase 1: Indian
restaurants (USA).** This repo is the walking skeleton from the architecture blueprint:

- **MCP server** exposing the 3 core capabilities (`get_indian_restaurants`,
  `get_restaurant_details`, `search_restaurants_by_text`) plus outreach tools
  (`find_unclaimed_restaurants`, `draft_claim_outreach`) and `submit_correction`.
- **Data pipeline**: scrape → raw → clean/enrich/score → approval queue → canonical table →
  versioning.
- **One real scraper**: OpenStreetMap Overpass (public, ODbL-licensed, no login, ToS-safe).
- **Storage**: PostgreSQL (+ `pgvector` for future embedding search) via Docker Compose.

## Architecture (Phase 1)

```
 OSM Overpass ──▶ restaurant_raw ──▶ clean()+score() ──▶ approval_queue ──▶ restaurants
   (scraper)        (JSONB)            (pipeline)         (high-risk only)   (canonical)
                                                                                 │
                                                                                 ▼
                                                                        restaurant_versions
                                                                                 │
                                                                                 ▼
                                                                     MCP tools (FastMCP)
```

Low-risk new inserts are auto-applied (configurable); updates to claimed/featured listings
are routed to the human approval queue.

## Quick start

Requires Docker Desktop and Python 3.11+.

```powershell
# 1. Start Postgres (with pgvector)
docker compose up -d

# 2. Create a virtualenv and install
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .

# 3. Configure env
copy .env.example .env   # default DATABASE_URL already points at the docker container

# 4. Initialise the schema
python -m indo_usa_mcp.cli init-db

# 5. Scrape one metro from OpenStreetMap, then process raw -> canonical
python -m indo_usa_mcp.cli scrape --metro bay_area
python -m indo_usa_mcp.cli process

# 6. Inspect
python -m indo_usa_mcp.cli stats

# 7. Run the MCP server (stdio transport)
python -m indo_usa_mcp.server
```

## CLI

| Command | Purpose |
|---|---|
| `init-db` | Apply SQL migrations (extensions, tables, indexes). |
| `scrape --metro <name>` | Run the OSM scraper for a metro bbox into `restaurant_raw`. |
| `process` | Clean/score unprocessed raw rows; auto-apply low-risk, queue high-risk. |
| `approvals` | List pending approval-queue items. |
| `approve <id>` / `reject <id>` | Resolve an approval item. |
| `outreach [--limit N]` | Draft claim outreach for unclaimed restaurants (creates claim links + messages). |
| `verify-claim <token>` | Owner-side: verify a claim token and take ownership. |
| `agents` | List the registered autonomous agents. |
| `agent <name>` | Run one agent now (audited in `agent_runs`). |
| `agents-loop [--once]` | Run the scheduler (worker loop over due agents). |
| `query [--city/--text/--lat --lng/--id/...]` | Call the MCP tool functions from the terminal. |
| `seed` | Load fictional seed restaurants for local testing (no scrape needed). |
| `enrich` | Backfill region/dietary cultural tags on under-tagged restaurants. |
| `approval-digest` | Human-readable summary of the pending approval queue. |
| `feedback --id N --field F --value V` | Submit a field correction (applied by the feedback agent). |
| `scrape --metro usa` | Nationwide sweep (occasional; slower than a single metro). |
| `feature --id N [--days 30 \| --permanent]` | Mark a paid featured listing. |
| `unfeature --id N` | Remove a featured listing. |
| `backfill-embeddings [--all]` | (Re)compute embeddings for canonical rows. |
| `stats` | Row counts and coverage summary. |

## Monetization & delivery

- **Featured listings** (`feature`/`unfeature`) — a paid tier; effectively-featured rows
  (flagged and within their `featured_until` window) surface first in every tool result.
- **Outreach email delivery** — optional and zero-cost: set Gmail SMTP + an app password in
  `.env` (see `.env.example`) and the Outreach Agent will auto-send claim emails to
  restaurants that have a public email; otherwise it stays draft-only.
- **Enrichment agent** — strengthens the cultural "data moat" by inferring region/dietary
  tags from restaurant names (free, keyword-based).

Coverage spans 15 metros (Bay Area, NYC/NJ, Dallas, Houston, Chicago, LA, Seattle, Atlanta,
Phoenix, Austin, Boston, Philadelphia, Raleigh, Detroit, Central NJ) plus an on-demand
**nationwide** sweep (`scrape --metro usa`).

WhatsApp outreach is delivered as free **click-to-send `wa.me` links** (message pre-filled);
true auto-send WhatsApp needs a paid API and is intentionally not used.

## Trying it without a live scrape

```powershell
python -m indo_usa_mcp.cli init-db
python -m indo_usa_mcp.cli seed     # 12 fictional restaurants across the 5 metros
python -m indo_usa_mcp.cli stats
```

Then exercise the MCP tools (e.g. `get_indian_restaurants` near the Bay Area, or
`search_restaurants_by_text "vegetarian dosa"`).

## Semantic search

`search_restaurants_by_text` ranks by embedding cosine distance (pgvector `<=>`) when an
embedding provider is configured, falling back to trigram otherwise. Providers
(`EMBEDDING_PROVIDER`):

- **`hashing`** (default) — deterministic feature-hashing, **zero extra dependencies**.
  Lexical similarity; good enough to exercise the full vector path anywhere.
- **`sentence_transformers`** — real semantics via `all-MiniLM-L6-v2` (384-dim).
  Opt-in: `pip install sentence-transformers` (pulls torch), then
  `python -m indo_usa_mcp.cli backfill-embeddings --all`.
- **`none`** — disable; search uses trigram only.

Embeddings are written automatically on every canonical insert/update; `backfill-embeddings`
repopulates existing rows after changing providers.

## Outreach & claiming (blueprint §7)

```powershell
# Draft claim messages + single-use claim links for unclaimed restaurants
python -m indo_usa_mcp.cli outreach --limit 10

# Later, an owner verifies their claim token (normally via the claim web page)
python -m indo_usa_mcp.cli verify-claim <token> --email owner@example.com
```

The Outreach Agent finds unclaimed restaurants (skipping anything with an open claim or
contacted within `OUTREACH_COOLDOWN_DAYS`), creates a single-use claim token + link, and
drafts an honest, opt-out-friendly message per restaurant. Messages are **not auto-sent** —
delivery needs channel integrations, and chains / featured / high-value targets are flagged
`requires_human`. Once an owner verifies, `restaurants.is_claimed` flips to true and future
scraper updates to that listing are routed to the approval queue. Agents can drive this via
the `find_unclaimed_restaurants` and `draft_claim_outreach` MCP tools.

## Autonomous agents (blueprint §6)

Each agent wraps a pipeline step, is idempotent, and writes a full audit row to
`agent_runs` (errors captured, never half-written canonical data).

| Agent | Does |
|---|---|
| `discovery` | Reports metro coverage and proposes scrape targets. |
| `scraper` | Runs every scraper across every metro into `restaurant_raw`. |
| `cleaner` | Processes raw → canonical via clean/score/approval. |
| `outreach` | Drafts claim outreach for eligible unclaimed restaurants. |
| `monitoring` | Detects anomalies (backlogs, scraper failures, stale data) → `agent_alerts`. |
| `submission` | Submits the MCP to directories (manual stub for now). |

```powershell
python -m indo_usa_mcp.cli agents              # list agents
python -m indo_usa_mcp.cli agent scraper       # run one, audited
python -m indo_usa_mcp.cli agents-loop --once  # one scheduler pass (scrape→clean→monitor…)
python -m indo_usa_mcp.agents.scheduler        # long-lived scheduler (VPS worker)
```

### Data sources

Two independent public scrapers feed the pipeline: `osm_overpass` (OpenStreetMap, ODbL)
and `wikidata` (Wikidata SPARQL, CC0). Pick one with `scrape --source <name>`; the
Scraper Agent runs both.

## Connecting an MCP client

Point any MCP client (Claude Desktop, etc.) at:

```json
{
  "mcpServers": {
    "indo-usa-diaspora": {
      "command": "python",
      "args": ["-m", "indo_usa_mcp.server"],
      "env": { "DATABASE_URL": "postgresql://diaspora:diaspora@localhost:5433/diaspora" }
    }
  }
}
```

## Deployment (VPS, blueprint §10)

The full hosted stack — Postgres + MCP server (HTTP) + agent worker — is in
[docker-compose.prod.yml](docker-compose.prod.yml):

```powershell
$env:POSTGRES_PASSWORD = "choose-a-strong-password"
docker compose -f docker-compose.prod.yml up -d --build
```

- **server** runs migrations (idempotent) then serves MCP over `streamable-http` on `:8000`.
- **worker** runs the agent scheduler (scrape → clean → monitor …); it waits for the schema
  before starting, so service start order doesn't matter.
- **db** stays on the internal network (not published).

Put a TLS-terminating reverse proxy (Caddy/nginx/Traefik) in front of `:8000` for HTTPS,
and add a firewall + scheduled `pg_dump` backups. The MCP endpoint is `https://<host>/mcp`.

## Checking it with MCP Inspector

The standard visual way to exercise the tools:

```powershell
# stdio (local)
npx @modelcontextprotocol/inspector .\.venv\Scripts\python.exe -m indo_usa_mcp.server

# or point the Inspector at a running HTTP server: http://localhost:8000/mcp
```

## Guardrails honoured

- Public data only (OSM/ODbL), no login-required scraping, no personal data, rate-limited.
- Confidence scoring, soft deletes, full version history.
- Human approval for high-risk updates; `is_featured` is an explicit, visible flag.

## Status / roadmap

Phase 1 is implemented and runs end-to-end: schema + versioning + approval queue, the
pipeline, two scrapers (OSM + Wikidata), all 5 MCP tools, semantic (pgvector) search,
outreach & claiming, six autonomous agents with a scheduler, seed fixtures, and a hosted
deployment stack. Remaining "last mile": real outreach channel delivery, a claim web page,
the Approval-Assistant + Feedback agents, monetization logic, and production hardening
(HTTPS, backups). Each future vertical (temples, events, groceries…) gets its own
table/scrapers/tools but shares this infra.
