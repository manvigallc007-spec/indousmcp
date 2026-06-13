"""Human-facing conversational assistant over the directory (pluggable LLM, zero-budget).

A real tool-calling chatbot: it exposes one small `search_directory` tool to an LLM via the
OpenAI-compatible chat-completions API, so the SAME code talks to self-hosted Ollama (free)
or any hosted API key. With no LLM configured (`llm_provider="search"`) it falls back to a
templated semantic-search reply, so the chat page is useful out of the box at no cost.

Human chat traffic is credited to analytics (tool_log client="web-chat") and to per-listing
impressions — the same reach signal that makes featured placements valuable.
"""

from __future__ import annotations

import json
import re
from typing import Any

import httpx

from . import analytics, verticals
from .config import settings

_SYSTEM = (
    "You are a warm, concise local guide to Indian-American businesses, temples, and events "
    "across the USA — restaurants, groceries, temples, doctors, salons, events, apparel & "
    "jewelry, sweets & bakeries, yoga/dance studios, and money-transfer/travel services. "
    "When the user asks for places or things to do, ALWAYS call the search_directory tool to "
    "find real listings — never invent businesses or details. After searching, reply in 1-3 "
    "short sentences and let the listing cards show the specifics; mention if something is "
    "featured or open now when relevant. If nothing matches, say so and suggest a nearby city "
    "or a broader search. Only state facts present in the search results."
)

_SYSTEM_GROUNDED = (
    "You are a warm, concise local guide to Indian-American businesses, temples, and events "
    "across the USA. You are given the directory listings that best match the user's request. "
    "Reply in 1-3 short sentences using ONLY those listings — never invent businesses or "
    "details. Mention featured or open-now when relevant. If the list is empty, say nothing "
    "matched and suggest a broader search or a nearby city. The user also sees the listings as "
    "cards below your reply."
)

_TOOLS = [{
    "type": "function",
    "function": {
        "name": "search_directory",
        "description": ("Search the Indian-American directory across every category. Returns "
                        "matching listings (name, category, city, contact, description)."),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description":
                          "What the user wants, e.g. 'vegetarian south indian' or 'diwali garba'"},
                "city": {"type": "string", "description": "City to focus on, optional"},
                "state": {"type": "string", "description": "2-letter US state code e.g. NJ, optional"},
            },
            "required": ["query"],
        },
    },
}]


# ---------------------------------------------------------------- directory search
def _point(geo: dict | None) -> tuple[float, float] | None:
    if not geo:
        return None
    try:
        return (float(geo["lat"]), float(geo["lng"]))
    except (KeyError, TypeError, ValueError):
        return None


def _run_search(args: dict, filters: dict | None = None, geo: dict | None = None,
                limit: int = 8) -> dict:
    """Search the directory. `filters` (from the chat UI chips) override the LLM's args:
    a `vertical` scopes to one category; `open_now` keeps only currently-open listings.
    `geo` enables proximity ranking ("near me")."""
    filters = filters or {}
    query = (args.get("query") or "").strip()
    city = filters.get("city") or args.get("city") or None
    state = filters.get("state") or args.get("state") or None
    vertical = filters.get("vertical") or args.get("vertical") or None
    open_now = bool(filters.get("open_now") or args.get("open_now"))
    point = _point(geo)

    fn = (getattr(verticals.VERTICALS[vertical]["queries"], f"search_{vertical}_by_text", None)
          if vertical in verticals.VERTICALS else None)
    if fn:
        res = fn(query, city=city, state=state, limit=limit, point=point)
        for r in res.get("results", []):
            r["vertical"] = vertical
    else:
        res = verticals.search_all(query, city=city, state=state, limit=limit,
                                   lat=point[0] if point else None,
                                   lng=point[1] if point else None)

    rows = res.get("results", [])
    if open_now and rows:
        from . import hours
        hours.annotate(rows)
        rows = [r for r in rows if r.get("open_now")]
        res = {**res, "results": rows, "count": len(rows)}

    try:  # credit human engagement to analytics + per-listing reach (best-effort)
        analytics.log_impressions("search_all", res)
        analytics.log_call("chat", {"query": query, "vertical": vertical, "open_now": open_now},
                           res.get("count"), "web-chat")
    except Exception:
        pass
    return res


def _filter_note(filters: dict | None) -> str | None:
    if not filters:
        return None
    parts = []
    if filters.get("vertical") in verticals.VERTICALS:
        parts.append(f"only {verticals.VERTICALS[filters['vertical']]['label']} listings")
    if filters.get("open_now"):
        parts.append("only places open right now")
    return ("The user has applied filters: " + "; ".join(parts) + ".") if parts else None


