"""Standard static / informational pages: About, Privacy, Terms, Contact, FAQ.

Content pages (vs. the form-card `_page`): a shared shell with full SEO meta (title/description/
canonical/og/twitter), the warm palette, and a site footer with OpenStreetMap ODbL attribution.
The legal text is a reasonable starting template — have it reviewed before a public launch.
"""

from __future__ import annotations

import html
import json

from starlette.requests import Request
from starlette.responses import HTMLResponse
from starlette.routing import Route

from .. import inbox
from ..config import settings
from . import seo
from .auth import verify_captcha
from .common import partner_bar
from .common import captcha_field

# SEO keywords (Google) — Namaste America is the app brand; Dost is the assistant.
_KEYWORDS = ("Namaste America, Indian America, Indian-American directory, Indian restaurants near me, "
             "Indian grocery store, Hindu temple, gurdwara, Jain temple, desi, South Asian, "
             "Indian immigration lawyer, Indian CPA, Indian tax preparer, Diwali, Holi, Navratri, "
             "Telugu Tamil Gujarati Punjabi Bengali community, Indian sweets mithai, Bharatanatyam "
             "classes, Indian salon threading, Indian realtor, NRI, MCP server, AI agent directory")


def _org_jsonld() -> str:
    base = settings.public_web_url.rstrip("/")
    return json.dumps({
        "@context": "https://schema.org", "@type": "Organization",
        "name": settings.platform_name, "url": base + "/", "logo": base + "/logo",
        "description": ("An agent-first directory & knowledge hub for Indians from India in the USA — "
                        "restaurants, temples, groceries, events, professionals and culture, "
                        "searchable by people and by AI agents."),
        "areaServed": "US",
        "knowsAbout": ["Indian restaurants", "Hindu temples", "Indian grocery stores",
                       "Indian festivals", "Indian-American community", "Indian immigration",
                       "Indian culture"],
    }, ensure_ascii=False).replace("<", "\\u003c")

# Footer links shown on every content page (and reusable elsewhere).
FOOTER_LINKS = [("Home", "/"), ("Ask " + settings.assistant_name, "/chat"), ("Browse", "/browse"),
                ("Insights", "/insights"), ("List your business", "/for-business"), ("About", "/about"),
                ("Privacy", "/privacy"), ("Terms", "/terms"), ("Contact", "/contact"), ("FAQ", "/faq")]


def footer_html() -> str:
    base = settings.public_web_url.rstrip("/")
    links = " · ".join(f"<a href='{h}'>{html.escape(t)}</a>" for t, h in FOOTER_LINKS)
    return (
        "<footer>"
        f"<div class='flinks'>{links}</div>"
        "<p class='attr'><b>Information only.</b> Listings are gathered from public sources, may be "
        "incomplete or out of date, and are <b>not legal, tax, immigration, or medical advice</b> — "
        "please verify directly with the business before relying on anything here.</p>"
        "<p class='attr'>Listing data from <a href='https://www.openstreetmap.org/copyright' "
        "rel='nofollow'>OpenStreetMap</a> contributors (ODbL) and Wikidata (CC0), enriched by "
        "automated agents and business owners. Names &amp; trademarks belong to their owners.</p>"
        f"<p class='attr'>© {html.escape(settings.platform_name)} · "
        f"<a href='/contact'>Contact</a></p></footer>")


def _doc(path: str, title: str, desc: str, body: str, status: int = 200,
         extra_jsonld: str = "") -> HTMLResponse:
    base = settings.public_web_url.rstrip("/")
    url, img = base + path, base + "/og.png"
    t, d = html.escape(title), html.escape(desc)
    doc = f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{t} · {html.escape(settings.platform_name)}</title>
