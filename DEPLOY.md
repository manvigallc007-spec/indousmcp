# Deploying on a Hostinger VPS (zero extra cost)

Everything here is free, open-source, and self-hosted on your VPS. The only thing you pay
for is the Hostinger VPS itself. No managed database, no metered add-ons, no "free trial
that starts charging." Specifically:

- **Docker, PostgreSQL (pgvector), Python** — open-source, unlimited.
- **Caddy + Let's Encrypt** (HTTPS) — Let's Encrypt is a nonprofit; certificates are free
  forever and renew automatically.
- **pg_dump** backups — built into PostgreSQL.

The stack runs four containers: `db` (Postgres), `server` (MCP over HTTP), `worker`
(agent scheduler), `backup` (daily dumps); plus an optional `caddy` for HTTPS.

---

## 1. Create / prepare the VPS in hPanel

1. Hostinger **hPanel → VPS**. When choosing the OS template, pick
   **"Ubuntu 22.04 with Docker"** (Application templates) — Docker comes preinstalled.
   If you already have a plain Ubuntu VPS, install Docker once:
   ```bash
   curl -fsSL https://get.docker.com | sh
   ```
2. Note your VPS **IP address** (hPanel → VPS → Overview) and **SSH/root password**
   (hPanel → VPS → SSH access). You can use Hostinger's **Browser terminal** instead of a
   local SSH client.

## 2. Get the code onto the VPS

Either copy it up from Windows PowerShell:
```powershell
scp -r C:\Users\desiplaza\Indo-usa-mcp root@YOUR_VPS_IP:/opt/diaspora
```
…or, better, push it to a Git repo and clone on the VPS:
```bash
mkdir -p /opt && git clone <your-repo-url> /opt/diaspora
```

## 3. Configure secrets

```bash
cd /opt/diaspora
cp .env.example .env
nano .env
```
Set at least:
- `POSTGRES_PASSWORD` — a strong password.
- `DOMAIN` — only if you have a domain (see step 6); otherwise leave it.
- `CLAIM_BASE_URL`, `OUTREACH_CONTACT_EMAIL` — your real values.

Compose reads `POSTGRES_PASSWORD` and `DOMAIN` from this `.env` automatically.

## 4. Launch the stack

```bash
docker compose -f docker-compose.prod.yml up -d --build
```
This builds the image, applies the schema (idempotent), starts the MCP server on `:8000`,
the agent worker, and the daily backup loop.

## 5. Verify

```bash
docker compose -f docker-compose.prod.yml ps                 # db/server/worker/backup Up
curl -i http://localhost:8000/mcp                            # HTTP 406 = healthy MCP endpoint
docker compose -f docker-compose.prod.yml logs --tail=20 worker   # scheduler running agents
docker compose -f docker-compose.prod.yml exec db \
  psql -U diaspora -d diaspora -c "select count(*) from restaurants;"
```

Seed some test data or run a real scrape:
```bash
docker compose -f docker-compose.prod.yml exec server python -m indo_usa_mcp.cli seed
docker compose -f docker-compose.prod.yml exec server python -m indo_usa_mcp.cli scrape --metro bay_area
docker compose -f docker-compose.prod.yml exec server python -m indo_usa_mcp.cli process
```

## 6. HTTPS (only if you have a domain)

Point an A record for your domain (or a subdomain) at the VPS IP, set `DOMAIN` in `.env`,
then bring up the optional Caddy proxy:
```bash
docker compose -f docker-compose.prod.yml --profile tls up -d
```
Caddy gets a free Let's Encrypt cert automatically and routes `/mcp*` to the MCP server and
everything else (claim/manage/upgrade pages, `/stripe/webhook`) to the web app. With a
domain, also set in `.env`: `PUBLIC_WEB_URL=https://yourdomain.com` and
`CLAIM_BASE_URL=https://yourdomain.com/claim`. Endpoints become `https://yourdomain.com/mcp`
(agents) and `https://yourdomain.com/claim` (owners).