def _cards(res: dict) -> list[dict]:
    out = []
    for r in (res.get("results") or [])[:8]:
        out.append({
            "vertical": r.get("vertical"),
            "name": r.get("name"),
            "city": r.get("city"),
            "state": r.get("state"),
            "phone": r.get("phone"),
            "website": r.get("website"),
            "description": (r.get("description") or "")[:240],
            "open_now": r.get("open_now"),
            "is_featured": bool(r.get("is_featured")),
            "is_claimed": bool(r.get("is_claimed")),
            "rating": float(r["rating"]) if r.get("rating") is not None else None,
            "rating_count": r.get("rating_count"),
            "verified_ago": r.get("verified_ago"),
            "distance_miles": r.get("distance_miles"),
            "id": r.get("id"),
        })
    return out


def _results_for_llm(res: dict) -> str:
    """Compact, factual rendering of results fed back to the model (keeps tokens small)."""
    rows = (res.get("results") or [])[:8]
    if not rows:
        return "No matching listings found."
    lines = []
    for r in rows:
        loc = ", ".join(x for x in (r.get("city"), r.get("state")) if x)
        flags = " ".join(f for f in (
            "FEATURED" if r.get("is_featured") else "",
            "open-now" if r.get("open_now") else "") if f)
        lines.append(
            f"- [{r.get('vertical')}] {r.get('name')} ({loc}) "
            f"{('· ' + r['phone']) if r.get('phone') else ''} {flags}".strip())
    return "\n".join(lines)


# ------------------------------------------------------------------ geo (near me)
def _location_note(geo: dict | None) -> str | None:
    if not geo:
        return None
    try:
        from .pipeline import clean
        city, state = clean.fill_location(None, None, float(geo["lat"]), float(geo["lng"]))
    except Exception:
        return None
    where = ", ".join(x for x in (city, state) if x)
    return f"The user is currently near {where}. Prefer results there unless they say otherwise." \
        if where else None


# ------------------------------------------------------------------- LLM transport
def _chat(messages: list[dict], use_tools: bool) -> dict:
    payload: dict[str, Any] = {"model": settings.llm_model, "messages": messages,
                               "temperature": 0.3}
    if use_tools:
        payload["tools"] = _TOOLS
        payload["tool_choice"] = "auto"
    resp = httpx.post(
        f"{settings.llm_base_url.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {settings.llm_api_key}"},
        json=payload, timeout=settings.llm_timeout_s)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]


def _llm_reply(messages: list[dict], geo: dict | None, filters: dict | None) -> dict:
    convo: list[dict] = [{"role": "system", "content": _SYSTEM}]
    for extra in (_location_note(geo), _filter_note(filters)):
        if extra:
            convo.append({"role": "system", "content": extra})
    convo += [{"role": m["role"], "content": m.get("content", "")} for m in messages]

    cards: list[dict] = []
    for _ in range(3):  # cap tool round-trips so a small model can't loop forever
        msg = _chat(convo, use_tools=True)
        calls = msg.get("tool_calls") or []
        if not calls:
            return {"reply": (msg.get("content") or "").strip() or "How can I help you explore?",
                    "cards": cards, "provider": "llm"}
        convo.append({"role": "assistant", "content": msg.get("content") or "",
                      "tool_calls": calls})
        for call in calls:
            fn = call.get("function", {})
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except Exception:
                args = {}
            res = _run_search(args, filters, geo)
            cards = _cards(res)  # newest search wins for the card panel
            convo.append({"role": "tool", "tool_call_id": call.get("id"),
                          "content": _results_for_llm(res)})
    # Hit the round-trip cap — answer from what we have.
    final = _chat(convo, use_tools=False)
    return {"reply": (final.get("content") or "Here's what I found.").strip(),
            "cards": cards, "provider": "llm"}


def _grounded_reply(messages: list[dict], geo: dict | None, filters: dict | None) -> dict:
    """RAG-style single-call reply: search first, then have the LLM write the answer over the
    results. No tool-calling — works with Gemma and any small model, and is faster on a CPU
    VPS (one LLM call instead of several tool round-trips)."""
    query = _search_query(messages)
    res = _run_search({"query": query}, filters, geo) if query else {"results": [], "count": 0}
    convo: list[dict] = [{"role": "system", "content": _SYSTEM_GROUNDED}]
    for extra in (_location_note(geo), _filter_note(filters)):
        if extra:
            convo.append({"role": "system", "content": extra})
    convo += [{"role": m["role"], "content": m.get("content", "")} for m in messages]
    convo.append({"role": "system", "content":
                  "Listings found for the latest request:\n" + _results_for_llm(res)})
    msg = _chat(convo, use_tools=False)
    return {"reply": (msg.get("content") or "Here's what I found.").strip(),
            "cards": _cards(res), "provider": "llm"}


