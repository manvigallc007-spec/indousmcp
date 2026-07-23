"""Human-facing chat front-end: a conversational search over the directory.

GET  /chat       -> the chat page (vanilla JS, no build step)
POST /chat/api   -> {messages, geo, filters} -> {reply, cards, provider}  (calls assistant.reply)
"""

from __future__ import annotations

import html
import json
import time

from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from starlette.routing import Route

from .. import assistant, flyer, verticals
from . import homeportal
from ..config import settings
from .auth import portal_email
from .common import analytics_tag, partner_bar

# --- tiny in-memory per-IP rate limiter (abuse guard; LLM calls cost CPU or money) ---
_HITS: dict[str, list[float]] = {}


def _rate_ok(ip: str) -> bool:
    now = time.time()
    window = [t for t in _HITS.get(ip, []) if now - t < 60]
    if len(window) >= settings.chat_rate_per_min:
        _HITS[ip] = window
        return False
    window.append(now)
    _HITS[ip] = window
    return True


_SUGGESTIONS = [
    "Biryani near me",
    "Indian catering for a party",
    "Vegetarian South Indian near me",
    "Sweets shop for Diwali in Edison NJ",
    "Hindu temple in the Bay Area",
    "Bharatanatyam dance class",
]

# Per-category icon + accent colour for the result cards.
_CAT_ICON = {"restaurants": "🍛", "temples": "🛕", "groceries": "🛒", "professionals": "🩺",
             "salons": "💇", "events": "🎉", "apparel": "👗", "sweets": "🍬", "studios": "🧘",
             "services": "💸", "community": "🤝", "legal": "⚖️", "education": "📚",
             "realestate": "🏡", "finance": "🧾", "movies": "🎬", "employers": "💼"}
_CAT_COLOR = {"restaurants": "#c1440e", "temples": "#b8860b", "groceries": "#2e7d32",
              "professionals": "#1565c0", "salons": "#ad1457", "events": "#6a1b9a",
              "apparel": "#c2185b", "sweets": "#e65100", "studios": "#00838f",
              "services": "#37474f", "community": "#5d4037", "legal": "#3949ab",
              "education": "#00897b", "realestate": "#8d6e63", "finance": "#546e7a",
              "movies": "#7b1fa2", "employers": "#455a64"}
# One-line descriptor per category — the shared "identity" used on cards/headers everywhere.
_CAT_BLURB = {"restaurants": "Dosa, biryani, thali & more", "temples": "Hindu · Sikh · Jain",
              "groceries": "Spices, produce, frozen", "professionals": "Doctors, dentists, clinics",
              "salons": "Threading, henna, bridal", "events": "Festivals, garba, concerts",
              "apparel": "Sarees, lehengas, jewelry", "sweets": "Mithai & Indian bakeries",
              "studios": "Yoga, dance & music", "services": "Money transfer, travel, visa",
              "community": "Associations & cultural orgs", "legal": "Immigration & attorneys",
              "education": "Tutoring, language & heritage", "realestate": "Realtors & home loans",
              "finance": "CPAs, tax & advisors"}