**No domain yet?** Skip Caddy. The server is on `http://YOUR_VPS_IP:8000/mcp`. Lock it down
with the firewall (next step) — allow `:8000` only from IPs you trust, or only expose it
once you add a domain + HTTPS.

## 7. Firewall (recommended)

```bash
ufw allow OpenSSH
ufw allow 80
ufw allow 443
# Direct (no Caddy): MCP server on 8000, claim web page on 8080
ufw allow 8000
ufw allow 8080
ufw enable
```
With Caddy/HTTPS, do **not** open 8000/8080 publicly — only 80/443, and route them via the
proxy. The owner-facing **claim page** runs on `:8080` (`/claim?...`); the agent MCP endpoint
is on `:8000` (`/mcp`).

## Backups

The `backup` service writes a gzipped `pg_dump` to `/opt/diaspora/backups/` once a day and
keeps the latest 14. To restore:
```bash
gunzip -c backups/diaspora_YYYYMMDD_HHMMSS.sql.gz | \
  docker compose -f docker-compose.prod.yml exec -T db psql -U diaspora -d diaspora
```
Consider copying `backups/` off the VPS periodically (e.g. `scp`) for off-site safety.

## Enabling Stripe payments (featured listings)

Optional — without it, you feature restaurants manually (`cli feature`). With it, owners
pay via Stripe Checkout and get auto-featured. Stripe charges only per sale (no monthly fee).

1. In the **Stripe Dashboard** → Developers → API keys, copy your **Secret key** (`sk_live_…`).
2. Set the public URL of your web app and the key in `/opt/diaspora/.env`:
   ```
   PUBLIC_WEB_URL=https://yourdomain.com      # or http://YOUR_VPS_IP:8080
   STRIPE_SECRET_KEY=sk_live_xxx
   STRIPE_PRICE_CENTS=3000                     # $30 per featured period
   FEATURED_DAYS=30
   ```
3. Create a **webhook** (Stripe → Developers → Webhooks → Add endpoint):
   - URL: `https://yourdomain.com/stripe/webhook` (must be reachable from the internet)
   - Event: `checkout.session.completed`
   - Copy the **Signing secret** (`whsec_…`) into `.env` as `STRIPE_WEBHOOK_SECRET`.
4. Recreate the web service:
   ```bash
   docker compose -f docker-compose.prod.yml up -d --build web
   ```

Now a claimed owner sees a **"Get Featured"** button → pays → the webhook auto-features them
(verified by Stripe signature). Test with Stripe **test mode** keys first (`sk_test_…`) and a
test card `4242 4242 4242 4242`.

## Admin dashboard & owner portal

Set these in `/opt/diaspora/.env`, then recreate the `web` service:
```
ADMIN_PASSWORD=a-strong-admin-password     # blank = /admin disabled
SECRET_KEY=a-long-random-string            # signs sessions + magic-links
REPORT_EMAIL=you@example.com               # daily report recipient (needs SMTP set)
```
```bash
docker compose -f docker-compose.prod.yml up -d --build web
```
- **Admin:** `http://YOUR_VPS_IP:8080/admin` → log in with `ADMIN_PASSWORD`. Control data,
  approvals, feedback, agents, payments, reports across all verticals.
- **Owner portal:** `http://YOUR_VPS_IP:8080/portal/login` → owners get a magic-link email
  (requires SMTP; without SMTP the link is shown on-page for testing).
- **Daily report:** emailed nightly by the `reporting` agent; on demand:
  `docker compose -f docker-compose.prod.yml exec server python -m indo_usa_mcp.cli report`.

> ⚠️ Put the **Caddy HTTPS proxy** in front before exposing `/admin` publicly, and use a strong
> `ADMIN_PASSWORD`. Admin over plain HTTP on a public IP is risky.