# --------------------------------------------------------------- no-LLM fallback
def _last_user(messages: list[dict]) -> str:
    for m in reversed(messages):
        if m.get("role") == "user":
            return (m.get("content") or "").strip()
    return ""


def _is_clarify(content: str) -> bool:
    return (content or "").startswith("Which city or area")


def _search_query(messages: list[dict]) -> str:
    """The text to search. If our previous turn asked for a location, merge the original
    request with the location the user just gave (so 'restaurants' + 'Edison' -> both)."""
    users = [m.get("content", "") for m in messages if m.get("role") == "user"]
    asst = [m.get("content", "") for m in messages if m.get("role") == "assistant"]
    if not users:
        return ""
    if asst and _is_clarify(asst[-1]) and len(users) >= 2:
        return f"{users[-2]} {users[-1]}".strip()[:300]
    return users[-1].strip()


def _search_reply(messages: list[dict], geo: dict | None, filters: dict | None) -> dict:
    query = _search_query(messages)
    if not query:
        return {"reply": "Tell me what you're looking for — a restaurant, temple, sweets shop, "
                "event, and a city.", "cards": [], "provider": "search"}
    res = _run_search({"query": query}, filters, geo)
    n = res.get("count", 0)
    if n == 0:
        text = (f"I couldn't find anything for “{query}”. Try adding a city/state, "
                "or a broader search.")
    else:
        text = f"Here are {n} match{'es' if n != 1 else ''} for “{query}”:"
    return {"reply": text, "cards": _cards(res), "provider": "search"}


# ----------------------------------------------------------------------- entrypoint
def enabled() -> bool:
    return settings.chat_enabled


def llm_active() -> bool:
    return settings.llm_provider == "llm" and bool(settings.llm_base_url and settings.llm_model)


# Local-intent words that benefit from a location; and a crude "did they name a place" check.
_LOCAL_WORDS = ("restaurant", "food", "eat", "dinner", "lunch", "thali", "temple", "mandir",
                "grocery", "store", "salon", "threading", "doctor", "clinic", "dentist",
                "studio", "yoga", "dance", "class", "sweets", "mithai", "bakery", "jewelry",
                "jeweler", "saree", "near me", "nearby", "around me")
_STATES = ("al", "ak", "az", "ar", "ca", "co", "ct", "de", "fl", "ga", "hi", "id", "il", "in",
           "ia", "ks", "ky", "la", "me", "md", "ma", "mi", "mn", "ms", "mo", "mt", "ne", "nv",
           "nh", "nj", "nm", "ny", "nc", "nd", "oh", "ok", "or", "pa", "ri", "sc", "sd", "tn",
           "tx", "ut", "vt", "va", "wa", "wv", "wi", "wy")


def _needs_location(messages: list[dict], geo: dict | None, filters: dict | None) -> bool:
    """Ask for a city only ONCE — on the first turn — when there's no geo, clear local intent,
    and no place named. After we've replied at all, never re-ask: the user's next message is
    taken as the location (see _search_query). This prevents the clarify loop."""
    if geo:
        return False
    if any(m.get("role") == "assistant" for m in messages):
        return False  # we've already responded once — don't loop; treat next msg as the answer
    text = _last_user(messages).lower()
    if not text:
        return False
    has_intent = any(w in text for w in _LOCAL_WORDS) or bool((filters or {}).get("vertical"))
    if not has_intent:
        return False
    if "near me" in text or "nearby" in text or "around me" in text:
        return True  # wants local but we have no coordinates
    named_place = (bool(re.search(r"\bin\s+[a-z]{3,}", text)) or "," in text
                   or any(re.search(rf"\b{s}\b", text) for s in _STATES))
    return not named_place


def reply(messages: list[dict], geo: dict | None = None, filters: dict | None = None) -> dict:
    """Produce an assistant reply for a chat history. Never raises into the web layer."""
    messages = [m for m in (messages or []) if m.get("role") in ("user", "assistant")][-12:]
    if _needs_location(messages, geo, filters):
        return {"reply": "Which city or area should I look in? For example: “Edison, NJ”, "
                "“Jersey City”, or “Bay Area”.", "cards": [], "provider": "clarify"}
    if llm_active():
        try:
            engine = _llm_reply if settings.llm_use_tools else _grounded_reply
            return engine(messages, geo, filters)
        except Exception as exc:  # LLM unreachable/misconfigured -> degrade to search
            out = _search_reply(messages, geo, filters)
            out["reply"] = ("(Live assistant is unavailable right now — showing a direct "
                            f"search instead.) {out['reply']}")
            out["llm_error"] = type(exc).__name__
            return out
    return _search_reply(messages, geo, filters)
