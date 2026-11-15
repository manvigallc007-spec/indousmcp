"""Server-side UI translations for the interactive secondary pages (the chat has its own JS i18n).

The visitor's language comes from the `lang` cookie — set when they pick a language in the chat —
with an Accept-Language fallback, so the review + add-a-business forms render in English, Hindi, or
Telugu. Business data (names, addresses) always stays in its original language.
"""

from __future__ import annotations

from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response
from starlette.routing import Route

LANGS = ("en", "hi", "te")

# Shown in the switcher, in each language's own script -- a visitor who cannot read the current
# language still has to be able to find their own.
LANG_NAMES = {"en": "English", "hi": "हिंदी", "te": "తెలుగు"}

COOKIE = "lang"
_COOKIE_MAX_AGE = 31536000      # a year: the choice should outlive the session

# Resolved once per request by LanguageMiddleware. A contextvar rather than a parameter because
# none of the three page shells (common._page, landing._page, pages._page) takes a request, and
# threading one through every handler that renders a nav would be a far larger change than this.
_CURRENT: ContextVar[str] = ContextVar("ui_lang", default="en")

# key -> {en, hi, te}. Keep keys ASCII; values are hand-translated (verified codepoints).
_T: dict[str, dict[str, str]] = {
    # --- shared chrome: the nav, the mobile tab bar, the footer. Every page shows these, so they
    # are the strings that decide whether the site "feels" translated at all. Business data (names,
    # addresses, descriptions) always stays in its original language.
    "nav_home": {"en": "Home", "hi": "होम", "te": "హోమ్"},
    "nav_today": {"en": "Today", "hi": "आज", "te": "ఈరోజు"},
    "nav_news": {"en": "News", "hi": "समाचार", "te": "వార్తలు"},
    "nav_events": {"en": "Events", "hi": "कार्यक्रम", "te": "కార్యక్రమాలు"},
    "nav_browse": {"en": "Browse", "hi": "ब्राउज़ करें", "te": "బ్రౌజ్ చేయండి"},
    "nav_qa": {"en": "Q&A", "hi": "प्रश्न-उत्तर", "te": "ప్రశ్న-జవాబు"},
    "nav_insights": {"en": "Insights", "hi": "आंकड़े", "te": "విశ్లేషణలు"},
    "nav_search": {"en": "Search", "hi": "खोजें", "te": "వెతకండి"},
    "nav_saved": {"en": "Saved", "hi": "सहेजे गए", "te": "సేవ్ చేసినవి"},
    "nav_list_business": {"en": "List your business", "hi": "अपना व्यवसाय जोड़ें",
                          "te": "మీ వ్యాపారాన్ని జోడించండి"},
    "nav_ask": {"en": "Ask", "hi": "पूछें", "te": "అడగండి"},
    "nav_more": {"en": "More", "hi": "और", "te": "మరిన్ని"},
    "nav_about": {"en": "About us", "hi": "हमारे बारे में", "te": "మా గురించి"},
    "nav_privacy": {"en": "Privacy", "hi": "गोपनीयता", "te": "గోప్యత"},
    "nav_terms": {"en": "Terms", "hi": "शर्तें", "te": "నిబంధనలు"},
    "nav_contact": {"en": "Contact", "hi": "संपर्क", "te": "సంప్రదించండి"},
    "nav_faq": {"en": "FAQ", "hi": "सामान्य प्रश्न", "te": "సాధారణ ప్రశ్నలు"},
    "language": {"en": "Language", "hi": "भाषा", "te": "భాష"},
    "skip_to_content": {"en": "Skip to content", "hi": "सामग्री पर जाएँ",
                        "te": "కంటెంట్‌కు వెళ్లండి"},
    "theme_toggle": {"en": "Switch between light and dark", "hi": "लाइट/डार्क बदलें",
                     "te": "లైట్/డార్క్ మార్చండి"},
    # --- reviews ---
    "community_reviews": {"en": "Community reviews", "hi": "सामुदायिक समीक्षाएँ", "te": "కమ్యూనిటీ సమీక్షలు"},
    "write_review": {"en": "Write a review", "hi": "समीक्षा लिखें", "te": "సమీక్ష రాయండి"},
    "your_rating": {"en": "Your rating", "hi": "आपकी रेटिंग", "te": "మీ రేటింగ్"},
    "your_review": {"en": "Your review", "hi": "आपकी समीक्षा", "te": "మీ సమీక్ష"},
    "your_name": {"en": "Your name", "hi": "आपका नाम", "te": "మీ పేరు"},
    "optional": {"en": "optional", "hi": "वैकल्पिक", "te": "ఐచ్ఛికం"},
    "submit_review": {"en": "Submit review", "hi": "समीक्षा भेजें", "te": "సమీక్ష సమర్పించండి"},
    "review_placeholder": {"en": "What was your experience? Be honest and helpful.",
                           "hi": "आपका अनुभव कैसा रहा? ईमानदार और मददगार बनें।",
                           "te": "మీ అనుభవం ఎలా ఉంది? నిజాయితీగా, ఉపయోగకరంగా ఉండండి."},
    "review_note": {"en": "Reviews are moderated. Be respectful and on-topic — spam and abuse are removed.",
                    "hi": "समीक्षाएँ जाँची जाती हैं। सम्मानजनक और प्रासंगिक रहें — स्पैम और दुर्व्यवहार हटा दिए जाते हैं।",
                    "te": "సమీక్షలు పర్యవేక్షించబడతాయి. మర్యాదగా, సంబంధితంగా ఉండండి — స్పామ్, దుర్వినియోగం తొలగించబడతాయి."},
    "no_reviews": {"en": "No community reviews yet — be the first to write one below.",
                   "hi": "अभी तक कोई समीक्षा नहीं — नीचे पहली समीक्षा लिखें।",
                   "te": "ఇంకా సమీక్షలు లేవు — క్రింద మొదటి సమీక్ష రాయండి."},
    "speaks": {"en": "Speaks", "hi": "भाषाएँ", "te": "భాషలు"},
    # --- add-a-business / submit ---
    "add_business": {"en": "Add your business", "hi": "अपना व्यवसाय जोड़ें", "te": "మీ వ్యాపారాన్ని జోడించండి"},
    "add_intro": {"en": "List your Indian-American business for free. We review each submission before it goes live.",
                  "hi": "अपना भारतीय-अमेरिकी व्यवसाय मुफ़्त में सूचीबद्ध करें। प्रकाशित होने से पहले हर प्रविष्टि की समीक्षा की जाती है।",
                  "te": "మీ ఇండియన్-అమెరికన్ వ్యాపారాన్ని ఉచితంగా జాబితా చేయండి. ప్రచురించే ముందు ప్రతి సమర్పణను మేము సమీక్షిస్తాము."},
    "category": {"en": "Category", "hi": "श्रेणी", "te": "వర్గం"},
    "business_name": {"en": "Business name", "hi": "व्यवसाय का नाम", "te": "వ్యాపారం పేరు"},
    "address": {"en": "Address", "hi": "पता", "te": "చిరునామా"},
    "city": {"en": "City", "hi": "शहर", "te": "నగరం"},
    "state": {"en": "State", "hi": "राज्य", "te": "రాష్ట్రం"},
    "phone": {"en": "Phone", "hi": "फ़ोन", "te": "ఫోన్"},
    "your_email": {"en": "Your email", "hi": "आपका ईमेल", "te": "మీ ఇమెయిల్"},
    "website": {"en": "Website", "hi": "वेबसाइट", "te": "వెబ్‌సైట్"},
    "languages_spoken": {"en": "Languages spoken", "hi": "बोली जाने वाली भाषाएँ", "te": "మాట్లాడే భాషలు"},
    "anything_else": {"en": "Anything else? (specialties, region, hours)",
                      "hi": "और कुछ? (विशेषताएँ, क्षेत्र, समय)",
                      "te": "ఇంకేమైనా? (ప్రత్యేకతలు, ప్రాంతం, వేళలు)"},
    "submit_for_review": {"en": "Submit for review", "hi": "समीक्षा के लिए भेजें", "te": "సమీక్ష కోసం సమర్పించండి"},
    "comma_separated": {"en": "comma-separated", "hi": "अल्पविराम से अलग", "te": "కామాతో వేరు చేయండి"},
    "required_star": {"en": "required", "hi": "आवश्यक", "te": "అవసరం"},
    # --- browse + listing ---
    "browse": {"en": "Browse", "hi": "ब्राउज़ करें", "te": "బ్రౌజ్ చేయండి"},
    "browse_intro": {"en": "Find Indian restaurants, temples, groceries, events and more by city, across the USA.",
                     "hi": "पूरे अमेरिका में शहर के अनुसार भारतीय रेस्टोरेंट, मंदिर, ग्रोसरी, इवेंट और बहुत कुछ खोजें।",
                     "te": "అమెరికా అంతటా నగరం వారీగా ఇండియన్ రెస్టారెంట్లు, ఆలయాలు, గ్రోసరీలు, ఈవెంట్లు మరియు మరిన్ని కనుగొనండి."},
    "pick_state": {"en": "Pick a state to see cities.", "hi": "शहर देखने के लिए एक राज्य चुनें।",
                   "te": "నగరాలు చూడటానికి ఒక రాష్ట్రాన్ని ఎంచుకోండి."},
    "pick_city": {"en": "Pick a city.", "hi": "एक शहर चुनें।", "te": "ఒక నగరాన్ని ఎంచుకోండి."},
    "no_listings": {"en": "No listings yet.", "hi": "अभी तक कोई लिस्टिंग नहीं।", "te": "ఇంకా లిస్టింగ్‌లు లేవు."},
    "details_reviews": {"en": "Details & reviews", "hi": "विवरण और समीक्षाएँ", "te": "వివరాలు & సమీక్షలు"},
    "owner_verified": {"en": "Owner-verified", "hi": "स्वामी-सत्यापित", "te": "యజమాని ధృవీకరించారు"},
    "featured": {"en": "Featured", "hi": "विशेष", "te": "ఫీచర్డ్"},
    "from_web": {"en": "from the web", "hi": "वेब से", "te": "వెబ్ నుండి"},
    "community": {"en": "community", "hi": "सामुदायिक", "te": "కమ్యూనిటీ"},
    "ask_picks": {"en": "Ask for personalized picks", "hi": "व्यक्तिगत सुझावों के लिए पूछें",
                  "te": "వ్యక్తిగత సూచనల కోసం అడగండి"},
    "review_live": {"en": "Thanks! Your review is now live.", "hi": "धन्यवाद! आपकी समीक्षा अब लाइव है।",
                    "te": "ధన్యవాదాలు! మీ సమీక్ష ఇప్పుడు లైవ్‌లో ఉంది."},
    "review_pending": {"en": "Thanks! Your review was received and will appear after a quick moderation check.",
                       "hi": "धन्यवाद! आपकी समीक्षा मिल गई और जाँच के बाद दिखाई देगी।",
                       "te": "ధన్యవాదాలు! మీ సమీక్ష అందింది, త్వరిత పరిశీలన తర్వాత కనిపిస్తుంది."},
    "back_listing": {"en": "Back to the listing", "hi": "लिस्टिंग पर वापस जाएँ", "te": "లిస్టింగ్‌కు తిరిగి వెళ్ళండి"},
}