## Release runbook (every deploy after the first)

The ordered, idempotent steps to ship `main`. Run **on the VPS** (laptop only pushes; never commit on
the VPS). Shorthand: `DC="docker compose -f docker-compose.prod.yml"`.

**New optional `.env` settings** (blank = disabled):
```ini
INDEXNOW_KEY=            # random 16-32 hex; serves /<key>.txt, pings Bing/Copilot/Yandex on changes
TELEGRAM_BOT_TOKEN=      # from @BotFather; enables the `telegram` bot service
```
Generate an IndexNow key: `python -c "import secrets;print(secrets.token_hex(16))"`. Keep these (and
the critical `LLM_PROVIDER=groq`+`LLM_API_KEY`, `EMBEDDING_PROVIDER=fastembed`, `SECRET_KEY`,
`ADMIN_PASSWORD`, `SESSION_HTTPS_ONLY=true`, `REVIEW_AUTO_PUBLISH`) set before deploying.

```bash
# 1) Pull + rebuild (server's init-db auto-applies new migrations, incl. 043_ai_content;
#    also starts the optional `telegram` service — idle until TELEGRAM_BOT_TOKEN is set)
cd /opt/diaspora && git pull && $DC up -d --build

# 2) Curate the data (worker), in this order:
$DC exec worker python -m indo_usa_mcp.cli dedupe              # review dupes (dry-run)
$DC exec worker python -m indo_usa_mcp.cli dedupe --apply      # merge same-place duplicates
$DC exec worker python -m indo_usa_mcp.cli purge-non-usa       # review non-USA / Indian-city (dry-run)
$DC exec worker python -m indo_usa_mcp.cli purge-non-usa --apply   # remove high-confidence foreign
$DC exec worker python -m indo_usa_mcp.cli enrich-llm          # LLM descriptions + review summaries (needs Groq)
$DC exec worker python -m indo_usa_mcp.cli backfill-embeddings --all   # ONE consistent embedding pass
$DC exec worker python -m indo_usa_mcp.cli kb-seed             # curated + newcomer + festival KB
$DC exec worker python -m indo_usa_mcp.cli kb-index
# optional, slow/off-peak — sharpens "near me" + the non-USA bbox check:
$DC exec worker python -m indo_usa_mcp.cli backfill-geo --limit 500

# 3) Verify
$DC exec worker python -m indo_usa_mcp.cli agent discovery     # expect status: success
```
On the live site: English → Telugu chat works; a listing shows its photo + "% complete / Updated /
Suggest an edit" + AI description; a `/best/<v>/<state>/<city>` page renders; **Admin → Messages**
receives edit suggestions; **Admin → Agents** shows discovery = success. If `INDEXNOW_KEY` is set,
`/<key>.txt` returns the key; if Telegram is set, the bot answers `/start`.

**Off-platform (one-time, see [GROWTH.md](GROWTH.md)):** submit `sitemap.xml` to Google Search
Console + Bing; list the MCP server (`/mcp`, `/.well-known/mcp.json`) in registries (mcp.so, Smithery,
PulseMCP, Glama); validate `/faq`, a `/best/...`, and a `/listing/...` page in Google's Rich Results Test.

## Day-2 operations

```bash
# Update after code changes
git pull && docker compose -f docker-compose.prod.yml up -d --build

# Logs
docker compose -f docker-compose.prod.yml logs -f server
docker compose -f docker-compose.prod.yml logs -f worker

# Run an agent on demand
docker compose -f docker-compose.prod.yml exec server python -m indo_usa_mcp.cli agent monitoring

# Stop / start
docker compose -f docker-compose.prod.yml stop
docker compose -f docker-compose.prod.yml up -d
```

## Connecting an MCP client

Point your MCP client at the streamable-HTTP endpoint:
- With HTTPS: `https://yourdomain.com/mcp`
- Without:    `http://YOUR_VPS_IP:8000/mcp`
