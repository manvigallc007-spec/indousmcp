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

from . import analytics, tags as _tags, verticals
from .config import settings

_SYSTEM = (
    "You are a warm, concise local guide to Indian-American businesses, temples, and events "
    "across the USA — restaurants, groceries, temples, doctors, salons, events, apparel & "
    "jewelry, sweets & bakeries, yoga/dance studios, money-transfer/travel services, "
    "immigration lawyers, tutoring & heritage schools, real-estate agents, and CPAs/tax advisors. "
    "When the user asks for places or things to do, ALWAYS call the search_directory tool to "
    "find real listings — never invent businesses or details. After searching, reply in 1-3 "
    "short sentences and let the listing cards show the specifics; mention if something is "
    "featured or open now when relevant. If nothing matches, say so and suggest a nearby city "
    "or a broader search. Only state facts present in the search results."
)

_SYSTEM_GROUNDED = (
    "You are Dost (Hindi/Urdu for “friend”), a warm, concise guide to Indian-American businesses, "
    "temples, and events across the USA. You are given the directory listings that best match the "
    "user's request, already ordered with the NEAREST first. Reply in 1-2 friendly, natural "
    "sentences using ONLY those listings — never invent businesses or details, and don't just list "
    "them all (the user sees them as cards below). Name the top pick and why it fits — closest, "
    "open now, or well-rated — and offer to narrow by area, cuisine/veg, or open-now. Vary your "
    "wording. If the list is empty, say nothing matched and suggest a nearby city or broader search."
)

_SYSTEM_WEB = (
    "You are a warm, concise guide for Indian-Americans living in the USA. Answer the user's "
    "question in plain English in 2-4 sentences, using ONLY the reference material provided "
    "below. This is GENERAL information, NOT from a verified directory — so never list, name, "
    "or invent any specific business, phone number, address, or price. If the references don't "
    "actually answer the question, say you're not sure.")

_SYSTEM_DISCOVERY = (
    "You are Dost (Hindi/Urdu for “friend”), a warm guide to Indian-American places across the "
    "USA. We do NOT have a listing for the user's request yet. In 1-2 friendly, natural sentences: "
    "(1) gently say we don't have it yet, (2) ask ONE specific follow-up to understand what they "
    "want (which area/city, what kind, veg or occasion), and (3) invite them to share a place they "
    "know so we can add it to the directory. Be warm and curious, vary your wording — never invent "
    "or name specific businesses.")

_SYSTEM_KB = (
    "You are Dost (Hindi/Urdu for “friend”), a warm, knowledgeable guide to Indian & South-Asian "
    "life in the USA — culture, festivals, food, religion and temples, plus practical topics like "
    "visas, taxes and settling in. Answer the user's question conversationally and helpfully in "
    "2-5 sentences, primarily using the KNOWLEDGE provided below; you may add widely-known general "
    "context. Do NOT invent specific businesses, names, prices or phone numbers, and don't give "
    "definitive legal/tax/medical advice — point them to a professional for specifics. If the "
    "knowledge doesn't cover it, briefly share what you do know and say so honestly. Warm, clear, "
    "never preachy.")

# Free-form knowledge intent: a question that wants an EXPLANATION, not a place to visit. We only
# treat it as knowledge when no category chip is set, no location is named, and there's no
# find-a-place cue — so "what is dosa" answers in prose while "dosa near me" still lists places.
_Q_START = re.compile(
    r"^\s*(what|what's|how|why|when|which|who|tell me|explain|describe|is it|are there|"
    r"do i|can i|should i)\b", re.I)
_KNOWLEDGE_PHRASES = ("celebrat", "significance", "history of", "meaning of", "tradition",
                      "how to apply", "documents for", "documents do i need", "difference between",
                      "what is", "what are", "how is", "how do", "how does", "tell me about",
                      "explain",
                      # diaspora-stats cues (Census facts answered in prose, not listings)
                      "how many", "population of", "median income", "per capita", "average income",
                      "most educated", "languages spoken", "what languages", "median age")
_PLACE_CUES = ("near me", "nearby", "open now", "find ", "show me", "list ", "recommend",
               "closest", "around me", "directions")