# Modern chat UI. Placeholders (__NAME__) are filled by .replace() so the CSS/JS braces
# don't need f-string escaping.
_CHAT_HTML = """<!doctype html><html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>__PLAT__ — __PTAG__</title>
<meta name="description" content="__OGDESC__">
<meta name="keywords" content="__KEYWORDS__">
<meta property="og:title" content="__PLAT__ — __PTAG__">
<meta property="og:description" content="__OGDESC__">
<meta property="og:type" content="website">
<meta property="og:url" content="__OGURL__">
<meta property="og:image" content="__OGIMG__">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:type" content="image/png">
<meta property="og:image:alt" content="__PLAT__ — __PTAG__">
<meta property="og:site_name" content="__PLAT__">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="__PLAT__ — __PTAG__">
<meta name="twitter:description" content="__OGDESC__">
<meta name="twitter:image" content="__OGIMG__">
<link rel="canonical" href="__OGURL__">
<link rel="icon" type="image/svg+xml" href="/icon.svg">
<link rel="manifest" href="/manifest.webmanifest"><meta name="theme-color" content="#e8772e">
__GA__
<script type="application/ld+json">__JSONLD__</script>
<script>if('serviceWorker' in navigator){window.addEventListener('load',function(){navigator.serviceWorker.register('/sw.js').catch(function(){})})}</script>
<style>
:root{--brand:#e8772e;--brand-d:#cf6212;--accent:#0f9b8e;--accent-d:#0c7e74;
 --bg:#faf8f4;--panel:#fff;--ink:#222b33;--muted:#667085;--line:#ece6dd;--ring:#e8772e26}
*{box-sizing:border-box}html,body{height:100%}html{font-size:16.5px}
body{margin:0;font-family:system-ui,-apple-system,"Segoe UI",Roboto,Arial,sans-serif;
 color:var(--ink);background:var(--bg);display:flex;flex-direction:column;height:100dvh;
 line-height:1.55;-webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility}
a{color:var(--brand);text-decoration:none}
.topbar{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:12px 20px;
 background:var(--panel);border-bottom:1px solid var(--line);position:sticky;top:0;z-index:5}
.brand{display:flex;align-items:center;gap:11px;color:var(--ink)}
.brand .logo{width:46px;height:46px;border-radius:13px;display:grid;place-items:center;
 background:linear-gradient(135deg,#ffd9a0,#ffb56b);font-size:24px}
.brand .brandlogo{height:46px;width:auto;max-width:200px;border-radius:10px;display:block}
.brand b{font-size:18px;line-height:1.15;display:block;font-weight:800;letter-spacing:-.01em}
.brand i{font-style:normal;font-size:12.5px;color:var(--muted)}
.actions{display:flex;align-items:center;gap:10px}
.newchat{background:#fff;border:1px solid var(--line);color:var(--ink);border-radius:10px;padding:8px 13px;
 font-size:14px;font-weight:600;cursor:pointer;display:flex;align-items:center;gap:6px;transition:.15s}
.newchat:hover{border-color:var(--brand);color:var(--brand)}
.langsel{border:1px solid var(--line);border-radius:10px;padding:8px 9px;font-size:14px;background:#fff;color:var(--ink);cursor:pointer}
.iconbtn{background:#fff;border:1px solid var(--line);border-radius:10px;padding:8px 10px;font-size:16px;cursor:pointer;line-height:1;transition:.15s}
.iconbtn:hover{border-color:var(--accent)}.iconbtn.on{border-color:var(--accent);background:#e7f6f4}
.micbtn{flex:0 0 auto;width:44px;height:44px;border:1.5px solid #e3ddd3;border-radius:13px;background:#fff;
 cursor:pointer;font-size:19px;line-height:1;transition:.15s}.micbtn:hover{border-color:var(--accent)}
.micbtn.rec{background:#ffe3e3;border-color:#e57373;animation:micpulse 1s infinite}
@keyframes micpulse{0%,100%{opacity:1}50%{opacity:.45}}
.voicebtn{flex:0 0 auto;display:inline-flex;align-items:center;gap:7px;height:44px;padding:0 16px;border-radius:13px;
 border:1.5px solid var(--accent);background:#e7f6f4;color:var(--accent-d);font-size:15px;font-weight:600;
 cursor:pointer;transition:.15s;line-height:1}.voicebtn svg{width:18px;height:18px}
.voicebtn:hover{background:var(--accent);color:#fff}
.voicebtn.on{background:var(--accent);border-color:var(--accent);color:#fff;animation:micpulse 1.4s infinite}
.convobar{max-width:820px;margin:0 auto;display:flex;align-items:center;justify-content:center;gap:16px;
 padding:13px 18px;background:#e7f6f4;border-top:1px solid var(--line);color:var(--accent-d);font-weight:600;font-size:15px}
.convobar .cstop{background:#fff;border:1px solid var(--accent);color:var(--accent);border-radius:10px;
 padding:7px 16px;font-size:14px;font-weight:600;cursor:pointer}.convobar .cstop:hover{background:var(--accent);color:#fff}
.status{display:flex;align-items:center;gap:7px;font-size:13px;color:var(--muted)}
.status .dot{width:9px;height:9px;border-radius:50%;background:#16a34a;box-shadow:0 0 0 3px #16a34a22}
@media(max-width:680px){.status{display:none}}
.filterbar{display:flex;gap:9px;overflow-x:auto;white-space:nowrap;padding:11px 18px;
 background:var(--panel);border-bottom:1px solid var(--line);-webkit-overflow-scrolling:touch}
.filterbar::-webkit-scrollbar{display:none}
.fchip{flex:0 0 auto;background:#fff;border:1px solid var(--line);color:#475467;border-radius:999px;
 padding:8px 15px;font-size:14px;cursor:pointer;transition:.15s}
.fchip:hover{border-color:#cfcdca}.fchip.on{background:var(--brand);color:#fff;border-color:var(--brand)}
.fchip.open.on{background:#137333;border-color:#137333}
.fchip.loc{color:var(--brand);border-color:#e7c3b6}
#log{flex:1;overflow-y:auto;scroll-behavior:smooth}
.wrap{max-width:820px;margin:0 auto;padding:22px 18px 10px;width:100%}
.welcome{max-width:660px;margin:7vh auto 0;padding:0 20px;text-align:center}
.hero-avatar{width:76px;height:76px;border-radius:22px;margin:0 auto 18px;display:grid;
 place-items:center;font-size:38px;background:linear-gradient(135deg,#ffd9a0,#ffb56b);box-shadow:0 10px 30px #e8772e2e}
.welcome h1{font-size:30px;line-height:1.2;margin:0 0 10px;letter-spacing:-.01em}
.welcome p{color:var(--muted);font-size:17px;margin:0 0 22px;line-height:1.55}
.herocard{background:linear-gradient(135deg,#fff4ea,#ffe7d3);border:1px solid #f2e2d0;
 border-radius:24px;padding:28px 26px 24px;margin:0 0 20px}
.herocard h1{margin:0 0 8px} .herocard .heroSub{color:#8a745e;margin:0}
.herocard .hero-avatar{margin-bottom:16px}
.disclaimer-note{background:#fff8ee;border:1px solid #f1dcc0;border-radius:12px;color:#7a5a2e !important;
 font-size:13.5px !important;line-height:1.5;padding:10px 14px;margin:0 auto 20px !important;max-width:560px}
.chips{display:flex;flex-wrap:wrap;gap:10px;justify-content:center}
.chip{background:#fff;border:1px solid var(--line);color:#344054;border-radius:999px;padding:10px 16px;
 font-size:14px;cursor:pointer;transition:.15s}.chip:hover{border-color:var(--brand);color:var(--brand)}
.voicecta{margin:26px auto 4px;display:inline-flex;align-items:center;gap:9px;background:var(--accent);
 color:#fff;border:0;border-radius:999px;padding:14px 28px;font-size:17px;font-weight:600;cursor:pointer;
 box-shadow:0 8px 22px #0f9b8e38;transition:.15s}.voicecta:hover{background:var(--accent-d);transform:translateY(-1px)}
.voicetip{color:var(--muted);font-size:14px;margin:8px 0 0}
.browsecat{margin:16px auto 0;display:inline-flex;align-items:center;gap:8px;background:#fff;border:1.5px solid var(--brand);
 color:var(--brand);border-radius:999px;padding:11px 24px;font-size:15px;font-weight:600;cursor:pointer;transition:.15s}
.browsecat:hover{background:var(--brand);color:#fff;text-decoration:none}
.browselink{margin:18px 0 0;font-size:15px}.browselink a{color:var(--accent);font-weight:600}
.welcome-contrib{margin-top:26px;color:var(--muted);font-size:15px}
.topnav{display:flex;gap:18px;font-size:14px}.topnav a{color:var(--ink);font-weight:500}
.topnav a:hover{color:var(--brand)}
@media(max-width:880px){.topnav{display:none}}
.trustrow{display:flex;gap:8px;flex-wrap:wrap;justify-content:center;margin:2px 0 20px}
.tpill{background:#fff;border:1px solid var(--line);border-radius:999px;padding:5px 12px;font-size:12.5px;color:#475467}
.homefoot{margin:32px auto 4px;max-width:640px;border-top:1px solid var(--line);padding-top:16px;text-align:center}
.homefoot .disclaim{font-size:12.5px;color:var(--muted);line-height:1.55;margin:0 0 10px}
.homefoot .footnav{font-size:13px;margin:0 0 8px;line-height:1.9}.homefoot .footnav a{color:var(--accent);font-weight:500}
.homefoot .copyr{font-size:12px;color:#98a2b3;margin:0}
.msg{display:flex;gap:11px;margin:18px 0;align-items:flex-start}.msg.user{justify-content:flex-end}
.avatar{flex:0 0 auto;width:34px;height:34px;border-radius:10px;display:grid;place-items:center;
 font-size:18px;background:linear-gradient(135deg,#ffd9a0,#ffb56b)}
.content{max-width:calc(100% - 48px)}
.bubble{padding:13px 17px;border-radius:16px;line-height:1.6;font-size:16px;white-space:pre-wrap;word-wrap:break-word}
.bot .bubble{background:var(--panel);border:1px solid var(--line);border-top-left-radius:6px;box-shadow:0 1px 2px rgba(16,24,40,.04)}
.user .bubble{background:var(--brand);color:#fff;border-top-right-radius:6px;max-width:82%}
.typing{display:inline-flex;gap:5px;padding:4px 2px}
.typing span{width:8px;height:8px;border-radius:50%;background:#c9c7c4;animation:bl 1.2s infinite}
.typing span:nth-child(2){animation-delay:.15s}.typing span:nth-child(3){animation-delay:.3s}
@keyframes bl{0%,80%,100%{opacity:.3;transform:translateY(0)}40%{opacity:1;transform:translateY(-3px)}}
.cards{margin-top:12px;display:grid;gap:12px}
.lc{background:var(--panel);border:1px solid var(--line);border-left:4px solid #777;border-radius:14px;
 padding:15px 17px;transition:.15s;overflow:hidden}.lc:hover{box-shadow:0 6px 20px rgba(16,24,40,.08)}
.lc-photo{display:block;width:calc(100% + 34px);height:160px;object-fit:cover;margin:-15px -17px 12px;
 background:#f3efe9}
.lc-head{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:8px}
.badge{color:#fff;background:#777;border-radius:999px;font-size:12px;font-weight:600;padding:4px 11px;
 text-transform:capitalize;letter-spacing:.02em}
.pill{font-size:12px;font-weight:600;border-radius:999px;padding:4px 10px}
.pill.feat{background:#fff4e5;color:#b45309}.pill.open{background:#e7f6ec;color:#137333}
.pill.claimed{background:#e8f0fe;color:#1565c0}
.lc h4{margin:0;font-size:17.5px;line-height:1.25}.lc-loc{color:var(--muted);font-size:14px;margin-top:4px}
.lc-rate{color:#b45309;font-size:14px;font-weight:600;margin-top:4px}
.lc-fresh{color:#137333;font-size:13px;margin-top:6px}
.lc-desc{color:#475467;font-size:15px;margin:9px 0 0;line-height:1.5}
.lc-langs{color:#0f766e;font-size:13.5px;font-weight:600;margin:7px 0 0}
.lc-feats{display:flex;flex-wrap:wrap;gap:5px;margin:8px 0 0}
.feat-chip{background:#f3efe9;border:1px solid #e7e0d6;border-radius:999px;padding:2px 9px;font-size:11.5px;color:#5b6470}
.lc-act{display:flex;gap:9px;margin-top:13px;flex-wrap:wrap}
.lc-btn{border:1px solid var(--line);border-radius:10px;padding:8px 14px;font-size:14px;font-weight:500;
 color:var(--ink);transition:.15s}.lc-btn:hover{border-color:var(--brand);color:var(--brand)}
.addcta{display:inline-block;margin-top:12px;background:var(--brand);color:#fff;border-radius:11px;
 padding:10px 16px;font-size:14px;font-weight:600;transition:.15s}.addcta:hover{background:var(--brand-d);color:#fff}
.morebtn{display:block;margin-top:12px;background:#fff;border:1px solid var(--accent);color:var(--accent);
 border-radius:11px;padding:10px 16px;font-size:14px;font-weight:600;cursor:pointer;transition:.15s}
.morebtn:hover{background:var(--accent);color:#fff}
.contrib{margin-top:12px;display:flex;flex-wrap:wrap;gap:9px}
.contrib .cin{flex:1 1 190px;border:1px solid var(--line);border-radius:10px;padding:11px 13px;font:inherit;font-size:15px}
.contrib .cin:focus{outline:0;border-color:var(--accent)}
.contrib .csend{background:var(--accent);color:#fff;border:0;border-radius:10px;padding:11px 18px;
 font-size:15px;font-weight:600;cursor:pointer}.contrib .csend:hover{background:var(--accent-d)}
.composer{background:var(--panel);border-top:1px solid var(--line);padding:14px 18px;
 padding-bottom:max(14px,env(safe-area-inset-bottom))}
.composer-inner{max-width:820px;margin:0 auto;display:flex;align-items:flex-end;gap:9px;background:#fff;
 border:1.5px solid #e3ddd3;border-radius:18px;padding:7px 8px 7px 16px;box-shadow:0 1px 3px rgba(16,24,40,.05)}
.composer-inner:focus-within{border-color:var(--brand);box-shadow:0 0 0 4px var(--ring)}
#q{flex:1;min-width:0;border:0;outline:0;resize:none;font:inherit;font-size:16px;line-height:1.5;padding:9px 0;
 max-height:150px;background:transparent;color:var(--ink)}
.send{flex:0 0 auto;width:44px;height:44px;border:0;border-radius:13px;background:var(--brand);color:#fff;
 display:grid;place-items:center;cursor:pointer;transition:.15s}.send:hover{background:var(--brand-d)}
.hint{max-width:820px;margin:9px auto 0;text-align:center;color:#98a2b3;font-size:12.5px}
@media(max-width:680px){.welcome{margin-top:4vh}.welcome h1{font-size:25px}.welcome p{font-size:16px}
 #mic{display:none}.voicebtn{padding:0 14px}}
__PORTALCSS__
</style></head><body>
<header class="topbar">
 <a class="brand" href="/"><img class="brandlogo" src="/logo" alt="__PLAT__"><span><b>__PLAT__</b><i>__PTAG__</i></span></a>
 <nav class="topnav"><a href="/today">☀ Today</a><a href="/news">📰 News</a><a href="/questions">💬 Q&amp;A</a><a href="/browse">Browse</a><a href="/me">♥ Saved</a><a href="/for-business">For business</a></nav>
 <div class="actions">
  <select id="lang" class="langsel" onchange="setLang(this.value)" aria-label="Language">
   <option value="en">English</option><option value="hi">हिंदी</option><option value="te">తెలుగు</option>
  </select>
  <button class="iconbtn" id="spk" type="button" onclick="toggleSpeak()" title="Read answers aloud" aria-label="Toggle voice">🔊</button>
  <button class="newchat" onclick="newChat()" aria-label="Start a new chat">✎ New chat</button>
  <span class="status"><span class="dot"></span>__MODE__</span>
 </div>
</header>
__PARTNERBAR__
<main id="log"><div class="wrap" id="thread">
 <section id="welcome" class="welcome">
  <div class="herocard">
   <div class="hero-avatar">🪷</div>
   <h1>Namaste! I'm __ANAME__ — that means “friend”.</h1>
   <p class="heroSub">Your desi friend for finding Indian America — restaurants, groceries, temples,
    events, movies, doctors and more across the USA. Tell me what you want and roughly where.</p>
  </div>
  __FESTIVAL__
  <div class="chips">__CHIPS__</div>
  <button class="voicecta" onclick="startConvo()">🎙️ <span class="voicebtn-t">Talk to Dost</span></button>
  <p class="voicetip">Hands-free voice — speak in English, हिंदी or తెలుగు</p>
  <a class="browsecat" href="/browse">🗂️ <span class="browselink-t">Browse by category</span></a>
  <p class="browselink" style="margin-top:4px"><a href="/for-business">🏪 <span>List your business free</span></a> · <a href="/about">About __PLAT__</a></p>
  __PORTAL__
  <footer class="homefoot">
   <p class="disclaim">Free directory for the Indian-from-India community in the USA · information
    only — <a href="/terms">verify before relying</a>.</p>
   <nav class="footnav">
    <a href="/about">About us</a> · <a href="/news">News</a> · <a href="/for-business">List your business</a> ·
    <a href="/insights">Insights</a> · <a href="/privacy">Privacy</a> · <a href="/terms">Terms</a> ·
    <a href="/contact">Contact</a> · <a href="/faq">FAQ</a>
   </nav>
   <p class="copyr">© __PLAT__ · Built for people &amp; AI · Data from OpenStreetMap (ODbL) &amp; Wikidata (CC0)</p>
  </footer>
 </section>
</div></main>
<div id="convobar" class="convobar" style="display:none">
 <span id="convostatus">🎙️ Listening…</span>
 <button class="cstop" type="button" onclick="stopConvo()">■ Stop</button>
</div>
<form class="composer" onsubmit="return submitForm(event)">
 <div class="composer-inner">
  <textarea id="q" rows="1" autocomplete="off" placeholder="Ask anything… e.g. vegetarian thali in Jersey City"></textarea>
  <button class="voicebtn" id="convo" type="button" onclick="toggleConvo()" title="Hands-free voice chat — speak your question and hear the answer" aria-label="Start voice conversation">
   <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3z"/><path d="M19 10v1a7 7 0 0 1-14 0v-1"/><line x1="12" y1="19" x2="12" y2="22"/></svg>
   <span class="vlabel">Voice</span></button>
  __FLYERBTN__
  <button class="micbtn" id="mic" type="button" onclick="startMic()" title="Dictate your search" aria-label="Speak to type">🎤</button>
  <button class="send" type="submit" aria-label="Send">
   <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="20" x2="12" y2="5"/><polyline points="5 12 12 5 19 12"/></svg>
  </button>
 </div>
 <div class="hint">__ANAME__ searches a live directory · <b>info only — verify independently</b> · Enter to send</div>
</form>
<script>
const ICON=__ICONS__, COLOR=__COLORS__;
const TTS_PROVIDER="__TTS__";  // "browser" today; a paid native-voice provider can hook in via speak()
const log=document.getElementById('log'), thread=document.getElementById('thread'), ta=document.getElementById('q');
const WELCOME=thread.innerHTML;
let history=[], geo=null, lastQuery='', lastBot=null;
let filters={vertical:null, open_now:false};
// --- language + voice (free: browser Web Speech API; Dost replies via the multilingual LLM) ---
let lang=localStorage.getItem('dost_lang')||'en';
let speakOn=localStorage.getItem('dost_speak')==='1';
const LOCALE={en:'en-US',hi:'hi-IN',te:'te-IN'};
const I18N={
 en:{hero:"Namaste! I'm Dost — that means “friend”.",
  heroSub:"Tell me what you're looking for and roughly where, and I'll find the closest ones.",
  contribLine:"New here? Add a place you love so others can find it too:",
  cRest:"➕ A restaurant I love",cGro:"➕ My go-to grocery",cTemple:"➕ My temple",
  placeholder:"Ask anything… e.g. vegetarian thali in Jersey City",
  hint:"Dost searches a live directory · Enter to send",
  nearme:"Near me",opennow:"Open now",newchat:"New chat",mic:"Speak",spk:"Read answers aloud",
  voiceBtn:"Talk to Dost",voiceTip:"Hands-free voice — speak in English, हिंदी or తెలుగు",
  voiceLabel:"Voice",voiceStop:"Stop",
  browse:"Browse by category"},
 hi:{hero:"नमस्ते! मैं दोस्त हूँ — यानी आपका “मित्र”।",
  heroSub:"बताइए आप क्या ढूँढ़ रहे हैं और किस शहर में — मैं आपके सबसे नज़दीकी जगहें खोज दूँगा।",
  contribLine:"नए हैं? अपनी पसंदीदा जगह जोड़ें ताकि और लोग भी उसे पा सकें:",
  cRest:"➕ मेरा पसंदीदा रेस्टोरेंट",cGro:"➕ मेरी रोज़ की ग्रोसरी",cTemple:"➕ मेरा मंदिर",
  placeholder:"कुछ भी पूछें… जैसे जर्सी सिटी में वेज थाली",
  hint:"दोस्त एक लाइव डायरेक्टरी खोजता है · भेजने के लिए Enter",
  nearme:"मेरे पास",opennow:"अभी खुला",newchat:"नई चैट",mic:"बोलें",spk:"जवाब सुनाएँ",
  voiceBtn:"दोस्त से बात करें",voiceTip:"हैंड्स-फ़्री आवाज़ — अंग्रेज़ी, हिंदी या तेलुगु में बोलें",
  voiceLabel:"आवाज़",voiceStop:"रोकें",
  browse:"श्रेणी के अनुसार ब्राउज़ करें"},
 te:{hero:"నమస్తే! నేను దోస్త్ — అంటే మీ “స్నేహితుడు”.",
  heroSub:"మీరు ఏమి వెతుకుతున్నారో, ఏ నగరంలోనో చెప్పండి — దగ్గర్లోని వాటిని నేను చూపిస్తాను.",
  contribLine:"కొత్తగా వచ్చారా? మీకు నచ్చిన ప్రదేశాన్ని జోడించండి, ఇతరులూ కనుగొంటారు:",
  cRest:"➕ నాకు ఇష్టమైన రెస్టారెంట్",cGro:"➕ నా రోజువారీ గ్రోసరీ",cTemple:"➕ నా ఆలయం",
  placeholder:"ఏదైనా అడగండి… ఉదా: జెర్సీ సిటీలో వెజ్ తాలి",
  hint:"దోస్త్ లైవ్ డైరెక్టరీని వెతుకుతుంది · పంపడానికి Enter",
  nearme:"నా దగ్గర",opennow:"ఇప్పుడు తెరిచి ఉంది",newchat:"కొత్త చాట్",mic:"మాట్లాడండి",spk:"సమాధానాలు చదవండి",
  voiceBtn:"దోస్త్‌తో మాట్లాడండి",voiceTip:"హ్యాండ్స్-ఫ్రీ వాయిస్ — ఇంగ్లీష్, హిందీ లేదా తెలుగులో మాట్లాడండి",
  voiceLabel:"వాయిస్",voiceStop:"ఆపు",
  browse:"వర్గం వారీగా బ్రౌజ్ చేయండి"}
};
function T(){return I18N[lang]||I18N.en;}
function setLang(v){lang=I18N[v]?v:'en';localStorage.setItem('dost_lang',lang);document.cookie='lang='+lang+';path=/;max-age=31536000;samesite=lax';applyLang();}
function applyLang(){const t=T();
 const set=(sel,val)=>{const e=document.querySelector(sel);if(e)e.textContent=val;};
 set('#welcome h1',t.hero);set('#welcome .heroSub',t.heroSub);set('#welcome .welcome-contrib',t.contribLine);
 const cc=document.querySelectorAll('#welcome .contribchip');if(cc[0])cc[0].textContent=t.cRest;if(cc[1])cc[1].textContent=t.cGro;if(cc[2])cc[2].textContent=t.cTemple;
 const vb=document.querySelector('#welcome .voicebtn-t');if(vb)vb.textContent=t.voiceBtn;
 const vt=document.querySelector('#welcome .voicetip');if(vt)vt.textContent=t.voiceTip;
 const bl=document.querySelector('#welcome .browselink-t');if(bl)bl.textContent=t.browse;
 if(ta)ta.placeholder=t.placeholder;
 const hint=document.querySelector('.hint');if(hint)hint.textContent=t.hint;
 const loc=document.querySelector('.fchip.loc');if(loc)loc.textContent='📍 '+t.nearme;
 const opn=document.querySelector('.fchip.open');if(opn)opn.textContent='● '+t.opennow;
 const nc=document.querySelector('.newchat');if(nc)nc.textContent='✎ '+t.newchat;
 const mic=document.getElementById('mic');if(mic)mic.title=t.mic;
 const spk=document.getElementById('spk');if(spk){spk.title=t.spk;spk.classList.toggle('on',speakOn);}
 const vl=document.querySelector('#convo .vlabel');if(vl)vl.textContent=convoMode?t.voiceStop:t.voiceLabel;
 const sel=document.getElementById('lang');if(sel)sel.value=lang;
}
function isIOS(){return /iPad|iPhone|iPod/.test(navigator.userAgent||"")||((navigator.platform==='MacIntel')&&navigator.maxTouchPoints>1);}
async function micPermState(){
 // 'granted' | 'denied' | 'prompt' | 'unknown' — lets us guide instead of failing blindly.
 try{if(navigator.permissions&&navigator.permissions.query){return (await navigator.permissions.query({name:'microphone'})).state;}}catch(e){}
 return 'unknown';
}
// The universal easy path: every phone keyboard has a 🎤 (dictation) that needs no site permission.
function keyboardMicTip(){return isIOS()
 ? '🎤 Easiest on iPhone: tap the message box, then tap the 🎤 on your keyboard and just speak — that always works. (In-app voice is limited on iPhone/Safari.)'
 : '🎤 Easiest way: tap the message box, then tap the 🎤 on your phone keyboard (or press Windows + H on a PC) and just speak — no permission needed.';}
async function ensureMic(){
 // Trigger the browser's native "Allow microphone?" popup (cleaner/more reliable than letting
 // SpeechRecognition request it). Returns false if blocked/denied.
 try{if(navigator.mediaDevices&&navigator.mediaDevices.getUserMedia){
   var s=await navigator.mediaDevices.getUserMedia({audio:true});s.getTracks().forEach(function(t){t.stop();});}
   return true;}catch(e){return false;}
}
async function startMic(){
 const SR=window.SpeechRecognition||window.webkitSpeechRecognition;
 if(!window.isSecureContext){fillBot(addBot(),'🎤 Voice needs a secure (https) connection — you can still type.',[]);return;}
 if(!SR||isIOS()){fillBot(addBot(),keyboardMicTip(),[]);return;}   // unsupported / iPhone -> keyboard mic
 // Request the mic FIRST, directly in the click — this is what pops the browser's permission
 // prompt (the 🔒 / mic icon). Don't await anything before it or the gesture can be lost (Safari).
 if(!(await ensureMic())){fillBot(addBot(),micError('not-allowed'),[]);return;}
 let r;try{r=new SR();}catch(e){return;}
 r.lang=LOCALE[lang]||'en-US';r.interimResults=true;r.maxAlternatives=1;
 const mic=document.getElementById('mic');if(mic)mic.classList.add('rec');
 r.onresult=function(e){var fin='',intr='';for(var i=e.resultIndex;i<e.results.length;i++){var t=e.results[i][0].transcript;if(e.results[i].isFinal)fin+=t;else intr+=t;}
   ta.value=fin||intr;                                  // live words appear as you speak
   if(fin&&fin.trim()){submitForm(new Event('submit'));}};
 r.onerror=function(ev){if(mic)mic.classList.remove('rec');var m=micError(ev.error);if(m)fillBot(addBot(),m,[]);};
 r.onend=function(){if(mic)mic.classList.remove('rec');};
 try{r.start();}catch(e){if(mic)mic.classList.remove('rec');}
}
function micError(code){var m={
 'not-allowed':'🎤 The mic isn’t allowed for this site yet. Tap the 🔒 (or “aA”) next to the web address → Microphone → Allow, then reload. ',
 'service-not-allowed':'🎤 Microphone access is turned off in your browser settings — switch it on and retry. ',
 'no-speech':'🎤 I didn’t catch that — tap Voice and speak again. ',
 'audio-capture':'🎤 No microphone found — check your device’s mic. ',
 'language-not-supported':'🎤 Voice isn’t available for this language on your device — switch to English and try again. ',
 'network':'🎤 Voice recognition needs an internet connection — please check your network. '}[code];
 return m?(m+keyboardMicTip()):null;}
function pickVoice(loc){
  // Pick the best available on-device voice for this locale. Hindi/Telugu device voices vary a lot
  // in quality, so we score: exact locale > higher-quality engines (neural/natural/Google) > on-device.
  var vs=(window.speechSynthesis?speechSynthesis.getVoices():[])||[];if(!vs.length)return null;
  var base=loc.slice(0,2).toLowerCase();
  var cand=vs.filter(function(v){return v.lang&&v.lang.replace('_','-').slice(0,2).toLowerCase()===base;});
  if(!cand.length)return null;
  function score(v){var s=0,L=(v.lang||'').replace('_','-').toLowerCase(),n=(v.name||'').toLowerCase();
    if(L===loc.toLowerCase())s+=40;                       // exact locale (te-IN) beats generic (te)
    if(/natural|neural|premium|enhanced|wavenet/.test(n))s+=12; // higher-quality TTS engines
    if(/google/.test(n))s+=8;                              // Google voices sound better for hi/te
    if(/microsoft/.test(n))s+=5;
    if(v.localService)s+=3;                                // on-device: reliable, no network gaps
    if(v.default)s+=1;return s;}
  cand.sort(function(a,b){return score(b)-score(a);});
  return cand[0];
}
function speak(text){
  if(!speakOn||!text){if(convoMode)convoListen();return;}
  // PROVISION: when TTS_PROVIDER!=='browser', a paid native voice (better Hindi/Telugu) would be
  // fetched server-side here and played; until then we use the free on-device Web Speech voices.
  if(!('speechSynthesis' in window)){if(convoMode)convoListen();return;}
  try{speechSynthesis.cancel();const u=new SpeechSynthesisUtterance(text);u.lang=LOCALE[lang]||'en-US';
    const v=pickVoice(u.lang);if(v)u.voice=v;
    u.rate=(lang==='en')?1:0.93;u.pitch=1;   // a touch slower for clearer Hindi/Telugu narration
    u.onstart=function(){if(convoMode){convoStatus('speaking');barged=false;bargeListen();}};
    u.onend=function(){stopBarge();if(convoMode&&!barged)convoListen();};   // barge handles its own re-listen
    speechSynthesis.speak(u);
  }catch(e){if(convoMode)convoListen();}
}
function toggleSpeak(){speakOn=!speakOn;localStorage.setItem('dost_speak',speakOn?'1':'0');const spk=document.getElementById('spk');if(spk)spk.classList.toggle('on',speakOn);if(!speakOn&&'speechSynthesis' in window){try{speechSynthesis.cancel();}catch(e){}}}

// ---- hands-free voice conversation: talk -> hear answer -> auto-listen for the next question ----
let convoMode=false, convoRecog=null, bargeRecog=null, barged=false;
// Barge-in: while Dost speaks, listen so the user can talk OVER him to cut him off. Final-result-only
// + length>1 to avoid TTS echo (echoCancellation is on by default via getUserMedia) falsely triggering.
function bargeListen(){
  var SR=window.SpeechRecognition||window.webkitSpeechRecognition;if(!SR)return;
  try{bargeRecog=new SR();}catch(e){return;}
  bargeRecog.lang=LOCALE[lang]||'en-US';bargeRecog.interimResults=false;bargeRecog.maxAlternatives=1;
  bargeRecog.onresult=function(e){var fin='';for(var i=e.resultIndex;i<e.results.length;i++){if(e.results[i].isFinal)fin+=e.results[i][0].transcript;}
    if(fin&&fin.trim().length>1){barged=true;stopBarge();try{speechSynthesis.cancel();}catch(_){}convoStatus('thinking');send(fin.trim(),false);}};
  bargeRecog.onerror=function(){};
  try{bargeRecog.start();}catch(e){}
}
function stopBarge(){if(bargeRecog){try{bargeRecog.abort();}catch(e){}bargeRecog=null;}}
function convoStatus(s){var bar=document.getElementById('convobar'),txt=document.getElementById('convostatus');
  if(bar)bar.style.display=convoMode?'flex':'none';
  if(txt)txt.textContent=s==='listening'?'🎙️ Listening…':(s==='thinking'?'💭 Thinking…':'🔊 Speaking…');}
function toggleConvo(){convoMode?stopConvo():startConvo();}
async function startConvo(){
  var SR=window.SpeechRecognition||window.webkitSpeechRecognition;
  if(!window.isSecureContext){fillBot(addBot(),'🎙️ Voice needs a secure (https) connection.',[]);return;}
  if(!SR||isIOS()){fillBot(addBot(),keyboardMicTip(),[]);return;}   // unsupported / iPhone -> keyboard mic
  // Request the mic FIRST, in the click gesture, so the browser's permission prompt actually pops.
  if(!(await ensureMic())){fillBot(addBot(),micError('not-allowed'),[]);return;}
  convoMode=true;speakOn=true;localStorage.setItem('dost_speak','1');
  var cb=document.getElementById('convo');if(cb){cb.classList.add('on');var vl=cb.querySelector('.vlabel');if(vl)vl.textContent=T().voiceStop;}
  var spk=document.getElementById('spk');if(spk)spk.classList.add('on');
  hideWelcome();convoListen();
}
function stopConvo(){convoMode=false;stopBarge();try{if(convoRecog)convoRecog.abort();}catch(e){}
  if('speechSynthesis' in window){try{speechSynthesis.cancel();}catch(e){}}
  var cb=document.getElementById('convo');if(cb){cb.classList.remove('on');var vl=cb.querySelector('.vlabel');if(vl)vl.textContent=T().voiceLabel;}
  var bar=document.getElementById('convobar');if(bar)bar.style.display='none';}
function convoListen(){
  if(!convoMode)return;
  var SR=window.SpeechRecognition||window.webkitSpeechRecognition;
  try{convoRecog=new SR();}catch(e){return;}
  convoRecog.lang=LOCALE[lang]||'en-US';convoRecog.interimResults=true;convoRecog.maxAlternatives=1;
  var got=false;convoStatus('listening');
  convoRecog.onresult=function(e){var fin='',intr='';for(var i=e.resultIndex;i<e.results.length;i++){var t=e.results[i][0].transcript;if(e.results[i].isFinal)fin+=t;else intr+=t;}
    if(intr&&!fin){var st=document.getElementById('convostatus');if(st)st.textContent='🎙️ '+intr;}   // live
    if(fin&&fin.trim()){got=true;convoStatus('thinking');send(fin.trim(),false);}};
  convoRecog.onerror=function(ev){
    if(ev.error==='not-allowed'||ev.error==='service-not-allowed'||ev.error==='language-not-supported'||ev.error==='audio-capture'){
      stopConvo();var m=micError(ev.error);if(m)fillBot(addBot(),m,[]);return;}
    if(convoMode&&ev.error!=='aborted'&&ev.error!=='no-speech')setTimeout(convoListen,700);};
  convoRecog.onend=function(){if(convoMode&&!got&&!(window.speechSynthesis&&speechSynthesis.speaking))setTimeout(convoListen,500);};
  try{convoRecog.start();}catch(e){}
}
function newChat(){
  history=[];lastQuery='';lastBot=null;filters={vertical:null,open_now:false};
  document.querySelectorAll('.fchip').forEach(c=>c.classList.remove('on'));
  const all=document.querySelector('.fchip[data-v=""]');if(all)all.classList.add('on');
  thread.innerHTML=WELCOME;ta.value='';ta.style.height='auto';applyLang();ta.focus();log.scrollTop=0;
}
navigator.geolocation && navigator.geolocation.getCurrentPosition(
  p=>{geo={lat:p.coords.latitude,lng:p.coords.longitude};}, ()=>{}, {timeout:4000});
function el(tag,cls,text){const e=document.createElement(tag);if(cls)e.className=cls;if(text!=null)e.textContent=text;return e;}
function scroll(){log.scrollTop=log.scrollHeight;}
function hideWelcome(){const w=document.getElementById('welcome');if(w)w.style.display='none';}
function typing(){const t=el('div','typing');for(let i=0;i<3;i++)t.appendChild(el('span'));return t;}
function setVertical(b){document.querySelectorAll('.fchip:not(.open)').forEach(c=>c.classList.remove('on'));b.classList.add('on');filters.vertical=b.dataset.v||null;if(lastQuery)rerun();}
function syncChip(v){document.querySelectorAll('.fchip:not(.open):not(.loc)').forEach(c=>c.classList.toggle('on',(c.dataset.v||'')===(v||'')));filters.vertical=v||null;}
function toggleOpen(b){filters.open_now=!filters.open_now;b.classList.toggle('on',filters.open_now);if(lastQuery)rerun();}
function rerun(){if(lastQuery&&lastBot)send(lastQuery,true);}
function useLocation(){
  if(!navigator.geolocation){fillBot(addBot(),'Location isn’t available — type a city like “Edison, NJ”.',[]);return;}
  navigator.geolocation.getCurrentPosition(
    function(p){geo={lat:p.coords.latitude,lng:p.coords.longitude};
      if(lastQuery){rerun();} else {fillBot(addBot(),'📍 Got your location — what are you looking for nearby?',[]);}},
    function(){fillBot(addBot(),'Couldn’t get your location — just type a city like “Edison, NJ”.',[]);},
    {timeout:8000});
}
function lnk(href,label,blank){const a=el('a','lc-btn',label);a.href=href;if(blank){a.target='_blank';a.rel='noopener';}return a;}
function card(c){
  const v=c.vertical||'',color=COLOR[v]||'#777',icon=ICON[v]||'•';
  const d=el('div','lc');d.style.borderLeftColor=color;
  if(c.photo_url){const im=el('img','lc-photo');im.src=c.photo_url;im.alt=c.name||'';im.loading='lazy';im.onerror=function(){im.remove();};d.appendChild(im);}
  const head=el('div','lc-head');
  const badge=el('span','badge',icon+' '+v);badge.style.background=color;head.appendChild(badge);
  if(c.is_featured)head.appendChild(el('span','pill feat','★ Featured'));
  if(c.is_claimed)head.appendChild(el('span','pill claimed','✓ Owner-verified'));
  if(c.open_now)head.appendChild(el('span','pill open','● Open now'));
  d.appendChild(head);d.appendChild(el('h4',null,c.name||''));
  if(c.community_rating){const rc=el('div','lc-rate','★ '+c.community_rating.toFixed(1)+' ('+(c.community_rating_count||0)+' community review'+((c.community_rating_count==1)?'':'s')+')');d.appendChild(rc);}
  if(c.rating){const rt=el('div','lc-rate',(c.community_rating?'web ':'')+'★ '+c.rating+(c.rating_count?(' ('+c.rating_count+')'):'')+'/5');if(c.community_rating)rt.style.opacity='.65';d.appendChild(rt);}
  const loc=[c.city,c.state].filter(Boolean).join(', ');
  let locline=loc;
  if(c.distance_miles!=null) locline+=(loc?' · ':'')+c.distance_miles+' mi';
  if(locline)d.appendChild(el('div','lc-loc','📍 '+locline));
  if(c.description)d.appendChild(el('p','lc-desc',c.description));
  if(c.languages&&c.languages.length)d.appendChild(el('div','lc-langs','🗣 Speaks '+c.languages.join(', ')));
  if(c.features&&c.features.length){const f=el('div','lc-feats');c.features.forEach(function(x){f.appendChild(el('span','feat-chip',x));});d.appendChild(f);}
  if(c.verified_ago)d.appendChild(el('div','lc-fresh','✓ '+c.verified_ago));
  const act=el('div','lc-act');
  if(c.id&&c.vertical)act.appendChild(lnk('/listing/'+c.vertical+'/'+c.id,'Details & reviews'));
  if(c.phone)act.appendChild(lnk('tel:'+c.phone,'Call'));
  if(c.website)act.appendChild(lnk(c.website,'Visit website',true));
  if(loc)act.appendChild(lnk('https://maps.google.com/?q='+encodeURIComponent((c.name||'')+' '+loc),'Map',true));
  if(act.children.length)d.appendChild(act);
  return d;
}
function addUser(text){const m=el('div','msg user');m.appendChild(el('div','bubble',text));thread.appendChild(m);scroll();}
function addBot(){const m=el('div','msg bot');m.appendChild(el('div','avatar','🪷'));
  const content=el('div','content');const b=el('div','bubble');b.appendChild(typing());content.appendChild(b);
  m.appendChild(content);thread.appendChild(m);scroll();return content;}
function fillBot(content,reply,cards,suggest,contribute){content.innerHTML='';content.appendChild(el('div','bubble',reply||'…'));
  if(cards&&cards.length){const w=el('div','cards');const N=6;
    cards.slice(0,N).forEach(c=>w.appendChild(card(c)));content.appendChild(w);
    if(cards.length>N){const b=el('button','morebtn','Show '+(cards.length-N)+' more');
      b.onclick=function(){cards.slice(N).forEach(c=>w.appendChild(card(c)));b.remove();scroll();};content.appendChild(b);}
    const vs=[...new Set(cards.map(c=>c.vertical).filter(Boolean))];syncChip(vs.length===1?vs[0]:'');}
  if(contribute){const a=el('button','addcta','➕ Add a place you know');
    a.onclick=function(){openContribute(contribute.vertical||'',contribute.city||'');};content.appendChild(a);}
  else if(suggest&&suggest.url){const a=el('a','addcta',suggest.label||'➕ Add to directory');a.href=suggest.url;a.target='_blank';a.rel='noopener';content.appendChild(a);}
  scroll();}
function openContribute(vertical,city){
  hideWelcome();const content=addBot();content.innerHTML='';
  content.appendChild(el('div','bubble','Wonderful — share a place you love and I’ll send it to our team to verify and add. 🙏'));
  const f=el('div','contrib');
  const nm=el('input','cin');nm.placeholder='Place name (e.g. Saravana Bhavan)';
  const ct=el('input','cin');ct.placeholder='City, ST (e.g. Edison, NJ)';if(city)ct.value=city;
  const ws=el('input','cin');ws.placeholder='Website (optional — we fill in the rest)';
  const send=el('button','csend','Add it');
  send.onclick=function(){submitContribute(content,nm.value,ct.value,vertical,ws.value);};
  f.appendChild(nm);f.appendChild(ct);f.appendChild(ws);f.appendChild(send);content.appendChild(f);scroll();nm.focus();
}
function submitContribute(content,name,city,vertical,website){
  name=(name||'').trim();if(!name){return;}
  content.innerHTML='';content.appendChild(el('div','bubble','Sending… 🙏'));
  fetch('/chat/contribute',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({name:name,city:city,vertical:vertical,website:website})})
    .then(r=>r.json()).then(d=>{content.innerHTML='';
      content.appendChild(el('div','bubble',d.message||'Thanks! We’ll review and add it.'));scroll();})
    .catch(function(){content.innerHTML='';
      content.appendChild(el('div','bubble','Sorry, that didn’t go through — please try again.'));scroll();});
}
// The proven blocking path (unchanged behavior) — also the fallback for anything streaming can't handle.
function sendBlocking(content,isRerun){
  return fetch('/chat/api',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({messages:history,geo:geo,filters:filters,lang:lang})})
    .then(function(r){return r.json();})
    .then(function(data){fillBot(content,data.reply,data.cards,data.suggest_add,data.contribute);
      speak(data.reply);if(!isRerun)history.push({role:'assistant',content:data.reply||''});})
    .catch(function(){fillBot(content,'Sorry, something went wrong. Please try again.',[]);});
}
async function send(text,isRerun){
  hideWelcome();let content;
  if(!isRerun){addUser(text);history.push({role:'user',content:text});lastQuery=text;content=addBot();lastBot=content;}
  else{content=lastBot;content.innerHTML='';const b=el('div','bubble');b.appendChild(typing());content.appendChild(b);scroll();}
  // Try streaming first (English + grounded model); ANY hiccup degrades to the blocking path.
  try{
    const r=await fetch('/chat/stream',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({messages:history,geo:geo,filters:filters,lang:lang})});
    if(!r.ok||(r.headers.get('content-type')||'').indexOf('text/event-stream')<0||!r.body){
      return sendBlocking(content,isRerun);
    }
    const reader=r.body.getReader(),dec=new TextDecoder();
    let buf='',acc='',cards=null,started=false,fell=false,bubble=null;
    while(true){
      const rd=await reader.read(); if(rd.done)break;
      buf+=dec.decode(rd.value,{stream:true});
      let i;
      while((i=buf.indexOf('\\n\\n'))>=0){
        const raw=buf.slice(0,i);buf=buf.slice(i+2);
        const d=raw.indexOf('data:'); if(d<0)continue;
        let obj;try{obj=JSON.parse(raw.slice(d+5).trim());}catch(e){continue;}
        if(obj.fallback){fell=true;break;}
        if(obj.delta!=null){
          if(!started){content.innerHTML='';bubble=el('div','bubble');content.appendChild(bubble);started=true;}
          acc+=obj.delta;bubble.textContent=acc;scroll();
        }
        if(obj.final){cards=(obj.final&&obj.final.cards)||null;}
      }
      if(fell)break;
    }
    if(fell||!started){return sendBlocking(content,isRerun);}
    fillBot(content,acc,cards);speak(acc);
    if(!isRerun)history.push({role:'assistant',content:acc});
  }catch(e){return sendBlocking(content,isRerun);}
}
function submitForm(e){if(e&&e.preventDefault)e.preventDefault();const t=ta.value.trim();if(!t)return false;
  ta.value='';ta.style.height='auto';send(t,false);return false;}
function ask(text){send(text,false);}
ta.addEventListener('input',()=>{ta.style.height='auto';ta.style.height=Math.min(ta.scrollHeight,140)+'px';});
ta.addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();submitForm(e);}});
// --- flyer upload: extract, then hand off to the review form (no in-chat conversation) ---
const flyerFile=document.getElementById('flyerfile');
if(flyerFile){flyerFile.addEventListener('change',function(){
  const file=flyerFile.files&&flyerFile.files[0];flyerFile.value='';if(!file)return;
  hideWelcome();addUser('📎 '+file.name);const content=addBot();
  content.innerHTML='';content.appendChild(el('div','bubble','Reading your flyer… 🔍'));scroll();
  const fd=new FormData();fd.append('image',file);
  fetch('/chat/flyer',{method:'POST',body:fd}).then(r=>r.json().then(d=>({status:r.status,d:d})))
    .then(function(res){content.innerHTML='';
      content.appendChild(el('div','bubble',res.d.reply||'Something went wrong.'));
      if(res.d.needs_login){const a=el('a','addcta','Sign in →');a.href='/portal/login';content.appendChild(a);}
      else if(res.d.link){const a=el('a','addcta','Review & confirm →');a.href=res.d.link;content.appendChild(a);}
      scroll();})
    .catch(function(){content.innerHTML='';
      content.appendChild(el('div','bubble','Sorry, that upload didn’t go through — please try again.'));scroll();});
});}
setLang(lang);  // apply saved language to the UI + selector
if('speechSynthesis' in window){speechSynthesis.onvoiceschanged=function(){};speechSynthesis.getVoices();}
ta.focus();
// Deep-link / SEO SearchAction: /chat?q=... prefills and runs the search automatically.
(function(){var q=new URLSearchParams(location.search).get('q');if(q&&q.trim()){send(q.trim(),false);}})();
</script></body></html>"""


