"""Server-side UI translations for the interactive secondary pages (the chat has its own JS i18n).

The visitor's language comes from the `lang` cookie — set when they pick a language in the chat —
with an Accept-Language fallback, so the review + add-a-business forms render in English, Hindi, or
Telugu. Business data (names, addresses) always stays in its original language.
"""

from __future__ import annotations

from starlette.requests import Request

LANGS = ("en", "hi", "te")

# key -> {en, hi, te}. Keep keys ASCII; values are hand-translated (verified codepoints).
_T: dict[str, dict[str, str]] = {
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
