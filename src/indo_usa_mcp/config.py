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
    scraper_timeout_seconds: int = 180

    # Public claim web page (owner-facing)
    web_host: str = "0.0.0.0"
    web_port: int = 8080

    # Admin dashboard + sessions/magic-links. Blank admin_password disables /admin.
    admin_password: str = ""
    secret_key: str = "dev-insecure-change-me"   # signs session cookies + magic-links
    report_email: str = ""                       # daily report recipient (defaults to contact)
    magic_link_ttl_minutes: int = 30
    # Public base URL of the web app (for Stripe redirect URLs), e.g. https://yourdomain.com
    public_web_url: str = "http://localhost:8080"

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
    # When the directory has no answer but the question is relevant to Indian-American life in
    # the USA, fetch a general-info answer from free, key-less web sources (Wikipedia + DuckDuckGo)
    # and have the LLM phrase it. Answers are labelled "general info, not from our directory".
    web_fallback_enabled: bool = True
    # When the browser won't share GPS, approximate the visitor's area from their IP (free,
    # no-key, city-level) so the chatbot can still show nearest-first results. Falls back to
    # asking for a city if this is off or fails. Set False to disable the IP lookup entirely.
    geoip_enabled: bool = True

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

    # Branding — TEMP placeholders until a real name/domain is chosen (override via env).
    platform_name: str = "DesiConnect"          # directory/platform brand shown across pages
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