_PORTAL_CACHE: dict[str, float | str] = {"html": "", "at": 0.0}
_PORTAL_TTL = 180  # seconds — the homepage is the busiest page; the portal changes slowly


def _portal_html() -> str:
    """The daily-portal feed below the hero, cached briefly so the busiest page doesn't re-run ~12
    queries per hit. Never breaks the homepage — any error yields nothing."""
    now = time.time()
    if _PORTAL_CACHE["html"] and now - float(_PORTAL_CACHE["at"]) < _PORTAL_TTL:
        return str(_PORTAL_CACHE["html"])
    try:
        html_out = homeportal.render()
    except Exception:
        html_out = ""
    _PORTAL_CACHE["html"], _PORTAL_CACHE["at"] = html_out, now
    return html_out


def chat_page(request: Request) -> HTMLResponse:
    if not assistant.enabled():
        return HTMLResponse("<h2>Chat is disabled.</h2>", status_code=503)
    from .pages import _KEYWORDS
    plat = html.escape(settings.platform_name)
    aname = html.escape(settings.assistant_name)
    mode = "live assistant" if assistant.llm_active() else "smart search"
    chips = "".join(f"<button class='chip' onclick=\"ask(this.textContent)\">{html.escape(s)}</button>"
                    for s in _SUGGESTIONS)
    base = settings.public_web_url.rstrip("/")
    # "Today" strip in the hero: festival countdown + one upcoming event + one community question.
    # A daily-habit hook right on the homepage; each pill links deeper. Degrades to empty gracefully.
    def _pill(href: str, inner: str) -> str:
        return (f"<a href='{href}' style='display:inline-block;background:#fff3dc;"
                "border:1px solid #ffd9a0;border-radius:999px;padding:7px 15px;margin:2px 4px 6px 0;"
                f"color:#b4530f;font-weight:600;font-size:14px;text-decoration:none'>{inner}</a>")
    _pills = []
    try:
        from .. import festivals
        _nf = festivals.next_festival()
        if _nf:
            _d = _nf["days_until"]
            _when = "today! 🎉" if _d == 0 else ("tomorrow" if _d == 1 else f"in {_d} days")
            _pills.append(_pill(
                "/today", f"{html.escape(_nf['emoji'])} <b>{html.escape(_nf['name'])}</b> is {_when}"))
    except Exception:
        pass
    try:
        from ..events import queries as eq
        _ev = eq.get_indian_events(limit=1).get("results", [])
        if _ev:
            _pills.append(_pill("/events", f"📅 {html.escape((_ev[0].get('name') or '')[:44])}"))
    except Exception:
        pass
    try:
        from .. import qa
        if qa.enabled():
            _tq = qa.trending(limit=1)
            if _tq:
                _pills.append(_pill(f"/q/{html.escape(_tq[0]['slug'])}",
                                    f"💬 {html.escape((_tq[0]['title'] or '')[:44])}"))
    except Exception:
        pass
    festival_html = (f"<div style='margin:2px 0 8px'>{''.join(_pills)}</div>" if _pills else "")
    flyerbtn_html = (
        '<button class="micbtn" id="flyerbtn" type="button" onclick="document.getElementById(\'flyerfile\').click()" '
        'title="Upload an event or business flyer" aria-label="Upload a flyer">📎</button>'
        '<input type="file" id="flyerfile" accept="image/jpeg,image/png,image/webp" style="display:none">'
        if settings.flyer_uploads_enabled else "")
    og_url = base + "/"          # the chatbot is the homepage now
    og_img = f"{base}/og.png"    # raster card (SVG OG images don't render on FB/LinkedIn/WhatsApp/X)
    aname_raw = settings.assistant_name
    og_desc = (f"{settings.platform_name} — your guide to Indian America. Find Indian restaurants, "
               f"sweets, temples, doctors, events, classes, salons and jewelry near you across the "
               f"USA, or ask {aname_raw}, our friendly assistant, by text or voice.")
    # JSON-LD so Google indexes the app under its real brand, with a search box pointing at /chat.
    jsonld = json.dumps([
        {"@context": "https://schema.org", "@type": "WebApplication", "name": settings.platform_name,
         "alternateName": f"{settings.platform_name} — Indian America directory", "url": og_url,
         "applicationCategory": "TravelApplication", "operatingSystem": "Web",
         "description": og_desc,
         "offers": {"@type": "Offer", "price": "0", "priceCurrency": "USD"}},
        {"@context": "https://schema.org", "@type": "WebSite", "name": settings.platform_name, "url": og_url,
         "potentialAction": {"@type": "SearchAction",
                             "target": f"{og_url}?q={{search_term_string}}",
                             "query-input": "required name=search_term_string"}},
    ], ensure_ascii=False).replace("<", "\\u003c")  # can't break out of the <script> block
    repl = {
        "__PLAT__": plat, "__ANAME__": aname, "__MODE__": html.escape(mode),
        "__ATAG__": html.escape(settings.assistant_tagline),
        "__PTAG__": html.escape(settings.platform_tagline),
        "__AMEAN__": html.escape(settings.assistant_meaning),
        "__CHIPS__": chips, "__FESTIVAL__": festival_html, "__FLYERBTN__": flyerbtn_html,
        "__PARTNERBAR__": partner_bar(), "__OGURL__": html.escape(og_url),
        "__OGIMG__": html.escape(og_img), "__OGDESC__": html.escape(og_desc),
        "__JSONLD__": jsonld,
        "__ICONS__": json.dumps(_CAT_ICON, ensure_ascii=False),
        "__COLORS__": json.dumps(_CAT_COLOR),
        "__TTS__": html.escape(settings.tts_provider),
        "__KEYWORDS__": html.escape(_KEYWORDS),
        "__GA__": analytics_tag(),
        "__PORTAL__": _portal_html(),
        "__PORTALCSS__": homeportal.CSS,
    }
    doc = _CHAT_HTML
    for k, v in repl.items():
        doc = doc.replace(k, v)
    return HTMLResponse(doc)