def _is_knowledge_question(query: str, filters: dict | None) -> bool:
    t = (query or "").lower().strip()
    if not t or (filters or {}).get("vertical"):
        return False
    if _extract_location(query) != (None, None) or any(c in t for c in _PLACE_CUES):
        return False
    return bool(_Q_START.match(t)) or any(p in t for p in _KNOWLEDGE_PHRASES)


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
_OPEN_NOW_PHRASES = ("open now", "open right now", "currently open", "whats open",
                     "what's open", "open late", "open today", "still open")


def _wants_open_now(query: str) -> bool:
    q = (query or "").lower()
    return any(p in q for p in _OPEN_NOW_PHRASES)


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
    # The directory is English: translate a native-script (Hindi/Telugu) request to English first,
    # so search works in every path (an English/LLM-supplied query passes through untouched).
    query = _english((args.get("query") or "").strip(), filters)
    city = filters.get("city") or args.get("city") or None
    state = filters.get("state") or args.get("state") or None
    vertical = filters.get("vertical") or args.get("vertical") or None
    # A typed category SCOPES the search to just that category: "restaurants in Plano" returns only
    # restaurants — not salons, professionals, etc. — and overrides any chip. When the message names
    # no category, the chip (or an all-category search) still applies, so chips stay useful for
    # follow-ups. This is what keeps results to exactly what the user asked for.
    typed_vertical = _guess_vertical(query) if query else None
    if typed_vertical:
        vertical = typed_vertical
    # Honor an explicit chip OR a free-text "open now" in the query itself.
    open_now = bool(filters.get("open_now") or args.get("open_now") or _wants_open_now(query))
    point = _point(geo)

    # Free-text location: "dallas restaurants" -> city=Dallas; "food in texas" -> state=TX.
    # Without this the query is just fuzzy-matched across every city (looks random). A named
    # place also overrides the browser's GPS — if you ask for Dallas from NJ, you want Dallas.
    auto_city = None
    if not city and not state and query:
        ec, es = _extract_location(query)
        if ec or es:
            city, state, auto_city = ec, es, ec
            point = None

    def _do(c: str | None, s: str | None) -> dict:
        fn = (getattr(verticals.VERTICALS[vertical]["queries"], f"search_{vertical}_by_text", None)
              if vertical in verticals.VERTICALS else None)
        if fn:
            r = fn(query, city=c, state=s, limit=limit, point=point)
            for row in r.get("results", []):
                row["vertical"] = vertical
            return r
        return verticals.search_all(query, city=c, state=s, limit=limit,
                                    lat=point[0] if point else None,
                                    lng=point[1] if point else None)

    res = _do(city, state)
    # If we narrowed to a specific city and found nothing, widen to its state (covers suburbs).
    if auto_city and not res.get("results") and state:
        res = _do(None, state)
        city = None

    rows = res.get("results", [])
    if open_now and rows:
        from . import hours
        hours.annotate(rows)
        rows = [r for r in rows if r.get("open_now")]
        res = {**res, "results": rows, "count": len(rows)}

    try:  # per-listing reach when listings are surfaced (the chat turn itself is logged in web/chat.py)
        analytics.log_impressions("search_all", res)
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


# Multilingual: the chat passes a language code; English is the default (no instruction needed).
_LANG_NAMES = {"hi": "Hindi", "te": "Telugu", "en": "English"}


def _lang_note(filters: dict | None) -> str | None:
    """System instruction so the LLM understands & replies in the user's chosen language while
    still searching the (English) directory in English."""
    name = _LANG_NAMES.get((filters or {}).get("lang") or "en")
    if not name or name == "English":
        return None
    return (f"LANGUAGE: Reply ENTIRELY in {name}, in its native script, using warm, natural, "
            f"everyday {name} the way a friendly local actually speaks — not stiff, not overly "
            f"formal, and NOT a word-for-word translation of English. Use the COLLOQUIAL, spoken "
            f"register (everyday conversational Hindustani for Hindi, everyday spoken Telugu for "
            f"Telugu); mixing in common English words people normally use is natural and welcome, and "
            f"AVOID heavy literary/Sanskritized or bureaucratic wording. Short, clear sentences that "
            f"sound good when read aloud. Keep proper nouns (business names, cities) in their usual "
            f"spelling, and you may keep common English words people normally use (e.g. "
            f"'restaurant', 'temple', 'open'). The user may type or speak in {name} or a romanized "
            f"form — understand either. When you search the directory or call a tool, TRANSLATE the "
            f"request into English search terms (listings are stored in English); never show the "
            f"English translation to the user.")


