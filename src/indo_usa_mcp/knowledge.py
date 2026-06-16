"""Per-vertical knowledge base (RAG over documents) — reuses pgvector + the existing embeddings.

Documents (listings, web-page text, curated culture/immigration articles, FAQs) are chunked and
embedded into kb_chunks; retrieval is cosine similarity over pgvector, filtered by vertical. This
powers Dost's free-form answers ("how is Pongal celebrated?", "H-1B basics") instead of always
returning listing cards.

Embeddings are reused from embeddings.py (no second model). When embeddings are disabled (hashing
'none' / not configured) the store still ingests text and retrieval degrades to an ILIKE match.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

from . import db, embeddings

# ~400-500 tokens per chunk (≈4 chars/token). Small enough for precise retrieval, big enough to
# carry a coherent idea. Listings are tiny (one chunk); articles/web pages split into several.
_CHUNK_CHARS = 1600
_MAX_PARA_CHARS = 1600


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def chunk_text(text: str) -> list[str]:
    """Split prose into retrieval-sized chunks, preferring paragraph boundaries."""
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= _CHUNK_CHARS:
        return [text]
    paras = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    chunks: list[str] = []
    cur = ""
    for p in paras:
        # a single oversized paragraph: hard-window it
        if len(p) > _MAX_PARA_CHARS:
            if cur:
                chunks.append(cur)
                cur = ""
            for i in range(0, len(p), _CHUNK_CHARS):
                chunks.append(p[i:i + _CHUNK_CHARS])
            continue
        if cur and len(cur) + len(p) + 2 > _CHUNK_CHARS:
            chunks.append(cur)
            cur = p
        else:
            cur = f"{cur}\n\n{p}".strip()
    if cur:
        chunks.append(cur)
    return chunks


def upsert_document(*, source_type: str, source_ref: str, content: str,
                    vertical: str | None = None, title: str | None = None,
                    url: str | None = None, lang: str = "en") -> dict[str, Any]:
    """Idempotently store a document + its embedded chunks. Re-embeds only when content changed."""
    content = (content or "").strip()
    if not content:
        return {"ok": False, "reason": "empty"}
    h = _hash(content)
    existing = db.query_one(
        "SELECT id, content_hash FROM kb_documents WHERE source_type = %s AND source_ref = %s",
        (source_type, source_ref))
    if existing and existing["content_hash"] == h:
        return {"ok": True, "unchanged": True, "document_id": existing["id"]}

    if existing:
        doc_id = existing["id"]
        db.execute("UPDATE kb_documents SET vertical = %s, title = %s, url = %s, lang = %s, "
                   "content = %s, content_hash = %s, updated_at = now() WHERE id = %s",
                   (vertical, title, url, lang, content, h, doc_id))
        db.execute("DELETE FROM kb_chunks WHERE document_id = %s", (doc_id,))
    else:
        row = db.query_one(
            "INSERT INTO kb_documents (vertical, source_type, source_ref, title, url, lang, "
            "content, content_hash) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
            (vertical, source_type, source_ref, title, url, lang, content, h))
        doc_id = row["id"]

    chunks = chunk_text(content)
    use_emb = embeddings.enabled()
    for i, ch in enumerate(chunks):
        if use_emb:
            vec = embeddings.to_vector_literal(embeddings.embed(ch))
            db.execute("INSERT INTO kb_chunks (document_id, vertical, chunk_index, text, embedding) "
                       "VALUES (%s,%s,%s,%s,%s::vector)", (doc_id, vertical, i, ch, vec))
        else:
            db.execute("INSERT INTO kb_chunks (document_id, vertical, chunk_index, text) "
                       "VALUES (%s,%s,%s,%s)", (doc_id, vertical, i, ch))
    return {"ok": True, "document_id": doc_id, "chunks": len(chunks), "updated": bool(existing)}


def search(query: str, *, vertical: str | None = None, limit: int = 6) -> list[dict]:
    """Top-k knowledge chunks for a question, optionally scoped to a vertical. Each row carries the
    chunk text + its source document's title/url so the answer can cite it."""
    q = (query or "").strip()
    if not q:
        return []
    if not embeddings.enabled():
        params: list[Any] = [f"%{q}%"]
        vfilter = ""
        if vertical:
            vfilter = "AND c.vertical = %s "
            params.append(vertical)
        params.append(limit)
        return db.query(
            "SELECT c.text, c.vertical, d.title, d.url, d.source_type FROM kb_chunks c "
            "JOIN kb_documents d ON d.id = c.document_id WHERE c.text ILIKE %s " + vfilter +
            "LIMIT %s", params)

    qv = embeddings.to_vector_literal(embeddings.embed(q))
    params = [qv]
    vfilter = ""
    if vertical:
        vfilter = "AND c.vertical = %s "
        params.append(vertical)
    params.append(limit)
    return db.query(
        "SELECT c.text, c.vertical, d.title, d.url, d.source_type, "
        "(c.embedding <=> %s::vector) AS dist FROM kb_chunks c "
        "JOIN kb_documents d ON d.id = c.document_id "
        "WHERE c.embedding IS NOT NULL " + vfilter + "ORDER BY dist LIMIT %s", params)