def page_lang(request: Request) -> str:
    """Visitor's UI language: the `lang` cookie (set by the chat) first, then Accept-Language, else en."""
    lang = (request.cookies.get("lang") or "").strip().lower()
    if lang in LANGS:
        return lang
    al = (request.headers.get("accept-language") or "").lower()
    for code in ("te", "hi"):
        if code in al:
            return code
    return "en"


def t(request: Request) -> dict[str, str]:
    """A {key: translated-string} map for the request's language (falls back to English per key)."""
    lang = page_lang(request)
    return {k: v.get(lang, v["en"]) for k, v in _T.items()}


def lang() -> str:
    """The current request's UI language. 'en' outside a request (CLI, agents, tests)."""
    return _CURRENT.get()


def tr(key: str, *, lang_code: str | None = None) -> str:
    """One translated string, falling back to English for a missing translation."""
    entry = _T.get(key)
    if not entry:
        return key
    return entry.get(lang_code or lang(), entry["en"])


def html_lang() -> str:
    """For <html lang="...">. Claiming English for Hindi text mispronounces it in screen readers
    and tells search engines the wrong thing."""
    return lang()


class LanguageMiddleware(BaseHTTPMiddleware):
    """Resolve the visitor's language once and expose it for the whole request."""

    async def dispatch(self, request: Request, call_next):
        token = _CURRENT.set(page_lang(request))
        try:
            return await call_next(request)
        finally:
            _CURRENT.reset(token)