# --- Multilingual normalization -------------------------------------------------------------
# The directory + topic routing are English. When the user speaks/types Hindi or Telugu, the STT
# may return native script (or a browser may even mis-transcribe), so we translate the request to
# English BEFORE searching/routing — making search correct in every path (tool, grounded, no-LLM),
# not only when the LLM happens to translate. Replies still go back in the user's language (see
# _lang_note). Free + zero-budget: reuse the configured LLM, with a key-less MyMemory fallback.
# Indic-script Unicode blocks: Devanagari (U+0900) through Malayalam (U+0D7F) — covers Hindi &
# Telugu (and neighbours), so a native-script request is detected regardless of the language tag.
_XLATE_CACHE: dict[str, str] = {}


def _has_indic(text: str) -> bool:
    return any(0x0900 <= ord(ch) <= 0x0DFF for ch in (text or ""))


def _mymemory_en(text: str, src: str) -> str | None:
    """Key-less free fallback translation (MyMemory). Only used when no LLM is configured."""
    try:
        r = httpx.get("https://api.mymemory.translated.net/get",
                      params={"q": text[:480], "langpair": f"{src}|en"}, timeout=6.0)
        out = (r.json().get("responseData") or {}).get("translatedText")
        return out.strip() if out else None
    except Exception:
        return None


def _translate_to_english(text: str, src: str) -> str | None:
    key = f"{src}:{text}"
    if key in _XLATE_CACHE:
        return _XLATE_CACHE[key]
    out = None
    if llm_active():
        out = complete_text(
            "You are a translator. Translate the user's message to English. Output ONLY the English "
            "translation — no quotes, no notes, no extra text.", text)
        out = out.strip() if out else None
    if not out:
        out = _mymemory_en(text, src if src in ("hi", "te") else "autodetect")
    if out:
        if len(_XLATE_CACHE) > 500:
            _XLATE_CACHE.clear()
        _XLATE_CACHE[key] = out
    return out


def _english(text: str, filters: dict | None) -> str:
    """English form of the user's request, for searching the English directory + topic routing.
    Translates only when the language is Hindi/Telugu AND the text is in native Indic script, so an
    English (or LLM-supplied English) query is left untouched and we never double-translate."""
    lang = (filters or {}).get("lang")
    if not text or lang in (None, "", "en") or not _has_indic(text):
        return text
    return _translate_to_english(text, lang) or text


def _cards(res: dict) -> list[dict]:
    # Return up to 12; the chat UI shows the top 6 and offers "show more" for the rest.
    out = []
    for r in (res.get("results") or [])[:12]:
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
            "community_rating": (float(r["community_rating"])
                                 if r.get("community_rating") is not None else None),
            "community_rating_count": r.get("community_rating_count"),
            "verified_ago": r.get("verified_ago"),
            "distance_miles": r.get("distance_miles"),
            "id": r.get("id"),
            "features": _tags.for_display(r.get("tags")),
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
    payload: dict[str, Any] = {"model": settings.effective_llm_model, "messages": messages,
                               "temperature": 0.3}
    if use_tools:
        payload["tools"] = _TOOLS
        payload["tool_choice"] = "auto"
    resp = httpx.post(
        f"{settings.effective_llm_base_url.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {settings.llm_api_key}"},
        json=payload, timeout=settings.llm_timeout_s)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]


