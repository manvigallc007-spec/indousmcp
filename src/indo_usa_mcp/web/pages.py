"""Standard static / informational pages: About, Privacy, Terms, Contact, FAQ.

Content pages (vs. the form-card `_page`): a shared shell with full SEO meta (title/description/
canonical/og/twitter), the warm palette, and a site footer with OpenStreetMap ODbL attribution.
The legal text is a reasonable starting template — have it reviewed before a public launch.
"""

from __future__ import annotations

import html

from starlette.requests import Request
from starlette.responses import HTMLResponse
from starlette.routing import Route

from ..config import settings

# Footer links shown on every content page (and reusable elsewhere).
FOOTER_LINKS = [("Home", "/"), ("Ask " + settings.assistant_name, "/chat"), ("Browse", "/browse"),
                ("Insights", "/insights"), ("Add a listing", "/submit"), ("About", "/about"),
                ("Privacy", "/privacy"), ("Terms", "/terms"), ("Contact", "/contact"), ("FAQ", "/faq")]


def footer_html() -> str:
    base = settings.public_web_url.rstrip("/")
    links = " · ".join(f"<a href='{h}'>{html.escape(t)}</a>" for t, h in FOOTER_LINKS)
    return (
        "<footer>"
        f"<div class='flinks'>{links}</div>"
        "<p class='attr'>Listing data from <a href='https://www.openstreetmap.org/copyright' "
        "rel='nofollow'>OpenStreetMap</a> contributors (ODbL) and Wikidata (CC0), enriched by "
        "automated agents and business owners. Names &amp; trademarks belong to their owners.</p>"
        f"<p class='attr'>© {html.escape(settings.platform_name)} · "
        f"<a href='mailto:{html.escape(settings.outreach_contact_email)}'>"
        f"{html.escape(settings.outreach_contact_email)}</a></p></footer>")


def _doc(path: str, title: str, desc: str, body: str, status: int = 200) -> HTMLResponse:
    base = settings.public_web_url.rstrip("/")
    url, img = base + path, base + "/og-image.svg"
    t, d = html.escape(title), html.escape(desc)
    doc = f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{t} · {html.escape(settings.platform_name)}</title>
<meta name="description" content="{d}">
<link rel="canonical" href="{html.escape(url)}">
<meta property="og:title" content="{t}"><meta property="og:description" content="{d}">
<meta property="og:type" content="website"><meta property="og:url" content="{html.escape(url)}">
<meta property="og:image" content="{html.escape(img)}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{t}"><meta name="twitter:description" content="{d}">
<meta name="twitter:image" content="{html.escape(img)}">
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
.cta{{display:inline-block;background:var(--brand);color:#fff;border-radius:10px;padding:10px 16px;
 font-weight:600;margin-top:8px}} .cta:hover{{text-decoration:none}}
footer{{margin-top:40px;border-top:1px solid var(--line);padding-top:18px;font-size:13px;color:var(--muted)}}
footer a{{color:var(--accent)}} .flinks{{margin-bottom:8px}} .attr{{margin:6px 0}}
</style></head><body>
<header class="top"><a class="logo" href="/">🪷</a>
 <b><a href="/" style="color:var(--ink)">{html.escape(settings.platform_name)}</a></b></header>
<main>{body}</main>
{footer_html()}
</body></html>"""
    return HTMLResponse(doc, status_code=status)


def about(request: Request) -> HTMLResponse:
    a = html.escape(settings.assistant_name)
    body = f"""<h1>About {html.escape(settings.platform_name)}</h1>
<p class="lead">A free, community directory of Indian-American life across the USA — restaurants,
 groceries, temples, doctors, salons, sweets, classes, jewelry, money-transfer/travel services,
 community associations and events.</p>
<h2>Built for people and AI</h2>
<p>Listings are discovered and kept fresh by automated agents (from open data like OpenStreetMap
 and Wikidata), enriched from businesses' own websites, and corrected by owners and visitors.
 You can search it conversationally through <a href="/chat">{a}</a> — our friendly assistant
 (“{a}” means “friend” in Hindi &amp; Urdu) — or browse by city. AI assistants can use it too,
 via our open tools.</p>
<h2>Free to use, free to list</h2>
<p>Searching is free. Businesses can <a href="/submit">add a listing</a> or claim and correct an
 existing one at no cost.</p>
<a class="cta" href="/chat">Ask {a} →</a>"""
    return _doc("/about", f"About {settings.platform_name}",
                "A free community directory of Indian-American businesses, temples, and events "
                "across the USA — searchable conversationally or by city.", body)


def privacy(request: Request) -> HTMLResponse:
    email = html.escape(settings.outreach_contact_email)
    body = f"""<h1>Privacy Policy</h1>
