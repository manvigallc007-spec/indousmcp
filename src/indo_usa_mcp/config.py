"""Runtime configuration, loaded from environment / .env."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://diaspora:diaspora@localhost:5433/diaspora"

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