def _llm_reply(messages: list[dict], geo: dict | None, filters: dict | None) -> dict:
    convo: list[dict] = [{"role": "system", "content": _SYSTEM}]
    for extra in (_location_note(geo), _filter_note(filters), _lang_note(filters)):
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
    if not res.get("results"):
        # No directory hit: skip the LLM call here and let reply() run the relevance gate +
        # free web fallback (avoids spending a slow CPU LLM call just to say "nothing matched").
        return {"reply": "", "cards": [], "provider": "llm", "_empty": True}
    convo: list[dict] = [{"role": "system", "content": _SYSTEM_GROUNDED}]
    for extra in (_location_note(geo), _filter_note(filters), _lang_note(filters)):
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
        return {"reply": "Tell me what you're looking for — say a category and a place, like "
                "“biryani in Edison, NJ” or “Krishna temple near me”.",
                "cards": [], "provider": "search"}
    res = _run_search({"query": query}, filters, geo)
    cards = _cards(res)
    n = len(cards)
    if n == 0:
        return {"reply": f"I couldn't find anything for “{query}”. Try a nearby city, or a "
                "broader search (just the cuisine or category).", "cards": [], "provider": "search"}
    nearest = any(c.get("distance_miles") is not None for c in cards)
    lead = "Here are the nearest matches" if nearest else "Here's what I found"
    extra = (" Showing the top 6 — tap “show more”, or narrow by area, “open now”, or veg."
             if n > 6 else
             " Tap a card to call, visit, or map it — or name an area to narrow it down.")
    return {"reply": f"{lead} for “{query}”.{extra}", "cards": cards, "provider": "search"}


# --------------------------------------------- relevance gate + free web fallback
# Signals that a free-text question is about Indian / Indian-American life in the USA. Used ONLY
# when the directory returns nothing, to decide between a web answer and a polite decline.
_TOPIC_SIGNALS = (
    "india", "indian", "indo", "desi", "hindustani", "bharat", "south asian", "subcontinent",
    "hindu", "sikh", "jain", "mandir", "gurdwara", "gurudwara", "puja", "pooja", "aarti",
    "bhajan", "swaminarayan", "iskcon",
    "telugu", "tamil", "gujarati", "punjabi", "bengali", "marathi", "kannada", "malayalam",
    "hindi", "urdu", "odia", "konkani", "sindhi", "andhra", "kerala", "rajasthani", "assamese",
    "diwali", "deepavali", "holi", "navratri", "garba", "dussehra", "rakhi", "raksha bandhan",
    "onam", "pongal", "ganesh", "durga", "ugadi", "baisakhi", "lohri", "sankranti", "janmashtami",
    "biryani", "dosa", "idli", "samosa", "paneer", "masala", "tandoori", "naan", "chaat",
    "thali", "mithai", "ladoo", "jalebi", "gulab jamun", "vada", "lassi", "halal", "tiffin",
    "bollywood", "cricket", "bharatanatyam", "kathak", "carnatic", "sitar", "tabla", "raga",
    "saree", "sari", "lehenga", "kurta", "sherwani", "mehndi", "henna", "rangoli", "ayurveda",
    "bhangra", "kirtan", "shaadi", "matrimony", "rishta", "pandit", "priest",
    "h1b", "h-1b", "green card", "oci", " pio ", "nri", "visa", "remittance",
    "samaj", "sangam", "mandal", "association",
)

_VERTICAL_HINTS = {
    "restaurants": ("restaurant", "food", "eat", "dinner", "lunch", "thali", "biryani", "dosa", "cafe"),
    "groceries": ("grocery", "spice", "vegetables", "atta", "lentil"),
    "temples": ("temple", "mandir", "gurdwara", "puja", "worship"),
    "professionals": ("doctor", "dentist", "clinic", "physician", "healthcare", "pharmacy", "hospital"),
    "salons": ("salon", "threading", "henna", "mehndi", "beauty", "hairdresser", "bridal"),
    "sweets": ("sweets", "mithai", "bakery", "ladoo", "jalebi", "halwa"),
    "studios": ("yoga", "dance", "music", "studio", "bharatanatyam", "tabla", "kathak", "class"),
    "apparel": ("saree", "sari", "lehenga", "jewelry", "jeweler", "clothing", "boutique"),
    "services": ("money transfer", "remittance", "travel", "cargo", "shipping", "visa"),
    "community": ("association", "samaj", "sangam", "organization", "cultural"),
    "legal": ("lawyer", "attorney", "immigration", "green card", "h1b", "law firm"),
    "education": ("tutoring", "tutor", "coaching", "vidyalaya", "gurukul", "bal vihar",
                  "sanskrit", "language school", "heritage school"),
    "realestate": ("realtor", "real estate", "realty", "mortgage", "property"),
    "finance": ("cpa", "accountant", "tax preparer", "tax prep", "financial advisor", "bookkeeping"),
}