<p class="lead">We keep this simple and collect as little as possible.</p>
<h2>Location</h2>
<ul>
<li><b>Your device location is optional.</b> If you allow it, your browser shares approximate
 coordinates so we can show the nearest listings. We use them only for that search and don't store
 them with your identity.</li>
<li>If you don't share device location, we may estimate your <b>approximate area from your IP
 address</b> (city-level only) to still show nearby results, or simply ask which city you mean.</li>
</ul>
<h2>What we log</h2>
<ul>
<li>Aggregate, non-identifying usage — e.g. which searches return no results — to improve coverage.</li>
<li>A session cookie is used only for admin and business-owner logins, not for general visitors.</li>
<li>We don't sell personal data or run third-party ad trackers.</li>
</ul>
<h2>Business listings &amp; outreach</h2>
<p>Listing details come from public sources and owners. If we email a business about claiming its
 listing, every message includes a one-click unsubscribe. To be removed, use that link or email
 <a href="mailto:{email}">{email}</a>.</p>
<h2>Contact</h2>
<p>Questions or removal requests: <a href="mailto:{email}">{email}</a>.</p>"""
    return _doc("/privacy", "Privacy Policy",
                "How we handle location, logging, cookies, and business outreach — minimal data, "
                "no selling, easy opt-out.", body)


def terms(request: Request) -> HTMLResponse:
    email = html.escape(settings.outreach_contact_email)
    body = f"""<h1>Terms of Use</h1>
<p class="lead">Plain-English terms for using this directory.</p>
<ul>
<li>The directory is provided <b>“as is”</b>. Listing details are gathered from public sources and
 may be incomplete or out of date — always confirm with the business directly.</li>
<li>We are <b>not affiliated</b> with the listed businesses unless stated. Names and trademarks
 belong to their owners.</li>
<li>Business owners may claim, correct, or request removal of their listing for free.</li>
<li>Don't scrape, overload, or misuse the service; automated access should use our provided tools
 and respect rate limits.</li>
<li>Listing data derived from OpenStreetMap is © OpenStreetMap contributors, licensed under the
 <a href="https://opendatacommons.org/licenses/odbl/" rel="nofollow">ODbL</a>.</li>
</ul>
<p>Questions: <a href="mailto:{email}">{email}</a>.</p>"""
    return _doc("/terms", "Terms of Use",
                "Plain-English terms: the directory is provided as-is, data may be imperfect, "
                "owners can claim/correct/remove listings.", body)


def contact(request: Request) -> HTMLResponse:
    email = html.escape(settings.outreach_contact_email)
    body = f"""<h1>Contact</h1>
<p class="lead">We'd love to hear from you.</p>
<ul>
<li><b>Add or fix a listing:</b> <a href="/submit">submit a business</a>, or claim an existing one
 from its page.</li>
<li><b>Email:</b> <a href="mailto:{email}">{email}</a> — corrections, removals, partnerships, or feedback.</li>
<li><b>Ask {html.escape(settings.assistant_name)}:</b> try the <a href="/chat">chat</a> to find
 what you need fast.</li>
</ul>"""
    return _doc("/contact", "Contact",
                "Get in touch — add or fix a listing, email us, or ask the assistant.", body)


def faq(request: Request) -> HTMLResponse:
    a = html.escape(settings.assistant_name)
    body = f"""<h1>Frequently asked questions</h1>
<h2>What is this?</h2>
<p>A free directory of Indian-American businesses, temples, classes, services and events across the
 USA, searchable by chatting with {a} or browsing by city.</p>
<h2>Is it free?</h2>
<p>Yes — searching is free, and listing or claiming a business is free.</p>
<h2>How does “near me” work?</h2>
<p>With your permission we use your device location (or an approximate area from your IP) to show
 the <b>nearest</b> matches first. You can also just type a city.</p>
<h2>Where does the data come from?</h2>
<p>Open data (OpenStreetMap, Wikidata), businesses' own websites, and submissions from owners and
 visitors — kept fresh by automated agents.</p>
<h2>My business is wrong or missing.</h2>
<p>You can <a href="/submit">add it</a> or claim and correct an existing listing for free.</p>
<h2>Is this only for Indian (from India) businesses?</h2>
<p>Yes — it focuses on the Indian (from India) / Indian-American diaspora in the USA.</p>
<a class="cta" href="/chat">Ask {a} →</a>"""
    return _doc("/faq", "FAQ",
                "Answers about what this directory is, how 'near me' works, where the data comes "
                "from, and how to add or fix a listing.", body)


routes = [
    Route("/about", about, methods=["GET"]),
    Route("/privacy", privacy, methods=["GET"]),
    Route("/terms", terms, methods=["GET"]),
    Route("/contact", contact, methods=["GET"]),
    Route("/faq", faq, methods=["GET"]),
]
