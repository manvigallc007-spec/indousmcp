"""Runtime configuration, loaded from environment / .env."""

from __future__ import annotations

from urllib.parse import quote

from pydantic_settings import BaseSettings, SettingsConfigDict

# Free / OpenAI-compatible LLM presets. Selecting one by name (LLM_PROVIDER=groq) fills in the
# base URL + a sensible default model + tool-calling capability, so enabling a chatbot LLM is
# just LLM_PROVIDER + LLM_API_KEY. Any field can still be overridden explicitly via env.
#  - ollama: self-hosted, truly $0 forever, slow on CPU. Key is ignored ("ollama").
#  - groq:   free tier, ~1s, no credit card. Fast + good quality. Needs a free LLM_API_KEY.
#  - gemini: Google AI Studio free tier, OpenAI-compatible endpoint. Needs a free LLM_API_KEY.
_LLM_PRESETS: dict[str, dict] = {
    "ollama": {"llm_base_url": "http://localhost:11434/v1",
               "llm_model": "gemma2:2b", "llm_use_tools": False},
    "groq": {"llm_base_url": "https://api.groq.com/openai/v1",
             "llm_model": "llama-3.3-70b-versatile", "llm_use_tools": True},
    "gemini": {"llm_base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
               "llm_model": "gemini-2.0-flash", "llm_use_tools": False},
}