# Verticals with no free bulk data source — they grow mainly from submissions, so when a search
# here returns only a handful, we proactively invite the visitor to add one they know.
_SPARSE_VERTICALS = {"legal", "finance", "realestate", "education", "community"}


def is_indian_american_topic(text: str) -> bool:
    """Heuristic, free relevance check (no LLM). Permissive toward diaspora topics; rejects
    clearly off-topic questions (e.g. car repair, generic coding) so we can decline politely."""
    t = (text or "").lower()
    if not t:
        return False
    return any(s in t for s in _TOPIC_SIGNALS) or any(w in t for w in _LOCAL_WORDS)


def _guess_vertical(query: str) -> str | None:
    # Longest matched keyword wins, so a specific word ("tutoring", "immigration") beats a generic
    # one in another vertical ("class", "store") regardless of dict order.
    t = (query or "").lower()
    best_v, best_len = None, 0
    for v, words in _VERTICAL_HINTS.items():
        for w in words:
            if w in t and len(w) > best_len:
                best_v, best_len = v, len(w)
    return best_v


def _thin_contribute(query: str, filters: dict | None, cards: list) -> dict | None:
    """A thin (1-3) result in a sparse vertical is a growth chance: invite the visitor to add one
    they know. Returns a contribute payload (shown as an '➕ Add a place you know' button) or None."""
    v = (filters or {}).get("vertical") or _guess_vertical(query)
    if v not in _SPARSE_VERTICALS or not (0 < len(cards or []) <= 3):
        return None
    city, state = _extract_location(query)
    return {"vertical": v, "city": city, "state": state}


def _suggest_add(query: str) -> dict:
    base = settings.public_web_url.rstrip("/")
    v = _guess_vertical(query)
    url = f"{base}/submit" + (f"?vertical={v}" if v else "")
    return {"label": "➕ Add it to the directory", "url": url, "vertical": v}


def _decline(query: str) -> dict:
    """Politely refuse off-topic questions (kept narrow to Indian-American life in the USA)."""
    return {"reply": ("I'm focused on Indian-American life in the USA — restaurants, groceries, "
                      "temples, events, professionals, classes, community groups and the like. I "
                      "don't have a good answer for that one. Try asking about an Indian business, "
                      "place, festival, or community topic and I'll do my best!"),
            "cards": [], "provider": "offtopic"}


def _web_snippets_text(snips: list[dict]) -> str:
    return "\n\n".join(f"[{s.get('source')}] {s.get('title', '')}: {s.get('text', '')}"
                       for s in snips)


def _is_local_request(query: str, filters: dict | None = None) -> bool:
    """A request for a local business/place (-> discovery conversation) vs a general-knowledge
    question (-> web answer). True if a category, local-intent word, or place is present."""
    if (filters or {}).get("vertical"):
        return True
    t = (query or "").lower()
    return bool(_guess_vertical(query)) or any(w in t for w in _LOCAL_WORDS) \
        or _extract_location(query) != (None, None)


def _discovery_template(vertical: str | None, city: str | None) -> str:
    label = (verticals.VERTICALS.get(vertical, {}).get("label", "").lower()
             if vertical else "") or "places like that"
    where = f" in {city}" if city else " in your area"
    return (f"I don't have {label}{where} in the directory yet — and honestly that's really useful "
            "to know, it tells me what to add next! Could you tell me a little more — which area, "
            "or what kind you're after? And if you already know a great spot, share its name and "
            "I'll get it into the directory for others.")