def _safe_next(raw: str | None) -> str:
    """A same-site path to return to. Anything else becomes '/', so the switcher can't be used as
    an open redirect ('//evil.com' and 'https://evil.com' both look like paths to a careless check)."""
    nxt = (raw or "/").strip()
    if not nxt.startswith("/") or nxt.startswith("//") or "\\" in nxt or ":" in nxt.split("/")[0]:
        return "/"
    return nxt[:300]


def set_lang(request: Request) -> Response:
    """GET /lang/<code>?next=/path -- switch language and come back.

    A GET + cookie + redirect, so it works with no JavaScript: the previous switcher was a JS
    <select> on the chat page only, which is why the rest of the site was stuck in English.
    """
    code = (request.path_params.get("code") or "").strip().lower()
    nxt = _safe_next(request.query_params.get("next"))
    resp = RedirectResponse(nxt, status_code=303)
    if code in LANGS:
        resp.set_cookie(COOKIE, code, max_age=_COOKIE_MAX_AGE, path="/", samesite="lax",
                        httponly=False)   # the chat's JS reads it too
    return resp


def switcher_html(current_path: str = "/") -> str:
    """The language switcher for the site header: plain links, no JavaScript."""
    import html as _h

    cur = lang()
    nxt = _h.escape(_safe_next(current_path), quote=True)
    links = "".join(
        f"<a href='/lang/{code}?next={nxt}'"
        + (" class='on' aria-current='true'" if code == cur else "")
        + f" hreflang='{code}' lang='{code}'>{_h.escape(LANG_NAMES[code])}</a>"
        for code in LANGS)
    return (f"<div class='langsw' role='group' aria-label='{_h.escape(tr('language'))}'>"
            f"{links}</div>")


LANG_CSS = """
 .langsw{display:inline-flex;gap:2px;flex:0 0 auto;border:1px solid var(--line);
   border-radius:var(--r-pill);padding:2px;background:var(--panel)}
 .langsw a{display:inline-block;padding:5px 9px;border-radius:var(--r-pill);font-size:12.5px;
   font-weight:600;color:var(--muted);text-decoration:none;white-space:nowrap}
 .langsw a:hover{color:var(--brand-strong)}
 .langsw a.on{background:var(--brand-strong);color:var(--on-brand)}
 @media(max-width:520px){.langsw a{padding:5px 7px;font-size:12px}}
"""

routes = [Route("/lang/{code}", set_lang, methods=["GET"])]