# ----------------------------------------------------------------- ingestion from listings
def _listing_text(vertical: str, r: dict) -> str:
    parts = [r.get("name"), r.get("description")]
    loc = ", ".join(x for x in (r.get("city"), r.get("state")) if x)
    if loc:
        parts.append(f"Location: {loc}.")
    if r.get("tags"):
        parts.append("Tags: " + ", ".join(r["tags"]) + ".")
    h = r.get("hours_json")
    raw = h.get("raw") if isinstance(h, dict) else None
    if raw:
        parts.append(f"Hours: {raw}.")
    if r.get("festival_specials"):
        parts.append(f"Festival specials: {r['festival_specials']}.")
    return "\n".join(str(p) for p in parts if p)


def index_listings(vertical: str, limit: int | None = None) -> dict[str, Any]:
    """Ingest one vertical's active listings into the KB (so Dost can talk about them in prose)."""
    from . import verticals
    table = verticals._table(vertical)
    sql = f"SELECT * FROM {table} WHERE deleted_at IS NULL AND is_active ORDER BY id"
    if limit:
        sql += f" LIMIT {int(limit)}"
    n = changed = 0
    for r in db.query(sql):
        res = upsert_document(source_type="listing", source_ref=f"{vertical}:{r['id']}",
                              content=_listing_text(vertical, r), vertical=vertical,
                              title=r.get("name"), url=r.get("website"))
        n += 1
        if res.get("ok") and not res.get("unchanged"):
            changed += 1
    return {"vertical": vertical, "scanned": n, "indexed": changed}


def index_all_listings(limit_per: int | None = None) -> dict[str, Any]:
    from . import verticals
    out: dict[str, Any] = {"by_vertical": {}, "total_indexed": 0}
    for v in verticals.VERTICALS:
        if v == "events":
            continue
        try:
            res = index_listings(v, limit=limit_per)
        except Exception as exc:
            out["by_vertical"][v] = {"error": str(exc)}
            continue
        out["by_vertical"][v] = res
        out["total_indexed"] += res.get("indexed", 0)
    return out


def stats() -> dict[str, Any]:
    def scalar(sql: str) -> int:
        row = db.query_one(sql)
        return int(list(row.values())[0]) if row else 0

    return {
        "documents": scalar("SELECT count(*) FROM kb_documents"),
        "chunks": scalar("SELECT count(*) FROM kb_chunks"),
        "embedded_chunks": scalar("SELECT count(*) FROM kb_chunks WHERE embedding IS NOT NULL"),
        "by_source": db.query(
            "SELECT source_type, count(*) AS n FROM kb_documents GROUP BY source_type ORDER BY n DESC"),
        "by_vertical": db.query(
            "SELECT COALESCE(vertical, '(general)') AS vertical, count(*) AS n FROM kb_documents "
            "GROUP BY vertical ORDER BY n DESC"),
    }