def _discovery_reply(query: str, messages: list[dict], geo: dict | None, filters: dict | None) -> dict:
    """A relevant *local* request we can't answer yet → engage: acknowledge, ask a follow-up, and
    invite the visitor to contribute the missing place (which we'll add). Demand was already logged
    by the search that came up empty, so agents can prioritize scraping it."""
    vertical = (filters or {}).get("vertical") or _guess_vertical(query)
    city, state = _extract_location(query)
    if not (city or state) and geo:
        try:
            from .pipeline import clean
            city, state = clean.fill_location(None, None, float(geo["lat"]), float(geo["lng"]))
        except Exception:
            pass
    reply = None
    if llm_active():
        try:
            convo = [{"role": "system", "content": _SYSTEM_DISCOVERY}]
            note = _lang_note(filters)
            if note:
                convo.append({"role": "system", "content": note})
            convo += [{"role": m["role"], "content": m.get("content", "")} for m in messages][-4:]
            reply = (_chat(convo, use_tools=False).get("content") or "").strip() or None
        except Exception:
            reply = None
    if not reply:
        reply = _discovery_template(vertical, city)
    return {"reply": reply, "cards": [], "provider": "discovery",
            "suggest_add": _suggest_add(query),
            "contribute": {"vertical": vertical, "city": city, "state": state}}


def _knowledge_reply(query: str, messages: list[dict], geo: dict | None, filters: dict | None) -> dict:
    """Free-form answer to a knowledge question — retrieve from the per-vertical knowledge base and
    answer in prose (with the LLM if available). Falls back to the free web sources when the KB has
    nothing yet, so this works even before any content is seeded."""
    from . import knowledge
    vertical = (filters or {}).get("vertical") or _guess_vertical(query)
    try:
        hits = knowledge.search(query, vertical=vertical, limit=6) if vertical else []
        if not hits:
            hits = knowledge.search(query, vertical=None, limit=6)
    except Exception:                                       # KB/DB unavailable -> degrade to web
        hits = []
    if not hits:
        return _web_fallback(query, geo, filters)          # nothing curated yet -> free web knowledge
    context = "\n\n".join(f"[{h.get('title') or h.get('source_type') or 'note'}] {h.get('text', '')}"
                          for h in hits)[:4000]
    if llm_active():
        try:
            convo = [{"role": "system", "content": _SYSTEM_KB}]
            note = _lang_note(filters)
            if note:
                convo.append({"role": "system", "content": note})
            convo.append({"role": "user", "content": f"Question: {query}\n\nKNOWLEDGE:\n{context}"})
            ans = (_chat(convo, use_tools=False).get("content") or "").strip()
            if ans:
                return {"reply": ans, "cards": [], "provider": "knowledge"}
        except Exception:
            pass
    top = hits[0]
    tail = f"\n\n— {top['title']}" if top.get("title") else ""
    return {"reply": (top.get("text") or "")[:800] + tail, "cards": [], "provider": "knowledge"}


def _web_fallback(query: str, geo: dict | None, filters: dict | None) -> dict:
    """Relevant question the directory can't answer → answer from free web sources (labelled as
    general info, never as a verified listing) + suggest adding it to the directory.

    Learning: a semantically-equivalent question answered before is served from the local cache
    (no LLM/web call); fresh general answers are stored so the same question won't need the LLM
    again."""
    from . import learning, websearch
    add = _suggest_add(query)
    cached = learning.lookup(query)
    if cached is not None:
        return {"reply": cached, "cards": [], "provider": "web", "suggest_add": add, "cached": True}

    snips = websearch.lookup(query) if settings.web_fallback_enabled else []
    answer = ""
    if snips:
        if llm_active():
            try:
                convo = [{"role": "system", "content": _SYSTEM_WEB}]
                note = _lang_note(filters)
                if note:
                    convo.append({"role": "system", "content": note})
                convo.append({"role": "user", "content":
                              f"Question: {query}\n\nReference material:\n{_web_snippets_text(snips)}"})
                msg = _chat(convo, use_tools=False)
                answer = (msg.get("content") or "").strip()
            except Exception:
                answer = ""
        if not answer:  # no LLM (or it failed): show the top snippet directly
            top = snips[0]
            answer = top["text"][:600] + f"\n\n— {top.get('source')}"
        reply = ("ℹ️ I don't have this in our verified directory, but here's some general "
                 f"information:\n\n{answer}")
    else:
        reply = ("I don't have this in our directory yet, and couldn't find a quick answer "
                 "online.")
    reply += f"\n\nKnow a place like this? Help others find it — {add['label'].lower()}."
    if snips:  # only cache real general answers (not transient "couldn't find" misses)
        learning.store(query, reply, provider="web")
    return {"reply": reply, "cards": [], "provider": "web", "suggest_add": add}


