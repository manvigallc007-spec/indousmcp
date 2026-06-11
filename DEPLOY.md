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
Caddy gets a free Let's Encrypt cert automatically. Your MCP endpoint becomes
`https://yourdomain.com/mcp`.

**No domain yet?** Skip Caddy. The server is on `http://YOUR_VPS_IP:8000/mcp`. Lock it down
with the firewall (next step) — allow `:8000` only from IPs you trust, or only expose it
once you add a domain + HTTPS.

## 7. Firewall (recommended)

```bash
ufw allow OpenSSH
ufw allow 80
ufw allow 443
# If running WITHOUT Caddy and you must reach :8000 directly, also: ufw allow 8000
ufw enable
```
With Caddy/HTTPS, do **not** open 8000 publicly — only 80/443.

## Backups

The `backup` service writes a gzipped `pg_dump` to `/opt/diaspora/backups/` once a day and
keeps the latest 14. To restore:
```bash
gunzip -c backups/diaspora_YYYYMMDD_HHMMSS.sql.gz | \
  docker compose -f docker-compose.prod.yml exec -T db psql -U diaspora -d diaspora
```
Consider copying `backups/` off the VPS periodically (e.g. `scp`) for off-site safety.

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