async def chat_api(request: Request) -> JSONResponse:
    if not assistant.enabled():
        return JSONResponse({"reply": "Chat is disabled.", "cards": []}, status_code=503)
    ip = (request.client.host if request.client else "?") or "?"
    if not _rate_ok(ip):
        return JSONResponse(
            {"reply": "You're sending messages a bit fast — please wait a moment.", "cards": []},
            status_code=429)
    try:
        body = await request.json()
    except Exception:
        body = {}
    messages = body.get("messages") or []
    geo = body.get("geo") if isinstance(body.get("geo"), dict) else None
    if geo is None:  # browser didn't share GPS -> approximate from IP so we can still go nearest-first
        from . import geoip
        pt = geoip.approx_point(geoip.client_ip(request))
        if pt:
            geo = {"lat": pt[0], "lng": pt[1], "approx": True}
    raw = body.get("filters") if isinstance(body.get("filters"), dict) else {}
    lang = body.get("lang") if body.get("lang") in ("en", "hi", "te") else "en"
    filters = {
        "vertical": raw.get("vertical") if isinstance(raw.get("vertical"), str) else None,
        "open_now": bool(raw.get("open_now")),
        "lang": lang,
    }
    if not isinstance(messages, list):
        messages = []
    # clamp lengths defensively
    for m in messages:
        if isinstance(m, dict) and isinstance(m.get("content"), str):
            m["content"] = m["content"][:1000]
    result = assistant.reply(messages, geo=geo, filters=filters)
    # Log EVERY chat turn (search, knowledge, clarify, discovery...) so the admin Traffic page
    # reflects real usage — not just listing searches. Best-effort; never breaks the response.
    try:
        from .. import analytics
        q = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "")
        analytics.log_call("chat", {"query": q[:200], "provider": result.get("provider"),
                                    "vertical": filters.get("vertical"),
                                    "city": filters.get("city"), "state": filters.get("state")},
                           len(result.get("cards") or []), "web-chat")
    except Exception:
        pass
    return JSONResponse(result)


