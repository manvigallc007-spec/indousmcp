# Scaling & lift-and-shift

Namaste America is built to move to a bigger machine (or managed cloud) with **no code changes** —
everything host-specific is environment-driven, and the app processes are stateless. This is the
operator's guide to growing it.

## Shape of the system

Five processes (see `docker-compose.prod.yml`), all from the **same image**:

| Process | Command | State | Scale |
|---|---|---|---|
| `db` | Postgres 16 + `pgvector` | **stateful** (the only stateful part) | vertical / managed |
| `server` | `python -m indo_usa_mcp.server` (MCP, :8000) | stateless | horizontal (N replicas) |
| `web` | `python -m indo_usa_mcp.web` (chat + API + admin, :8080) | stateless | horizontal (N replicas) |
| `worker` | `python -m indo_usa_mcp.agents.scheduler` (agents) | stateless, **singleton** | keep **1** |
| `backup` | daily `pg_dump` | — | drop when using managed PG backups |

Sessions are signed cookies (`SECRET_KEY`), not server memory — so `web`/`server` scale horizontally
behind a load balancer **as long as every replica shares the same `SECRET_KEY`**.

## Lift-and-shift checklist

1. **Database** — point the app at any Postgres via a single env var:
   ```
   DATABASE_URL=postgresql://user:pass@host:5432/diaspora
   ```
   (or leave it blank and set `POSTGRES_HOST/PORT/USER/PASSWORD/DB` — the password is URL-encoded in
   code, so any characters are safe). The DB must have the **`vector`** (pgvector) and **`pg_trgm`**
   extensions available; `cli init-db` creates them and applies all `sql/*.sql` migrations idempotently.
2. **Managed Postgres** (RDS / Cloud SQL / Neon / Supabase): create the instance, ensure pgvector is
   enabled, set `DATABASE_URL`, then drop the `db` + `backup` services from compose (the provider does
   backups + HA). Nothing else changes.
3. **Run migrations once** on deploy: `python -m indo_usa_mcp.cli init-db`. It's idempotent
   (`CREATE ... IF NOT EXISTS`), but with many replicas run it as a **one-off job**, not in every
   replica's start command, to avoid startup races.
4. **Stateless web/MCP**: run as many `web` and `server` replicas as you need behind a load balancer.
   Share `SECRET_KEY`, `DATABASE_URL`, and the LLM/SMTP/Stripe env across them.
5. **Keep the worker a singleton.** The scheduler is a timer loop; two copies would double-scrape and
   double-send outreach. Run exactly **one** `worker`. (If you ever need HA for it, add a simple
   advisory-lock leader election — not built yet.)
6. **Connection pooling**: when you run several web/server replicas against managed PG, put
   **PgBouncer** (transaction pooling) in front so you don't exhaust connections.

## Memory / CPU notes

- **Embeddings** (`EMBEDDING_PROVIDER`):
  - `hashing` — zero extra RAM, no model download, decent keyword-ish recall. Use it on tiny boxes.
  - `fastembed` — real 384-dim semantic vectors (ONNX, no torch). Downloads a ~130 MB model and uses
    roughly **300–500 MB RAM per process** that embeds. Use it once you have the headroom (it's the
    compose default for `server`/`worker`).
  - The `embedding` columns are `vector(384)` regardless of provider, **but the two spaces are not
    compatible** — if you switch provider, re-embed (`cli enhance <vertical>` / re-run the cleaners)
    so old and new vectors match.
- Postgres is the main RAM consumer at scale; give it the box's bulk and tune `shared_buffers` /
  `work_mem`. The pgvector + `pg_trgm` GIN indexes are already created per table.

## When read traffic grows (agents hammering search)

- Add Postgres **read replicas** and send the read-only paths (MCP search tools, `/api/v1/search`,
  `/browse`) to a replica. (The code uses one `DATABASE_URL` today; routing reads to a replica is a
  future addition — the queries are already read-only and safe to replicate.)
- Cache the hottest queries at the edge / a reverse proxy; API + browse responses are cacheable.
- The per-IP rate limits (`CHAT_RATE_PER_MIN`, `API_RATE_PER_MIN`) are in-process; with multiple
  replicas move them to a shared store (e.g. Redis) if you need a global cap.

## Monetization provision (charging agents — dormant)

Per-agent usage is **already counted**: every MCP tool call and `/api/v1/search` is logged to
`tool_log` with a `client` id (an API-key/agent header, or the IP). See `metering.py` and the admin
**Traffic** view (`usage_by_client`).

To start charging for retrieval later, flip one flag — no request-path rewrite needed:

```
AGENT_METERING_ENABLED=true
AGENT_FREE_MONTHLY_QUOTA=1000
```

`metering.within_quota()` is already wired into `/api/v1/search` (and is a no-op while the flag is
off). When enabled, agents over their monthly free quota get `429 quota_exceeded`; wire your billing
(e.g. Stripe metered prices, already a dependency) to the same `usage_by_client` counts. Agents
identify themselves with `X-API-Key:` / `X-Agent-Id:` / `Authorization: Bearer <key>`.

## Backups & safety

- Self-hosted: the `backup` service writes a gzipped `pg_dump` daily (keeps 14). Managed PG: use the
  provider's automated backups + PITR and remove `backup`.
- Data lifecycle is **decay, never hard-delete** (see `lifecycle.py`): stale/low-quality rows are
  deactivated/archived reversibly, so scaling mistakes are recoverable.