# Default SELECT for the caterbid import — maps the caterbid "Caterer" table (Prisma schema, so
# identifiers are CamelCase + quoted) to our restaurant fields. cuisines is a JSONB array, flattened
# to a comma list. Only active caterers. Override via CATERBID_QUERY if needed; expected aliases:
# source_id, name, address_full, city, state, phone, email, website, cuisine_type, lat, lng.
_CATERBID_DEFAULT_QUERY = """
SELECT id AS source_id,
       "businessName" AS name,
       NULLIF(concat_ws(', ', "streetAddress", city, state), '') AS address_full,
       city, state,
       COALESCE(NULLIF(phone, ''), "importedPhone") AS phone,
       email, website,
       CASE WHEN jsonb_typeof("cuisines") = 'array'
            THEN (SELECT string_agg(elem, ', ') FROM jsonb_array_elements_text("cuisines") AS elem)
            ELSE NULL END AS cuisine_type,
       lat, lng
FROM "Caterer"
WHERE active = true
""".strip()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Either set DATABASE_URL directly, or leave it blank and provide the POSTGRES_* parts
    # below — the parts are URL-encoded, so passwords may contain @ : / # etc. safely.
    database_url: str = ""
    postgres_user: str = "diaspora"
    postgres_password: str = "diaspora"
    postgres_host: str = "localhost"
    postgres_port: int = 5433  # dev default (docker maps 5433->5432); prod sets 5432
    postgres_db: str = "diaspora"

    @property
    def effective_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        user = quote(self.postgres_user, safe="")
        pw = quote(self.postgres_password, safe="")
        return (f"postgresql://{user}:{pw}@{self.postgres_host}:"
                f"{self.postgres_port}/{self.postgres_db}")

    # Pipeline behaviour
    auto_approve_low_risk: bool = True
    auto_approve_min_confidence: float = 0.6

    # Events: public iCalendar (.ics) feed URLs the event agent ingests (comma-separated).
    event_ical_feeds: str = ""

    # Scraper politeness
    overpass_url: str = "https://overpass-api.de/api/interpreter"
    scraper_user_agent: str = "indo-usa-diaspora-mcp/0.1"
    # NPPES (free CMS NPI registry) API base. NOTE the host is npiregistry.cms.HHS.gov — the
    # cms.gov variant does NOT resolve. Configurable so a future move is an env change, not code.
    nppes_api_url: str = "https://npiregistry.cms.hhs.gov/api/"
    # Optional free Socrata app token (higher SODA API rate limits). The open-data API works
    # without one; set it only if you register for higher throughput. Token via env only.
    socrata_app_token: str = ""
    # Optional free US Census API key (https://api.census.gov/data/key_signup.html). Low-volume
    # demographics pulls work without one; set it to be safe under rate limits.
    census_api_key: str = ""
    scraper_timeout_seconds: int = 180

    # caterbid.co import — the operator's OWN restaurant directory, on the same VPS. We read its
    # Postgres directly over the shared docker network (NO website scraping — it's our data). Blank
    # = disabled. All rows land in `restaurants`, tagged 'catering' (every caterbid business caters),
    # South-Asian cuisines kept. If caterbid's schema differs from the default query, set
    # CATERBID_QUERY to a SELECT that aliases columns to our names:
    #   source_id, name, address_full, city, state, phone, email, website, cuisine_type, lat, lng
    caterbid_database_url: str = ""
    caterbid_query: str = ""   # blank -> _CATERBID_DEFAULT_QUERY (so compose can pass an empty default)
    caterbid_site_url: str = "https://caterbid.co"

    @property
    def effective_caterbid_query(self) -> str:
        return self.caterbid_query.strip() or _CATERBID_DEFAULT_QUERY

    # H-1B intelligence from the free DOL OFLC LCA disclosure data (public domain). Blank = disabled.
    # Point this at the current fiscal-year file from dol.gov (URL or local path). The annual file is
    # large — prefer a single quarter, or convert to .csv first (the .csv reader streams in constant
    # memory; .xlsx needs openpyxl + more RAM). dol_h1b_fiscal_year just labels the output.
    dol_h1b_disclosure_url: str = ""
    dol_h1b_fiscal_year: str = ""

    # IRS Exempt-Org Business Master File (free nonprofit CSVs) -> Indian temples & community orgs.
    # Blank irs_eo_urls = the 4 standard IRS files. The IrsEoAgent stays DORMANT until irs_eo_enabled;
    # `cli irs-import` runs it manually anytime (streams ~200MB total, keeps only clearly-Indian orgs).
    irs_eo_urls: str = ""
    irs_eo_enabled: bool = False

    # Public claim web page (owner-facing)
    web_host: str = "0.0.0.0"
    web_port: int = 8080

    # Admin dashboard + sessions/magic-links. Blank admin_password disables /admin.
    admin_username: str = "admin"
    admin_password: str = ""
    secret_key: str = "dev-insecure-change-me"   # signs session cookies + magic-links
    # Mark session cookies Secure (HTTPS-only). Flip True once the site is served over TLS (Caddy).
    session_https_only: bool = False
    report_email: str = ""                       # daily report recipient (defaults to contact)
    magic_link_ttl_minutes: int = 30
    # Google Analytics 4 measurement ID, e.g. G-XXXXXXXXXX. Blank = no tracking. NOT a secret —
    # it's public in the page source; injected into every public page's <head> when set.
    google_analytics_id: str = ""
    # Let the SubmissionReviewAgent auto-publish obviously-good, complete, clearly-Indian business
    # submissions (ambiguous ones still wait for a human). Set false to require manual approval for all.
    auto_approve_submissions: bool = True
    # Let the ContactReplyAgent auto-SEND replies to clearly-routine, non-sensitive messages (a copy
    # is stored + emailed to you). Needs SMTP + an LLM; sensitive topics always wait for approval.
    auto_reply_routine: bool = True
    # Community reviews (visitor 1-5 star ratings + optional text on a listing). Moderated: a clean
    # review is auto-published; spam/abusive/off-topic ones are held ('pending') and escalated to
    # Admin -> Reviews. Flip review_auto_publish=False to hold ALL reviews for manual approval. The
    # rolled-up community score lives in separate columns and never clobbers the web-harvested rating.
    # Reuses the same captcha + per-IP rate-limit that protect the contact/submission forms.
    reviews_enabled: bool = True
    review_auto_publish: bool = True
    review_min_chars: int = 0          # 0 = a star-only rating (no text) is allowed
    review_max_chars: int = 2000
    reviews_per_ip_per_day: int = 8    # across all listings (abuse guard)
    # Google sign-in for the business-owner portal (optional; magic-link still works without it).
    # Create an OAuth 2.0 Web client at console.cloud.google.com -> APIs & Services -> Credentials.
    # Authorized redirect URI = <PUBLIC_WEB_URL>/portal/google/callback. Secrets via env only.
    google_oauth_client_id: str = ""
    google_oauth_client_secret: str = ""

    @property
    def google_oauth_enabled(self) -> bool:
        return bool(self.google_oauth_client_id and self.google_oauth_client_secret)

    # Captcha for the business-registration form. By default a free, self-contained signed math
    # challenge is used (no account, no external call). Optionally set Cloudflare Turnstile keys
    # (free at dash.cloudflare.com -> Turnstile) for a stronger widget; blank = use the math captcha.
    turnstile_site_key: str = ""
    turnstile_secret_key: str = ""

    @property
    def turnstile_enabled(self) -> bool:
        return bool(self.turnstile_site_key and self.turnstile_secret_key)
    # Public base URL of the web app (for Stripe redirect URLs), e.g. https://yourdomain.com
    public_web_url: str = "http://localhost:8080"
    # IndexNow: instantly notify Bing/Copilot/Yandex when listings change (free, no account). Set
    # INDEXNOW_KEY to a random 16-32 char hex string; we serve it at /{key}.txt and ping on updates.
    # Blank = disabled (all IndexNow calls are no-ops). NOT a secret — the key file is public.
    indexnow_key: str = ""

    # Payments (Stripe) — optional. Blank secret key = payments disabled (manual featuring).
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_price_cents: int = 3000      # $30.00 for a featured listing
    stripe_currency: str = "usd"
    featured_days: int = 30
    # Sell Featured placement? Kept OFF until a city+vertical has provable traffic — Stripe
    # plumbing stays intact, but the "Get Featured" buttons + /upgrade are hidden meanwhile.
    featured_sales_enabled: bool = False

    @property
    def payments_enabled(self) -> bool:
        return bool(self.stripe_secret_key)

    # Claiming a listing is FREE (drives adoption + the verified-owner badge). Flip on only
    # if/when you decide to charge for claims — the paid checkout itself is not built yet.
    paid_claim_enabled: bool = False

    @property
    def featured_for_sale(self) -> bool:
        return bool(self.stripe_secret_key and self.featured_sales_enabled)

    # Human chatbot front-end (/chat). Pluggable LLM via the OpenAI-compatible chat API.
    #   llm_provider = "search"           -> no LLM, templated semantic-search replies (default, $0)
    #   llm_provider = "ollama"|"groq"|"gemini" -> a preset (see _LLM_PRESETS): just add LLM_API_KEY
    #   llm_provider = "llm"              -> fully custom: set llm_base_url + llm_model yourself
    # The API key NEVER lives in code — set LLM_API_KEY via .env / environment only.
    #   Quick start (free, fast): LLM_PROVIDER=groq + LLM_API_KEY=<your free Groq key>.
    #   Zero-cost-forever: LLM_PROVIDER=ollama (self-hosted; slower on CPU, key ignored).
    chat_enabled: bool = True
    llm_provider: str = "search"
    llm_base_url: str = "http://localhost:11434/v1"
    llm_api_key: str = "ollama"
    llm_model: str = "llama3.1"
    # True = function/tool-calling (needs a tool-capable model). False = grounded RAG: search
    # first, then one LLM call to phrase the answer — works with Gemma & any small model, and
    # is faster on a no-GPU VPS. A preset sets a sensible default; override here if needed.
    llm_use_tools: bool = True
    llm_timeout_s: int = 60

    @property
    def _llm_preset(self) -> dict:
        return _LLM_PRESETS.get(self.llm_provider.strip().lower(), {})

    @property
    def llm_enabled(self) -> bool:
        """Any non-'search' provider means a real LLM should be used."""
        return self.llm_provider.strip().lower() != "search"

    def _llm_resolved_str(self, field: str) -> str:
        """For a preset provider: an explicit, NON-EMPTY env value wins; otherwise the preset's
        value. (Blank is treated as 'use the preset' — compose can inject empty defaults.)
        For 'search'/'llm' there's no preset, so the explicit field is used as-is."""
        preset = self._llm_preset
        if preset:
            explicit = getattr(self, field)
            if field in self.model_fields_set and explicit:
                return explicit
            return preset[field]
        return getattr(self, field)

    @property
    def effective_llm_base_url(self) -> str:
        return self._llm_resolved_str("llm_base_url")

    @property
    def effective_llm_model(self) -> str:
        return self._llm_resolved_str("llm_model")

    @property
    def effective_llm_use_tools(self) -> bool:
        # A preset knows the right mode for its model (Groq tool-calls; Gemma/Gemini grounded).
        preset = self._llm_preset
        return bool(preset["llm_use_tools"]) if preset else self.llm_use_tools
    chat_rate_per_min: int = 20            # per-IP request cap on the chat API (abuse guard)
    api_rate_per_min: int = 60             # per-IP request cap on the public read-only JSON API

    # Agent metering (future monetization — points 12 & 15). DORMANT by default: every MCP/API call
    # is already logged per-client, so usage is COUNTABLE now (see metering.py + the admin Traffic
    # view). Flip this on later to ENFORCE a per-agent monthly quota (charge for retrieval beyond
    # it). Off = zero behavior change (within_quota() always returns True).
    agent_metering_enabled: bool = False
    agent_free_monthly_quota: int = 1000   # calls/agent/month before metering would gate
    # When the directory has no answer but the question is relevant to Indian-American life in
    # the USA, fetch a general-info answer from free, key-less web sources (Wikipedia + DuckDuckGo)
    # and have the LLM phrase it. Answers are labelled "general info, not from our directory".
    web_fallback_enabled: bool = True
    # When the browser won't share GPS, approximate the visitor's area from their IP (free,
    # no-key, city-level) so the chatbot can still show nearest-first results. Falls back to
    # asking for a city if this is off or fails. Set False to disable the IP lookup entirely.
    geoip_enabled: bool = True

    # Text-to-speech for the chatbot's spoken replies.
    #   "browser" -> the device's free on-device Web Speech API (default, $0). Hindi/Telugu voice
    #                quality depends on what the visitor's OS ships; we pick the best one available.
    # PROVISION ONLY: set this to a paid native-voice provider later (e.g. "google" / "azure" /
    # "elevenlabs") for natural Hindi/Telugu narration. The chat page reads this value, so wiring a
    # server-side /chat/tts route is a pure addition — no UI rework. Keys live in env only, never code.
    tts_provider: str = "browser"

    # MCP server transport
    # "stdio" for local clients (Claude Desktop), "streamable-http" for a hosted service.
    mcp_transport: str = "stdio"
    mcp_host: str = "0.0.0.0"
    mcp_port: int = 8000

    # Embeddings (semantic search)
    # Provider: "hashing" (zero-dep default), "fastembed" (real semantic, ONNX, no torch,
    # ~130MB model, recommended), "sentence_transformers" (heavier), "none".
    embedding_provider: str = "hashing"
    embedding_model: str = "all-MiniLM-L6-v2"          # sentence_transformers only
    fastembed_model: str = "BAAI/bge-small-en-v1.5"    # fastembed (384-dim, matches column)
    embedding_dim: int = 384                            # must match the embedding vector(N) columns

    # Branding. Real brand: Namaste America (namasteamerica.us). Dost is the chatbot's name.
    platform_name: str = "Namaste America"      # directory/platform brand shown across pages
    assistant_name: str = "Dost"                # the chatbot's name
    # One source for the friendly meaning, surfaced in chat copy + meta so non-Hindi speakers get it.
    assistant_meaning: str = "“Dost” means “friend” in Hindi & Urdu"
    assistant_tagline: str = "your friend for finding Indian America"
    platform_tagline: str = "Your guide to Indian America"

    # Outreach & claiming
    claim_base_url: str = "https://yourdomain.com/claim"
    outreach_contact_email: str = "manvigallc007@gmail.com"
    # Don't re-contact the same restaurant within this many days (anti-spam).
    outreach_cooldown_days: int = 21
    # CAN-SPAM requires a valid physical postal address in every commercial email.
    # Auto-send stays OFF until this is set (see `outreach_compliant`).
    outreach_postal_address: str = ""
    # Slow ramp: max messages auto-sent per day across the whole platform.
    outreach_daily_send_cap: int = 15

    @property
    def outreach_compliant(self) -> bool:
        """Auto-send is allowed only when delivery AND CAN-SPAM prerequisites are met:
        SMTP configured + a physical postal address present. Otherwise outreach stays
        draft-only (messages are prepared for human review but never sent)."""
        return bool(self.email_enabled and self.outreach_postal_address.strip())

    # Email delivery (optional). Leave smtp_host blank to keep outreach in draft-only mode.
    # Works with free providers (e.g. Gmail SMTP + an app password): no cost.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""           # defaults to outreach_contact_email if blank
    smtp_use_tls: bool = True

    @property
    def email_enabled(self) -> bool:
        return bool(self.smtp_host and self.smtp_user and self.smtp_password)


settings = Settings()