async def chat_stream(request: Request) -> "JSONResponse | StreamingResponse":
    """Server-Sent-Events streaming of a chat reply, ONLY for the clean case (English + grounded model +
    a directory hit). Any other case returns {"fallback": true} so the browser calls the proven blocking
    /chat/api instead — that endpoint is untouched. The blocking LLM read runs in a worker thread that
    feeds an asyncio.Queue, so the event loop is never blocked."""
    import asyncio

    from starlette.concurrency import run_in_threadpool

    if not assistant.enabled():
        return JSONResponse({"fallback": True})
    ip = (request.client.host if request.client else "?") or "?"
    if not _rate_ok(ip):
        return JSONResponse({"fallback": True})
    try:
        body = await request.json()
    except Exception:
        body = {}
    messages = body.get("messages") or []
    geo = body.get("geo") if isinstance(body.get("geo"), dict) else None
    raw = body.get("filters") if isinstance(body.get("filters"), dict) else {}
    lang = body.get("lang") if body.get("lang") in ("en", "hi", "te") else "en"
    filters = {"vertical": raw.get("vertical") if isinstance(raw.get("vertical"), str) else None,
               "open_now": bool(raw.get("open_now")), "lang": lang}
    if not isinstance(messages, list):
        messages = []
    for m in messages:
        if isinstance(m, dict) and isinstance(m.get("content"), str):
            m["content"] = m["content"][:1000]
    if not assistant.can_stream(filters):
        return JSONResponse({"fallback": True})

    q: "asyncio.Queue" = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def worker():
        try:
            for item in assistant.stream_reply(messages, geo, filters):
                loop.call_soon_threadsafe(q.put_nowait, item)
        except Exception:
            loop.call_soon_threadsafe(q.put_nowait, ("fallback", None))
        finally:
            loop.call_soon_threadsafe(q.put_nowait, None)

    async def sse():
        task = asyncio.create_task(run_in_threadpool(worker))
        cards = None
        try:
            while True:
                item = await q.get()
                if item is None:
                    break
                kind, val = item
                if kind == "fallback":
                    yield "data: " + json.dumps({"fallback": True}) + "\n\n"
                    break
                if kind == "delta":
                    yield "data: " + json.dumps({"delta": val}) + "\n\n"
                elif kind == "final":
                    cards = (val or {}).get("cards")
                    yield "data: " + json.dumps({"final": val}) + "\n\n"
        finally:
            await task
        try:                                              # best-effort turn log (mirrors /chat/api)
            from .. import analytics
            uq = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "")
            analytics.log_call("chat", {"query": uq[:200], "provider": "llm-stream"},
                               len(cards or []), "web-chat")
        except Exception:
            pass

    return StreamingResponse(sse(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


async def chat_contribute(request: Request) -> JSONResponse:
    """In-chat contribution: a visitor names a place they know -> a pending submission for the
    portal (admin moderates). This is how the discovery conversation + 'add your favorite' turn
    into real data the agents can verify and grow."""
    if not assistant.enabled():
        return JSONResponse({"ok": False, "message": "Unavailable right now."}, status_code=503)
    ip = (request.client.host if request.client else "?") or "?"
    if not _rate_ok(ip):
        return JSONResponse({"ok": False, "message": "A bit too fast — try again in a moment."},
                            status_code=429)
    try:
        body = await request.json()
    except Exception:
        body = {}
    name = (body.get("name") or "").strip()[:120]
    if not name:
        return JSONResponse({"ok": False, "message": "Please add the place's name."}, status_code=400)
    raw_city = (body.get("city") or "").strip()[:120]
    city, state = raw_city or None, None
    if "," in raw_city:                                   # "Edison, NJ" -> city + state
        c, s = raw_city.rsplit(",", 1)
        city, state = c.strip() or None, (s.strip()[:2].upper() or None)
    v = body.get("vertical") if body.get("vertical") in verticals.VERTICALS else None
    if not v or v == "events":                            # guess, default to restaurants (admin recategorizes)
        v = assistant._guess_vertical(f"{name} {raw_city}") or "restaurants"
    if v == "events":
        v = "restaurants"
    website = (body.get("website") or "").strip()[:300] or None
    # Enrich the bare name/city into a full candidate (OSM + the site + LLM category-fill) so a
    # chat-contributed place arrives rich -> better data + more likely to clear auto-approve.
    from .. import onboard, submissions
    try:
        payload = onboard.lookup(name, city or "", state or "", v, website=website)
        payload = onboard.ai_fill(v, payload)
    except Exception:
        payload = {"name": name, "city": city, "state": state}
    payload.setdefault("name", name)
    res = submissions.submit(v, payload, note="Suggested by a visitor via Dost chat")
    if res.get("ok"):
        return JSONResponse({"ok": True, "message":
                             f"🎉 Thank you! I've sent “{name}” to our team to verify and add to the "
                             "directory. Anything else I can help you find?"})
    return JSONResponse({"ok": False, "message": "Hmm, that didn't go through — please try again."},
                        status_code=400)


async def chat_flyer(request: Request) -> JSONResponse:
    """In-chat flyer upload: extract, then hand off to the SAME review form the portal upload uses --
    deliberately NOT a multi-turn conversation (see the flyer-upload plan's clarify-UX decision)."""
    email = portal_email(request)
    if not email:
        return JSONResponse({"reply": "Please sign in to upload a flyer.", "needs_login": True},
                            status_code=401)
    if not settings.flyer_uploads_enabled:
        return JSONResponse({"reply": "Flyer upload isn't available right now."}, status_code=503)
    form = await request.form()
    upload = form.get("image")
    if upload is None or not getattr(upload, "filename", None):
        return JSONResponse({"reply": "Please attach an image."}, status_code=400)
    data = await upload.read()
    res = flyer.create_upload(email, data, upload.content_type or "")
    if not res.get("ok"):
        msg = {"unsupported_image_type": "Please upload a JPG, PNG, or WEBP image.",
               "image_too_large": f"That image is too large (max {settings.max_upload_mb}MB)."}.get(
            res.get("error"), "Couldn't read that image.")
        return JSONResponse({"reply": msg}, status_code=400)
    link = f"/portal/flyer/{res['id']}/review"
    guess = (res.get("vertical_guess") or "").replace("_", " ").title() or "your flyer"
    return JSONResponse({"reply": f"Got it! I read your flyer — looks like {guess}. "
                                  f"Review and confirm the details here: {link}", "link": link})


def chat_redirect(request: Request) -> RedirectResponse:
    return RedirectResponse("/", status_code=308)   # chat moved to the homepage; keep old links


routes = [
    Route("/", chat_page, methods=["GET"]),          # the chatbot is the primary homepage
    Route("/chat", chat_redirect, methods=["GET"]),  # legacy path -> /
    Route("/chat/api", chat_api, methods=["POST"]),
    Route("/chat/stream", chat_stream, methods=["POST"]),
    Route("/chat/contribute", chat_contribute, methods=["POST"]),
    Route("/chat/flyer", chat_flyer, methods=["POST"]),
]