# ----------------------------------------------------------------------- entrypoint
def enabled() -> bool:
    return settings.chat_enabled


def llm_active() -> bool:
    return settings.llm_enabled and bool(settings.effective_llm_base_url
                                         and settings.effective_llm_model)


def complete_text(system: str, user: str) -> str | None:
    """One-shot LLM completion (no tools) for non-chat callers like recommendation research.
    Returns the model's text, or None if the LLM is inactive or the call fails (caller decides)."""
    if not llm_active():
        return None
    try:
        msg = _chat([{"role": "system", "content": system},
                     {"role": "user", "content": user}], use_tools=False)
        return (msg.get("content") or "").strip() or None
    except Exception:
        return None


# Local-intent words that benefit from a location; and a crude "did they name a place" check.
_LOCAL_WORDS = ("restaurant", "food", "eat", "dinner", "lunch", "thali", "temple", "mandir",
                "grocery", "store", "salon", "threading", "doctor", "clinic", "dentist",
                "studio", "yoga", "dance", "class", "sweets", "mithai", "bakery", "jewelry",
                "jeweler", "saree", "near me", "nearby", "around me")
_STATES = ("al", "ak", "az", "ar", "ca", "co", "ct", "de", "fl", "ga", "hi", "id", "il", "in",
           "ia", "ks", "ky", "la", "me", "md", "ma", "mi", "mn", "ms", "mo", "mt", "ne", "nv",
           "nh", "nj", "nm", "ny", "nc", "nd", "oh", "ok", "or", "pa", "ri", "sc", "sd", "tn",
           "tx", "ut", "vt", "va", "wa", "wv", "wi", "wy")

# Full US state names -> USPS code, for "...in texas" style queries.
_STATE_NAMES = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR", "california": "CA",
    "colorado": "CO", "connecticut": "CT", "delaware": "DE", "florida": "FL", "georgia": "GA",
    "hawaii": "HI", "idaho": "ID", "illinois": "IL", "indiana": "IN", "iowa": "IA",
    "kansas": "KS", "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV", "new hampshire": "NH",
    "new jersey": "NJ", "new mexico": "NM", "north carolina": "NC", "north dakota": "ND",
    "ohio": "OH", "oklahoma": "OK", "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI",
    "south carolina": "SC", "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
    "vermont": "VT", "virginia": "VA", "washington": "WA", "west virginia": "WV",
    "wisconsin": "WI", "wyoming": "WY",
}

# Diaspora-hub cities/metros people actually type -> (city, state). Metro phrases that span many
# cities map to (None, state) so we filter by state, not one city.
_CITY_LOCATIONS = {
    "dallas": ("Dallas", "TX"), "plano": ("Plano", "TX"), "irving": ("Irving", "TX"),
    "frisco": ("Frisco", "TX"), "houston": ("Houston", "TX"), "austin": ("Austin", "TX"),
    "chicago": ("Chicago", "IL"), "naperville": ("Naperville", "IL"), "schaumburg": ("Schaumburg", "IL"),
    "atlanta": ("Atlanta", "GA"), "seattle": ("Seattle", "WA"), "redmond": ("Redmond", "WA"),
    "bellevue": ("Bellevue", "WA"), "phoenix": ("Phoenix", "AZ"), "boston": ("Boston", "MA"),
    "philadelphia": ("Philadelphia", "PA"), "raleigh": ("Raleigh", "NC"), "cary": ("Cary", "NC"),
    "morrisville": ("Morrisville", "NC"), "durham": ("Durham", "NC"), "detroit": ("Detroit", "MI"),
    "troy": ("Troy", "MI"), "canton": ("Canton", "MI"), "edison": ("Edison", "NJ"),
    "iselin": ("Iselin", "NJ"), "jersey city": ("Jersey City", "NJ"), "parsippany": ("Parsippany", "NJ"),
    "piscataway": ("Piscataway", "NJ"), "san jose": ("San Jose", "CA"), "fremont": ("Fremont", "CA"),
    "sunnyvale": ("Sunnyvale", "CA"), "santa clara": ("Santa Clara", "CA"), "milpitas": ("Milpitas", "CA"),
    "cupertino": ("Cupertino", "CA"), "san francisco": ("San Francisco", "CA"),
    "los angeles": ("Los Angeles", "CA"), "irvine": ("Irvine", "CA"), "artesia": ("Artesia", "CA"),
    "queens": ("Queens", "NY"),
}
_METRO_LOCATIONS = {  # phrase -> (None=any city, state)
    "bay area": (None, "CA"), "silicon valley": (None, "CA"), "socal": (None, "CA"),
    "nyc": (None, "NY"), "new york city": (None, "NY"), "new york": (None, "NY"),
    "dfw": ("Dallas", "TX"), "central jersey": (None, "NJ"), "north jersey": (None, "NJ"),
}