<meta name="description" content="{d}">
<link rel="canonical" href="{html.escape(url)}">
<meta property="og:title" content="{t}"><meta property="og:description" content="{d}">
<meta property="og:type" content="website"><meta property="og:url" content="{html.escape(url)}">
<meta property="og:image" content="{html.escape(img)}">
<meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">
<meta property="og:image:type" content="image/png">
<meta property="og:site_name" content="{html.escape(settings.platform_name)}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{t}"><meta name="twitter:description" content="{d}">
<meta name="twitter:image" content="{html.escape(img)}">
<meta name="keywords" content="{html.escape(_KEYWORDS)}">
<script type="application/ld+json">{_org_jsonld()}</script>{extra_jsonld}
<link rel="icon" type="image/svg+xml" href="/icon.svg"><meta name="theme-color" content="#e8772e">
<style>
:root{{--brand:#e8772e;--accent:#0f9b8e;--ink:#25303a;--muted:#6b7280;--line:#efe9e1;--bg:#faf7f2}}
body{{font-family:system-ui,-apple-system,"Segoe UI",Roboto,Arial,sans-serif;color:var(--ink);
 background:var(--bg);max-width:760px;margin:0 auto;padding:0 18px 48px;line-height:1.6}}
header.top{{display:flex;align-items:center;gap:10px;padding:18px 0;border-bottom:1px solid var(--line)}}
header.top .logo{{width:34px;height:34px;border-radius:10px;display:grid;place-items:center;font-size:18px;
 background:linear-gradient(135deg,#ffd9a0,#ffb56b)}}
header.top b{{font-size:16px}} a{{color:var(--brand);text-decoration:none}} a:hover{{text-decoration:underline}}
h1{{font-size:26px;margin:26px 0 6px}} h2{{font-size:18px;margin:24px 0 6px}}
.lead{{color:var(--muted);font-size:16px}} ul{{padding-left:20px}} li{{margin:4px 0}}
.ok{{color:#137333}} .err{{color:#c5221f}}
.cta{{display:inline-block;background:var(--brand);color:#fff;border-radius:10px;padding:10px 16px;
 font-weight:600;margin-top:8px}} .cta:hover{{text-decoration:none}}
footer{{margin-top:40px;border-top:1px solid var(--line);padding-top:18px;font-size:13px;color:var(--muted)}}
footer a{{color:var(--accent)}} .flinks{{margin-bottom:8px}} .attr{{margin:6px 0}}
</style></head><body>
<header class="top"><a class="logo" href="/">🪷</a>
 <b><a href="/" style="color:var(--ink)">{html.escape(settings.platform_name)}</a></b></header>
{partner_bar()}
<main>{body}</main>
{footer_html()}
</body></html>"""
    return HTMLResponse(doc, status_code=status)


_ABOUT_CSS = """<style>
.hero{text-align:center;padding:6px 0 2px}.hero h1{font-size:32px;margin:14px 0 8px}
.tagrow{display:flex;gap:8px;justify-content:center;flex-wrap:wrap;margin:12px 0}
.pill{background:#fff;border:1px solid var(--line);border-radius:999px;padding:6px 12px;font-size:13px;color:#475467}
.ctarow{display:flex;gap:10px;justify-content:center;flex-wrap:wrap;margin:18px 0}
.card{background:#fff;border:1px solid var(--line);border-radius:14px;padding:16px 18px;margin:10px 0}
.card ul{margin:6px 0}.feat{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:12px;margin:12px 0}
.feat .f{background:#fff;border:1px solid var(--line);border-radius:12px;padding:14px}
.feat .f b{display:block;margin-bottom:4px;color:var(--ink)}.feat .f span{font-size:14px;color:var(--muted)}
</style>"""


def about(request: Request) -> HTMLResponse:
    plat = html.escape(settings.platform_name)
    a = html.escape(settings.assistant_name)
    body = _ABOUT_CSS + f"""<section class="hero">
 <h1>{plat}</h1>
 <p class="lead">Your guide to Indian America — and the first directory built for <b>both people
  and AI agents</b>. Find Indian restaurants, temples, groceries, events, classes, doctors, sweets,
  jewelry and more across the USA — or just ask {a}, your desi friend.</p>
 <div class="tagrow"><span class="pill">🍛 Restaurants</span><span class="pill">🛕 Temples</span>
  <span class="pill">🛒 Groceries</span><span class="pill">🎉 Events</span><span class="pill">🩺 Doctors</span>
  <span class="pill">⚖️ Immigration</span><span class="pill">🧾 CPAs</span><span class="pill">🤝 Community</span></div>
 <div class="ctarow"><a class="cta" href="/">💬 Ask {a}</a> <a class="cta" href="/browse">🗂️ Browse by city</a>
  <a class="cta" href="/submit">➕ Add your business</a></div>
</section>

<h2>For everyone</h2>
<div class="card">Search conversationally with <a href="/">{a}</a> (“{a}” means “friend” in Hindi &amp;
 Urdu) — by text or <b>voice</b>, in <b>English, हिंदी or తెలుగు</b>. Ask for places <i>and</i> ask
 about Indian life: “how is Pongal celebrated?”, “what's an H-1B?”, “best veg thali near me”. Results
 are nearest-first, with ratings, hours and “open now”.</div>

<h2>For businesses — why listing here is promising</h2>
<div class="card"><ul>
 <li><b>AI agents can find &amp; recommend you.</b> {plat} is an <b>MCP server</b> — AI assistants
  (and a free public API) can search the directory directly. As more people ask AI “find me an Indian
  caterer in New Jersey,” you want your business <i>in that answer</i>, not invisible.</li>
 <li><b>Humans find you too</b> — conversational search ({a}), browse-by-city, voice, and Google
  (we publish SEO-friendly pages + structured data for every listing).</li>
 <li><b>Free</b> to list, claim and correct — you stay in control of your own listing.</li>
 <li><b>Always fresh</b> — autonomous agents keep details current, and you can update anytime.</li>
</ul><a class="cta" href="/submit">➕ Add your business — free →</a></div>

<h2>Modern AI features</h2>
<div class="feat">
 <div class="f"><b>🤖 MCP server</b><span>Agent-searchable: AI tools query dozens of structured
  capabilities over the live directory.</span></div>
 <div class="f"><b>🧠 {a}, a smart assistant</b><span>Free-form answers on culture, festivals,
  temples, visas &amp; taxes — a real “little India” guide, not just a search box.</span></div>
 <div class="f"><b>🔌 Free JSON API + llms.txt</b><span>Open, documented endpoints so any app or
  agent can use the data.</span></div>
 <div class="f"><b>🎙️ Voice + multilingual</b><span>Ask and hear answers in English, हिंदी or
  తెలుగు.</span></div>
 <div class="f"><b>📍 Near-me &amp; live</b><span>Nearest-first results, “open now”, ratings and
  freshness signals.</span></div>
 <div class="f"><b>🌱 Self-updating</b><span>Autonomous agents discover, enrich and verify listings
  continuously.</span></div>
</div>

<p class="lead" style="margin-top:18px">Focused on the Indian (from India) diaspora in the USA — a
 little India, searchable by the world.</p>
<div class="ctarow"><a class="cta" href="/">💬 Ask {a}</a> <a class="cta" href="/submit">➕ Add your business</a></div>"""
    return _doc("/about", f"{settings.platform_name} — Indian America, searchable by people & AI",
                f"{settings.platform_name} is an agent-first directory & AI guide ({settings.assistant_name}) "
                "for Indians from India in the USA — find restaurants, temples, groceries, events, "
                "doctors and more, or list your business free. Built for people and AI agents (MCP).",
                body)


def privacy(request: Request) -> HTMLResponse:
    plat = html.escape(settings.platform_name)
    body = f"""<h1>Privacy Policy</h1>
<p class="lead">Last updated: June 2026. {plat} (“we”, “us”) respects your privacy and collects as
 little as possible. This policy explains what we collect, why, and the choices you have.</p>

<h2>1. Information we collect</h2>
<ul>
<li><b>Location (optional).</b> If you allow it, your browser shares approximate coordinates so we
 can show the nearest listings. We use them only for that search and don't store them with your
 identity. If you decline, we may estimate your city-level area from your IP address, or simply ask
 which city you mean.</li>
<li><b>Usage data.</b> We log aggregate, non-identifying activity — for example which searches
 return no results — to improve coverage and reliability. This may include your search text and
 approximate area.</li>
<li><b>Business accounts.</b> If you register or claim a business, we collect your email address
 and, if you set one, a password stored only as a salted one-way hash (never in plain text).
 Listing details you provide are published in the directory.</li>
<li><b>Reviews you post.</b> A star rating, your review text, an optional display name, and (only if
 you provide it) an email used solely to contact you about the review — your email is never
 published. Reviews are public and moderated.</li>
<li><b>Cookies.</b> A signed session cookie is used only for admin and business-owner logins. We
 don't use cookies to track general visitors for advertising.</li>
</ul>

<h2>2. Analytics</h2>
<p>We use <b>Google Analytics 4</b> to understand aggregate site usage (pages viewed, rough
 geography, device type). It may set its own cookies; Google Analytics 4 does not store full IP
 addresses. See <a href="https://policies.google.com/privacy" rel="nofollow">Google's Privacy
 Policy</a>. We don't use Analytics to identify you personally. You can opt out with Google's
 <a href="https://tools.google.com/dlpage/gaoptout" rel="nofollow">opt-out add-on</a> or by blocking
 analytics cookies in your browser.</p>

<h2>3. How we use information</h2>
<ul>
<li>To return relevant, nearby results and answer your questions.</li>
<li>To maintain and improve the directory (e.g. find gaps in coverage).</li>
<li>To operate business-owner accounts and verify listing ownership.</li>
<li>To contact a business about claiming or correcting its listing — every such message has a
 one-click unsubscribe.</li>
</ul>

<h2>4. Sharing</h2>
<p>We do <b>not</b> sell your personal data. We share data only with service providers that help us
 operate (e.g. Google Analytics, our email provider) and where required by law. Public listing
 information is, by design, publicly visible and available through our search, JSON API, and
 AI-agent (MCP) interfaces.</p>

<h2>5. Data retention</h2>
<p>We keep aggregate usage logs for a limited period to analyze trends, and account data for as long
 as your account is active. You can ask us to delete your account data at any time.</p>

<h2>6. Your choices &amp; rights</h2>
<ul>
<li>Decline or revoke location access in your browser at any time.</li>
<li>Opt out of analytics (see above).</li>
<li>Businesses can claim, correct, or request removal of a listing for free.</li>
<li>Request access to or deletion of your account data by emailing us.</li>
</ul>

<h2>7. Children</h2>
<p>This service is intended for adults and is not directed to children under 13; we don't knowingly
 collect personal information from children.</p>

<h2>8. Security</h2>
<p>We use reasonable measures (HTTPS, hashed passwords, minimal data collection) to protect
 information, but no method of transmission or storage is 100% secure.</p>

<h2>9. Changes</h2>
<p>We may update this policy; material changes are reflected by the “last updated” date above.</p>

<h2>10. Contact</h2>
<p>Questions or removal requests: please use our <a href="/contact">contact form</a>.</p>"""
    return _doc("/privacy", "Privacy Policy",
                "How we handle location, logging, cookies, analytics, accounts, and business "
                "outreach — minimal data, no selling, easy opt-out.", body)


def terms(request: Request) -> HTMLResponse:
    plat = html.escape(settings.platform_name)
    body = f"""<h1>Terms of Use</h1>
<p class="lead">Last updated: June 2026. By using {plat} you agree to these terms — please read them.</p>

<h2>1. What this is</h2>
<p>{plat} is a free, informational directory and assistant for the Indian (from India) community in
 the USA. It helps you discover businesses, temples, events and community resources, and answers
 general questions.</p>

<h2>2. Information only — not professional advice</h2>
<p>All content is provided <b>for general information only</b> and <b>“as is”</b>, without
 warranties of any kind. Listing details are gathered from public sources, automated agents, and
 submissions, and <b>may be incomplete, inaccurate, or out of date</b>. Nothing here is <b>legal,
 tax, immigration, financial, or medical advice</b>. <b>Always verify details directly with the
 business and consult a qualified professional</b> before relying on any information. You use the
 service at your own risk.</p>

<h2>3. Business listings</h2>
<ul>
<li>We are <b>not affiliated</b> with listed businesses unless stated; names and trademarks belong
 to their owners, and a listing is not an endorsement.</li>
<li>Owners may register, claim, correct, or request removal of their listing for free.</li>
</ul>

<h2>4. Accounts &amp; registration</h2>
<ul>
<li>To manage a business you must register with a valid email (which we verify) or sign in with
 Google, and accept these Terms and the <a href="/privacy">Privacy Policy</a>.</li>
<li>Provide accurate information and keep your password secure; you're responsible for activity
 under your account.</li>
<li>Only list businesses you're authorized to represent.</li>
<li>We may suspend accounts or remove content that is fraudulent, spammy, unlawful, or off-topic.</li>
</ul>

<h2>5. Your submissions &amp; reviews</h2>
<p>When you add or edit a listing, you confirm the information is accurate and that you have the
 right to share it, and you grant us a non-exclusive license to display and distribute it through
 the directory, API, and AI-agent interfaces. Don't submit false, misleading, infringing, or spam
 content.</p>
<p><b>Reviews &amp; ratings.</b> If you post a review or star rating, it is <b>public</b> and shown
 with the name you provide (or “Anonymous”); any email you give is used only to contact you about the
 review and is <b>never published</b>. Reviews are <b>moderated</b> — we may decline, hold, or remove
 content that is spam, advertising, hateful, harassing, defamatory, off-topic, fake, or that reveals
 someone's private information. Post only your own genuine, first-hand experience; you grant us a
 non-exclusive license to display it, and you remain responsible for what you post.</p>

<h2>6. Acceptable use</h2>
<ul>
<li>Don't scrape, overload, disrupt, or misuse the service. Automated access should use our
 provided tools (MCP server / JSON API) and respect rate limits.</li>
<li>Don't use the service for unlawful purposes or to harass others.</li>
</ul>

<h2>7. Intellectual property &amp; data</h2>
<p>Listing data derived from OpenStreetMap is © OpenStreetMap contributors, licensed under the
 <a href="https://opendatacommons.org/licenses/odbl/" rel="nofollow">ODbL</a>; data from Wikidata is
 CC0. Our own text, design, and branding remain ours.</p>

<h2>8. Limitation of liability</h2>
<p>To the fullest extent permitted by law, {plat} and its operators are not liable for any indirect,
 incidental, or consequential damages, or for any loss arising from your use of — or reliance on —
 the service or any listing. The service is provided without warranty of accuracy or availability.</p>

<h2>9. Changes</h2>
<p>We may update these terms; continued use after changes means you accept them. The “last updated”
 date reflects the latest version.</p>

<h2>10. Contact</h2>
<p>Questions: please use our <a href="/contact">contact form</a>.</p>
<p class="lead" style="font-size:13px;margin-top:18px">This is a general template provided for
 convenience, not legal advice; have a lawyer review it before relying on it.</p>"""
    return _doc("/terms", "Terms of Use",
                "Terms for using the directory: information-only/as-is, no professional advice, "
                "accounts & submissions, acceptable use, IP, and liability.", body)


_CONTACT_CSS = """<style>
.cform label{display:block;font-weight:600;font-size:14px;margin:12px 0 4px;color:#3a4654}
.cform input,.cform textarea{width:100%;padding:11px 12px;border:1.5px solid #e3ddd3;border-radius:11px;
 font:inherit;font-size:15px;background:#fff}
.cform input:focus,.cform textarea:focus{outline:0;border-color:var(--brand);box-shadow:0 0 0 4px #e8772e22}
.cform .hp{position:absolute;left:-9999px}
.cform button{margin-top:16px;background:var(--brand);color:#fff;border:0;padding:13px 24px;border-radius:11px;
 font-size:15px;font-weight:600;cursor:pointer}.cform button:hover{filter:brightness(1.05)}
</style>"""


def contact(request: Request) -> HTMLResponse:
    a = html.escape(settings.assistant_name)
    body = _CONTACT_CSS + f"""<h1>Contact us</h1>
<p class="lead">Questions, ideas, corrections, or data you'd like us to add — send us a message and
 we'll get back to you. (Fastest help: just <a href="/chat">ask {a}</a> or
 <a href="/submit">add a business</a>.)</p>
<form class="cform" method="post" action="/contact" autocomplete="on">
 <input class="hp" type="text" name="website" tabindex="-1" autocomplete="off" aria-hidden="true">
 <label>Your name</label><input name="name" maxlength="120">
 <label>Your email <span style="font-weight:400;color:#6b7280">(so we can reply)</span></label>
 <input name="email" type="email" required maxlength="200">
 <label>Subject</label><input name="subject" maxlength="200">
 <label>Message</label><textarea name="body" rows="6" required maxlength="5000"></textarea>
 {captcha_field()}
 <button type="submit">Send message</button>
</form>"""
    return _doc("/contact", "Contact",
                "Send us a message — questions, corrections, partnerships, or data requests.", body)


async def contact_post(request: Request) -> HTMLResponse:
    form = await request.form()
    if (form.get("website") or "").strip():            # honeypot: bots fill it -> silently accept
        return _doc("/contact", "Thanks", "Your message has been received.",
                    "<h1>Thanks!</h1><p>Your message has been received.</p>")
    email = (form.get("email") or "").strip()
    msg = (form.get("body") or "").strip()
    if not email or "@" not in email or not msg:
        return _doc("/contact", "Contact", "Please add your email and a message.",
                    "<h1 class='err'>Please add your email and a message</h1>"
                    "<p><a href='/contact'>&#8592; Back to the form</a></p>", status=400)
    if not verify_captcha(form):
        return _doc("/contact", "Contact", "The captcha answer was incorrect.",
                    "<h1 class='err'>The captcha answer was incorrect</h1>"
                    "<p><a href='/contact'>&#8592; Try again</a></p>", status=400)
    ip = request.client.host if request.client else None
    try:
        inbox.create_message(form.get("name") or "", email, form.get("subject") or "", msg, ip)
    except Exception:
        pass
    return _doc("/contact", "Message sent", "Thanks — your message was received.",
                "<h1 class='ok'>&#10003; Thanks — message received</h1>"
                "<p>We've got your message and will reply to your email soon. Meanwhile, you can "
                "<a href='/chat'>ask " + html.escape(settings.assistant_name) + "</a> anything.</p>")


def _faq_pairs() -> list[tuple[str, str]]:
    a = html.escape(settings.assistant_name)
    plat = html.escape(settings.platform_name)
    return [
        ("What is " + settings.platform_name + "?",
         f"A free directory and AI guide of Indian-American businesses, temples, classes, services and "
         f"events across the USA — searchable by chatting with {a} or browsing by city. It's built for "
         f"both people and AI agents (it's an MCP server with a free public API)."),
        ("Is it free?",
         "Yes — searching is free, and listing or claiming a business is free."),
        ("Can I search in Hindi or Telugu?",
         f"Yes. You can ask {a} by text or voice in <b>English, हिंदी or తెలుగు</b>, and get answers "
         f"back in the same language."),
        ("How does “near me” work?",
         "With your permission we use your device location (or an approximate area from your IP) to "
         "show the <b>nearest</b> matches first. You can also just type a city."),
        ("Where does the data come from?",
         "Open data (OpenStreetMap, Wikidata), businesses' own websites, and submissions from owners "
         "and visitors — kept fresh by automated agents."),
        ("Can AI assistants use this directory?",
         f"Yes — {plat} is an <b>MCP server</b>, so AI assistants can search the live directory "
         f"directly, plus there's a free JSON API and an <a href='/llms.txt'>llms.txt</a>. See "
         f"<a href='/for-agents'>/for-agents</a>."),
        ("How do reviews work?",
         "Anyone can leave a star rating and review on a listing. Reviews are public and moderated — "
         "spam, abuse, and fake content are removed."),
        ("My business is wrong or missing.",
         "You can <a href='/submit'>add it</a> or claim and correct an existing listing for free."),
        ("Is this only for Indian (from India) businesses?",
         "Yes — it focuses on the Indian (from India) / Indian-American diaspora in the USA."),
    ]


def faq(request: Request) -> HTMLResponse:
    a = html.escape(settings.assistant_name)
    pairs = _faq_pairs()
    qa = "".join(f"<h2>{html.escape(q)}</h2><p>{ans}</p>" for q, ans in pairs)
    body = f"<h1>Frequently asked questions</h1>{qa}<a class=\"cta\" href=\"/chat\">Ask {a} →</a>"
    return _doc("/faq", "FAQ",
                "Answers about what this directory is, how 'near me' works, multilingual search, the "
                "MCP/API for AI agents, reviews, and how to add or fix a listing.", body,
                extra_jsonld=seo.faq_jsonld(pairs))


routes = [
    Route("/about", about, methods=["GET"]),
    Route("/privacy", privacy, methods=["GET"]),
    Route("/terms", terms, methods=["GET"]),
    Route("/contact", contact, methods=["GET"]),
    Route("/contact", contact_post, methods=["POST"]),
    Route("/faq", faq, methods=["GET"]),
]
