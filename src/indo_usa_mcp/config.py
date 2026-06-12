"""Runtime configuration, loaded from environment / .env."""

from __future__ import annotations

from urllib.parse import quote

from pydantic_settings import BaseSettings, SettingsConfigDict


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

    @property
    def payments_enabled(self) -> bool:
        return bool(self.stripe_secret_key)

    # MCP server transport
    # "stdio" for local clients (Claude Desktop), "streamable-http" for a hosted service.
    mcp_transport: str = "stdio"
    mcp_host: str = "0.0.0.0"
    mcp_port: int = 8000

    # Embeddings (semantic search)
    # Provider: "hashing" (zero-dep default), "sentence_transformers" (opt-in, heavy), "none".
    embedding_provider: str = "hashing"
    embedding_model: str = "all-MiniLM-L6-v2"  # used only by sentence_transformers
    embedding_dim: int = 384                    # must match restaurants.embedding vector(N)

    # Outreach & claiming
    platform_name: str = "Indian Eats Directory"
    claim_base_url: str = "https://yourdomain.com/claim"
    outreach_contact_email: str = "manvigallc007@gmail.com"
    # Don't re-contact the same restaurant within this many days (anti-spam).
    outreach_cooldown_days: int = 21

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