def _extract_location(text: str) -> tuple[str | None, str | None]:
    """Pull a (city, state) hint from free text. City/metro phrases win (longest first), then a
    full state name, then a 2-letter code after a comma ("Edison, NJ"). ("", "") -> nothing."""
    t = (text or "").lower()
    if not t:
        return None, None
    places = sorted({**_CITY_LOCATIONS, **_METRO_LOCATIONS}.items(), key=lambda kv: -len(kv[0]))
    for phrase, (c, s) in places:
        if re.search(rf"\b{re.escape(phrase)}\b", t):
            return c, s
    for name, abbr in _STATE_NAMES.items():
        if re.search(rf"\b{name}\b", t):
            return None, abbr
    m = re.search(r",\s*([a-z]{2})\b", t)  # only trust a bare 2-letter code after a comma
    if m and m.group(1) in _STATES:
        return None, m.group(1).upper()
    return None, None


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
                   or any(re.search(rf"\b{s}\b", text) for s in _STATES)
                   or _extract_location(text) != (None, None))
    return not named_place


def reply(messages: list[dict], geo: dict | None = None, filters: dict | None = None) -> dict:
    """Produce an assistant reply for a chat history. Never raises into the web layer."""
    messages = [m for m in (messages or []) if m.get("role") in ("user", "assistant")][-12:]
    if _needs_location(messages, geo, filters):
        return {"reply": "Which city or area should I look in? For example: “Edison, NJ”, "
                "“Jersey City”, or “Bay Area”.", "cards": [], "provider": "clarify"}
    query = _search_query(messages)
    # Topic routing below is English-keyword based, so normalize a Hindi/Telugu request to English
    # first (otherwise a native-script question could be mis-declined as "off-topic"). The LLM still
    # sees the original `messages` and replies in the user's language (see _lang_note).
    query = _english(query, filters)
    # Free-form knowledge question (explain/what/how, no place named) -> answer in prose from the
    # knowledge base (then the free web), instead of forcing listing cards. This is what makes Dost
    # conversational ("how is Pongal celebrated?") rather than a search box.
    if query and is_indian_american_topic(query) and _is_knowledge_question(query, filters):
        return _knowledge_reply(query, messages, geo, filters)
    if llm_active():
        try:
            engine = _llm_reply if settings.effective_llm_use_tools else _grounded_reply
            out = engine(messages, geo, filters)
        except Exception as exc:  # LLM unreachable/misconfigured -> degrade to search
            out = _search_reply(messages, geo, filters)
            out["reply"] = ("(Live assistant is unavailable right now — showing a direct "
                            f"search instead.) {out['reply']}")
            out["llm_error"] = type(exc).__name__
    else:
        out = _search_reply(messages, geo, filters)

    # Directory found nothing for a real query. Route the dead-end into something useful:
    #  - off-topic            -> polite decline
    #  - local business/place -> a DISCOVERY conversation (ask a follow-up + invite them to add it)
    #  - general knowledge    -> answer from free web sources
    if query and not out.get("cards"):
        if not is_indian_american_topic(query):
            return _decline(query)
        if _is_local_request(query, filters):
            return _discovery_reply(query, messages, geo, filters)
        return _web_fallback(query, geo, filters)
    # Thin result in a submission-fed vertical -> invite the visitor to add one they know.
    if query and out.get("cards") and "contribute" not in out:
        inv = _thin_contribute(query, filters, out["cards"])
        if inv:
            out["contribute"] = inv
    return out
