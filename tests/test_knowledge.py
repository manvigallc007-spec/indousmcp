"""Knowledge-base articles: admin moderation (pause/suspend + soft-delete + metadata-only edit).

No DB-interaction test file existed for knowledge.py before this -- real local dev DB, ZZTEST-prefixed
disposable rows, try/finally cleanup, matching tests/test_h1b.py's convention."""

import indo_usa_mcp.embeddings as emb
import indo_usa_mcp.knowledge as knowledge
from indo_usa_mcp import db

_REF = "zztest-admin-article"


def _seed_doc(**over):
    db.execute("DELETE FROM kb_documents WHERE source_ref = %s", (_REF,))
    res = knowledge.upsert_document(
        source_type="article", source_ref=_REF, content="ZZTEST distinctive kb content about dosa.",
        title="ZZTest Admin Article", url="https://example.com/zztest")
    return res["document_id"]


def test_kb_set_active_and_deleted_roundtrip():
    doc_id = _seed_doc()
    try:
        d = knowledge.get_document(doc_id)
        assert d["is_active"] is True and d["deleted_at"] is None
        knowledge.set_active(doc_id, False)
        assert knowledge.get_document(doc_id)["is_active"] is False
        knowledge.set_active(doc_id, True)
        assert knowledge.get_document(doc_id)["is_active"] is True
        knowledge.set_deleted(doc_id, True)
        assert knowledge.get_document(doc_id)["deleted_at"] is not None
        knowledge.set_deleted(doc_id, False)
        assert knowledge.get_document(doc_id)["deleted_at"] is None
    finally:
        db.execute("DELETE FROM kb_documents WHERE id = %s", (doc_id,))


def test_kb_apply_edits_metadata_only():
    doc_id = _seed_doc()
    try:
        out = knowledge.apply_edits_metadata(
            doc_id, {"title": "New Title", "url": "https://new.example", "lang": "en",
                     "content": "HACKED CONTENT"})
        assert sorted(out["fields"]) == ["lang", "title", "url"]
        d = knowledge.get_document(doc_id)
        assert d["title"] == "New Title" and d["url"] == "https://new.example"
        assert "HACKED" not in d["content"]                 # content is NOT editable via this path
    finally:
        db.execute("DELETE FROM kb_documents WHERE id = %s", (doc_id,))


def test_knowledge_search_excludes_paused(monkeypatch):
    monkeypatch.setattr(emb, "enabled", lambda: False)   # exercise the ILIKE fallback branch
    doc_id = _seed_doc()
    try:
        assert knowledge.search("distinctive kb content")
        knowledge.set_active(doc_id, False)
        assert knowledge.search("distinctive kb content") == []
        knowledge.set_active(doc_id, True)
        assert knowledge.search("distinctive kb content")
    finally:
        db.execute("DELETE FROM kb_documents WHERE id = %s", (doc_id,))


def test_upsert_document_does_not_reset_pause(monkeypatch):
    # Regression: upsert_document's content UPDATE must not clobber is_active/deleted_at -- those
    # aren't in its SET column list, only content/title/url/lang/content_hash/updated_at are.
    monkeypatch.setattr(emb, "enabled", lambda: False)
    doc_id = _seed_doc()
    try:
        knowledge.set_active(doc_id, False)
        knowledge.upsert_document(source_type="article", source_ref=_REF,
                                  content="ZZTEST distinctive kb content, now CHANGED.",
                                  title="ZZTest Admin Article")
        assert knowledge.get_document(doc_id)["is_active"] is False
    finally:
        db.execute("DELETE FROM kb_documents WHERE id = %s", (doc_id,))
