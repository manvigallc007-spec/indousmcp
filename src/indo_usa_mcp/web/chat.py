"""Human-facing chat front-end: a conversational search over the directory.

GET  /chat       -> the chat page (vanilla JS, no build step)
POST /chat/api   -> {messages, geo, filters} -> {reply, cards, provider}  (calls assistant.reply)
"""

from __future__ import annotations

import html
import json
import time

from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Route

from .. import assistant, verticals
from ..config import settings

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
    "Vegetarian South Indian near me",
    "Sweets shop for Diwali in Edison NJ",
    "Hindu temple in the Bay Area",
    "Bharatanatyam dance class",
]

# Per-category icon + accent colour for the result cards.
_CAT_ICON = {"restaurants": "🍛", "temples": "🛕", "groceries": "🛒", "professionals": "🩺",
             "salons": "💇", "events": "🎉", "apparel": "👗", "sweets": "🍬", "studios": "🧘",
             "services": "💸", "community": "🤝"}
_CAT_COLOR = {"restaurants": "#c1440e", "temples": "#b8860b", "groceries": "#2e7d32",
              "professionals": "#1565c0", "salons": "#ad1457", "events": "#6a1b9a",
              "apparel": "#c2185b", "sweets": "#e65100", "studios": "#00838f",
              "services": "#37474f", "community": "#5d4037"}
# One-line descriptor per category — the shared "identity" used on cards/headers everywhere.
_CAT_BLURB = {"restaurants": "Dosa, biryani, thali & more", "temples": "Hindu · Sikh · Jain",
              "groceries": "Spices, produce, frozen", "professionals": "Doctors, dentists, clinics",
              "salons": "Threading, henna, bridal", "events": "Festivals, garba, concerts",
              "apparel": "Sarees, lehengas, jewelry", "sweets": "Mithai & Indian bakeries",
              "studios": "Yoga, dance & music", "services": "Money transfer, travel, visa",
              "community": "Associations & cultural orgs"}

# Modern chat UI. Placeholders (__NAME__) are filled by .replace() so the CSS/JS braces
# don't need f-string escaping.
_CHAT_HTML = """<!doctype html><html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>__ANAME__ — __ATAG__</title>
<meta name="description" content="__OGDESC__">
<meta property="og:title" content="__ANAME__ — __ATAG__">
<meta property="og:description" content="__OGDESC__">
<meta property="og:type" content="website">
<meta property="og:url" content="__OGURL__">
<meta property="og:image" content="__OGIMG__">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="__ANAME__ — __ATAG__">
<meta name="twitter:description" content="__OGDESC__">
<meta name="twitter:image" content="__OGIMG__">
<link rel="canonical" href="__OGURL__">
<link rel="icon" type="image/svg+xml" href="/icon.svg">
<link rel="manifest" href="/manifest.webmanifest"><meta name="theme-color" content="#e8772e">
<script type="application/ld+json">__JSONLD__</script>
<script>if('serviceWorker' in navigator){window.addEventListener('load',function(){navigator.serviceWorker.register('/sw.js').catch(function(){})})}</script>
<style>
:root{--brand:#e8772e;--brand-d:#cf6212;--accent:#0f9b8e;--accent-d:#0c7e74;
 --bg:#faf7f2;--panel:#fff;--ink:#25303a;--muted:#6b7280;--line:#efe9e1}
*{box-sizing:border-box}html,body{height:100%}
body{margin:0;font-family:system-ui,-apple-system,"Segoe UI",Roboto,Arial,sans-serif;
 color:var(--ink);background:var(--bg);display:flex;flex-direction:column;height:100dvh}
a{color:var(--brand);text-decoration:none}
.topbar{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:11px 18px;
 background:var(--panel);border-bottom:1px solid var(--line);position:sticky;top:0;z-index:5}
.brand{display:flex;align-items:center;gap:10px;color:var(--ink)}
.brand .logo{width:34px;height:34px;border-radius:10px;display:grid;place-items:center;
 background:linear-gradient(135deg,#ffd9a0,#ffb56b);font-size:18px}
.brand b{font-size:15px;line-height:1.15;display:block}.brand i{font-style:normal;font-size:12px;color:var(--muted)}
.actions{display:flex;align-items:center;gap:12px}
.newchat{background:#fff;border:1px solid #e2e0dd;color:var(--ink);border-radius:9px;padding:7px 11px;
 font-size:13px;font-weight:600;cursor:pointer;display:flex;align-items:center;gap:6px;transition:.15s}
.newchat:hover{border-color:var(--brand);color:var(--brand)}
.status{display:flex;align-items:center;gap:6px;font-size:12px;color:var(--muted)}
.status .dot{width:8px;height:8px;border-radius:50%;background:#16a34a;box-shadow:0 0 0 3px #16a34a22}
@media(max-width:600px){.status{display:none}}
.filterbar{display:flex;gap:8px;overflow-x:auto;white-space:nowrap;padding:10px 16px;
 background:var(--panel);border-bottom:1px solid var(--line);-webkit-overflow-scrolling:touch}
.filterbar::-webkit-scrollbar{display:none}
.fchip{flex:0 0 auto;background:#fff;border:1px solid #e2e0dd;color:#555;border-radius:999px;
 padding:7px 13px;font-size:13px;cursor:pointer;transition:.15s}
.fchip:hover{border-color:#cfcdca}.fchip.on{background:var(--brand);color:#fff;border-color:var(--brand)}
.fchip.open.on{background:#137333;border-color:#137333}
.fchip.loc{color:var(--brand);border-color:#e7c3b6}
#log{flex:1;overflow-y:auto;scroll-behavior:smooth}
.wrap{max-width:760px;margin:0 auto;padding:18px 16px 8px;width:100%}
.welcome{max-width:620px;margin:6vh auto 0;padding:0 20px;text-align:center}
.hero-avatar{width:64px;height:64px;border-radius:18px;margin:0 auto 14px;display:grid;
 place-items:center;font-size:30px;background:linear-gradient(135deg,#ffd9a0,#ffb56b);box-shadow:0 8px 24px #c1440e22}
.welcome h1{font-size:24px;margin:0 0 8px}.welcome p{color:var(--muted);font-size:15px;margin:0 0 20px;line-height:1.5}
.chips{display:flex;flex-wrap:wrap;gap:9px;justify-content:center}
.chip{background:#fff;border:1px solid #e2e0dd;color:#374151;border-radius:999px;padding:9px 14px;
 font-size:13px;cursor:pointer;transition:.15s}.chip:hover{border-color:var(--brand);color:var(--brand)}
.msg{display:flex;gap:10px;margin:14px 0;align-items:flex-start}.msg.user{justify-content:flex-end}
.avatar{flex:0 0 auto;width:30px;height:30px;border-radius:9px;display:grid;place-items:center;
 font-size:16px;background:linear-gradient(135deg,#ffd9a0,#ffb56b)}
.content{max-width:calc(100% - 44px)}
.bubble{padding:11px 15px;border-radius:14px;line-height:1.5;font-size:15px;white-space:pre-wrap;word-wrap:break-word}
.bot .bubble{background:var(--panel);border:1px solid var(--line);border-top-left-radius:5px}
.user .bubble{background:var(--brand);color:#fff;border-top-right-radius:5px;max-width:80%}
.typing{display:inline-flex;gap:5px;padding:3px 2px}
.typing span{width:7px;height:7px;border-radius:50%;background:#c9c7c4;animation:bl 1.2s infinite}
.typing span:nth-child(2){animation-delay:.15s}.typing span:nth-child(3){animation-delay:.3s}
@keyframes bl{0%,80%,100%{opacity:.3;transform:translateY(0)}40%{opacity:1;transform:translateY(-2px)}}
.cards{margin-top:10px;display:grid;gap:10px}
.lc{background:var(--panel);border:1px solid var(--line);border-left:4px solid #777;border-radius:12px;
 padding:13px 15px;transition:.15s}.lc:hover{box-shadow:0 4px 16px rgba(0,0,0,.06)}
.lc-head{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:7px}
.badge{color:#fff;background:#777;border-radius:999px;font-size:11px;font-weight:600;padding:3px 10px;
 text-transform:capitalize;letter-spacing:.02em}
.pill{font-size:11px;font-weight:600;border-radius:999px;padding:3px 9px}
.pill.feat{background:#fff4e5;color:#b45309}.pill.open{background:#e7f6ec;color:#137333}
.pill.claimed{background:#e8f0fe;color:#1565c0}
.lc h4{margin:0;font-size:16px}.lc-loc{color:var(--muted);font-size:13px;margin-top:3px}
.lc-rate{color:#b45309;font-size:13px;font-weight:600;margin-top:3px}
.lc-fresh{color:#137333;font-size:12px;margin-top:5px}
.lc-desc{color:#4b5563;font-size:14px;margin:8px 0 0;line-height:1.45}
.lc-act{display:flex;gap:8px;margin-top:11px;flex-wrap:wrap}
.lc-btn{border:1px solid #e2e0dd;border-radius:9px;padding:6px 12px;font-size:13px;font-weight:500;
 color:var(--ink);transition:.15s}.lc-btn:hover{border-color:var(--brand);color:var(--brand)}
.addcta{display:inline-block;margin-top:10px;background:var(--brand);color:#fff;border-radius:10px;
 padding:8px 14px;font-size:13px;font-weight:600;transition:.15s}.addcta:hover{background:var(--brand-d);color:#fff}
.morebtn{display:block;margin-top:10px;background:#fff;border:1px solid var(--accent);color:var(--accent);
 border-radius:10px;padding:8px 14px;font-size:13px;font-weight:600;cursor:pointer;transition:.15s}
.morebtn:hover{background:var(--accent);color:#fff}
.composer{background:var(--panel);border-top:1px solid var(--line);padding:12px 16px;
 padding-bottom:max(12px,env(safe-area-inset-bottom))}
.composer-inner{max-width:760px;margin:0 auto;display:flex;align-items:flex-end;gap:10px;background:#fff;
 border:1px solid #ddd;border-radius:16px;padding:6px 6px 6px 14px;box-shadow:0 1px 2px rgba(0,0,0,.04)}
.composer-inner:focus-within{border-color:var(--brand);box-shadow:0 0 0 3px #c1440e1a}
#q{flex:1;border:0;outline:0;resize:none;font:inherit;font-size:15px;line-height:1.4;padding:8px 0;
 max-height:140px;background:transparent;color:var(--ink)}
.send{flex:0 0 auto;width:40px;height:40px;border:0;border-radius:12px;background:var(--brand);color:#fff;
 display:grid;place-items:center;cursor:pointer;transition:.15s}.send:hover{background:var(--brand-d)}
.hint{max-width:760px;margin:8px auto 0;text-align:center;color:#9aa0a6;font-size:11px}
@media(max-width:600px){.welcome{margin-top:4vh}.welcome h1{font-size:21px}}
</style></head><body>
<header class="topbar">
 <a class="brand" href="/"><span class="logo">🪷</span><span><b>__ANAME__</b><i>__AMEAN__</i></span></a>
 <div class="actions">
  <button class="newchat" onclick="newChat()" aria-label="Start a new chat">✎ New chat</button>
  <span class="status"><span class="dot"></span>__MODE__</span>
 </div>
</header>
<div class="filterbar"><button class="fchip loc" onclick="useLocation()">📍 Near me</button>__FCHIPS__</div>
<main id="log"><div class="wrap" id="thread">
 <section id="welcome" class="welcome">
  <div class="hero-avatar">🪷</div>
  <h1>Namaste! I'm __ANAME__ — that means “friend”.</h1>
  <p>Think of me as your desi friend for finding Indian America — restaurants, sweets, temples,
   events, classes, salons, doctors, jewelry and more across the USA. Tell me what you're looking
   for and roughly where, and I'll find the closest ones.</p>
  <div class="chips">__CHIPS__</div>
 </section>
</div></main>
<form class="composer" onsubmit="return submitForm(event)">
 <div class="composer-inner">
  <textarea id="q" rows="1" autocomplete="off" placeholder="Ask anything… e.g. vegetarian thali in Jersey City"></textarea>
  <button class="send" type="submit" aria-label="Send">
   <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="20" x2="12" y2="5"/><polyline points="5 12 12 5 19 12"/></svg>
  </button>
 </div>
 <div class="hint">__ANAME__ searches a live directory · Enter to send · Shift+Enter for a new line</div>
</form>
<script>
const ICON=__ICONS__, COLOR=__COLORS__;
const log=document.getElementById('log'), thread=document.getElementById('thread'), ta=document.getElementById('q');
const WELCOME=thread.innerHTML;
let history=[], geo=null, lastQuery='', lastBot=null;
let filters={vertical:null, open_now:false};
function newChat(){
  history=[];lastQuery='';lastBot=null;filters={vertical:null,open_now:false};
  document.querySelectorAll('.fchip').forEach(c=>c.classList.remove('on'));
  const all=document.querySelector('.fchip[data-v=""]');if(all)all.classList.add('on');
  thread.innerHTML=WELCOME;ta.value='';ta.style.height='auto';ta.focus();log.scrollTop=0;
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
  const head=el('div','lc-head');
  const badge=el('span','badge',icon+' '+v);badge.style.background=color;head.appendChild(badge);
  if(c.is_featured)head.appendChild(el('span','pill feat','★ Featured'));
  if(c.is_claimed)head.appendChild(el('span','pill claimed','✓ Owner-verified'));
  if(c.open_now)head.appendChild(el('span','pill open','● Open now'));
  d.appendChild(head);d.appendChild(el('h4',null,c.name||''));
  if(c.rating){const rt=el('div','lc-rate','★ '+c.rating+(c.rating_count?(' ('+c.rating_count+')'):'')+'/5');d.appendChild(rt);}
  const loc=[c.city,c.state].filter(Boolean).join(', ');
  let locline=loc;
  if(c.distance_miles!=null) locline+=(loc?' · ':'')+c.distance_miles+' mi';
  if(locline)d.appendChild(el('div','lc-loc','📍 '+locline));
  if(c.description)d.appendChild(el('p','lc-desc',c.description));
  if(c.verified_ago)d.appendChild(el('div','lc-fresh','✓ '+c.verified_ago));
  const act=el('div','lc-act');
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
function fillBot(content,reply,cards,suggest){content.innerHTML='';content.appendChild(el('div','bubble',reply||'…'));
  if(cards&&cards.length){const w=el('div','cards');const N=6;
    cards.slice(0,N).forEach(c=>w.appendChild(card(c)));content.appendChild(w);
    if(cards.length>N){const b=el('button','morebtn','Show '+(cards.length-N)+' more');
      b.onclick=function(){cards.slice(N).forEach(c=>w.appendChild(card(c)));b.remove();scroll();};content.appendChild(b);}
    const vs=[...new Set(cards.map(c=>c.vertical).filter(Boolean))];syncChip(vs.length===1?vs[0]:'');}
  if(suggest&&suggest.url){const a=el('a','addcta',suggest.label||'➕ Add to directory');a.href=suggest.url;a.target='_blank';a.rel='noopener';content.appendChild(a);}
  scroll();}
async function send(text,isRerun){
  hideWelcome();let content;
  if(!isRerun){addUser(text);history.push({role:'user',content:text});lastQuery=text;content=addBot();lastBot=content;}
  else{content=lastBot;content.innerHTML='';const b=el('div','bubble');b.appendChild(typing());content.appendChild(b);scroll();}
  try{
    const r=await fetch('/chat/api',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({messages:history,geo:geo,filters:filters})});
    const data=await r.json();fillBot(content,data.reply,data.cards,data.suggest_add);
    if(!isRerun)history.push({role:'assistant',content:data.reply||''});
  }catch(e){fillBot(content,'Sorry, something went wrong. Please try again.',[]);}
}
function submitForm(e){if(e&&e.preventDefault)e.preventDefault();const t=ta.value.trim();if(!t)return false;
  ta.value='';ta.style.height='auto';send(t,false);return false;}
function ask(text){send(text,false);}
ta.addEventListener('input',()=>{ta.style.height='auto';ta.style.height=Math.min(ta.scrollHeight,140)+'px';});
ta.addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();submitForm(e);}});
ta.focus();
// Deep-link / SEO SearchAction: /chat?q=... prefills and runs the search automatically.
(function(){var q=new URLSearchParams(location.search).get('q');if(q&&q.trim()){send(q.trim(),false);}})();
</script></body></html>"""


def chat_page(request: Request) -> HTMLResponse:
    if not assistant.enabled():
        return HTMLResponse("<h2>Chat is disabled.</h2>", status_code=503)
    plat = html.escape(settings.platform_name)
    aname = html.escape(settings.assistant_name)
    mode = "live assistant" if assistant.llm_active() else "smart search"
    chips = "".join(f"<button class='chip' onclick=\"ask(this.textContent)\">{html.escape(s)}</button>"
                    for s in _SUGGESTIONS)
    # Category filter chips (All + every vertical) + an Open-now toggle.
    fchips = "<button class='fchip on' data-v='' onclick='setVertical(this)'>All</button>"
    fchips += "".join(
        f"<button class='fchip' data-v='{k}' onclick='setVertical(this)'>{html.escape(cfg['label'])}</button>"
        for k, cfg in verticals.VERTICALS.items())
    fchips += "<button class='fchip open' onclick='toggleOpen(this)'>● Open now</button>"
    base = settings.public_web_url.rstrip("/")
    og_url = f"{base}/chat"
    og_img = f"{base}/og-image.svg"
    aname_raw = settings.assistant_name
    og_desc = (f"{aname_raw} ({settings.assistant_meaning}) is your friendly guide to Indian "
               f"America — find Indian restaurants, sweets, temples, doctors, events, classes, "
               f"salons and jewelry near you across the USA.")
    # JSON-LD so Google indexes the chatbot as a named app, with a search box pointing at /chat.
    jsonld = json.dumps([
        {"@context": "https://schema.org", "@type": "WebApplication", "name": aname_raw,
         "alternateName": f"{aname_raw} — {settings.platform_name}", "url": og_url,
         "applicationCategory": "TravelApplication", "operatingSystem": "Web",
         "description": og_desc,
         "offers": {"@type": "Offer", "price": "0", "priceCurrency": "USD"}},
        {"@context": "https://schema.org", "@type": "WebSite", "name": aname_raw, "url": og_url,
         "potentialAction": {"@type": "SearchAction",
                             "target": f"{og_url}?q={{search_term_string}}",
                             "query-input": "required name=search_term_string"}},
    ], ensure_ascii=False)
    repl = {
        "__PLAT__": plat, "__ANAME__": aname, "__MODE__": html.escape(mode),
        "__ATAG__": html.escape(settings.assistant_tagline),
        "__AMEAN__": html.escape(settings.assistant_meaning),
        "__FCHIPS__": fchips, "__CHIPS__": chips, "__OGURL__": html.escape(og_url),
        "__OGIMG__": html.escape(og_img), "__OGDESC__": html.escape(og_desc),
        "__JSONLD__": jsonld,
        "__ICONS__": json.dumps(_CAT_ICON, ensure_ascii=False),
        "__COLORS__": json.dumps(_CAT_COLOR),
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
    filters = {
        "vertical": raw.get("vertical") if isinstance(raw.get("vertical"), str) else None,
        "open_now": bool(raw.get("open_now")),
    }
    if not isinstance(messages, list):
        messages = []
    # clamp lengths defensively
    for m in messages:
        if isinstance(m, dict) and isinstance(m.get("content"), str):
            m["content"] = m["content"][:1000]
    result = assistant.reply(messages, geo=geo, filters=filters)
    return JSONResponse(result)


routes = [
    Route("/chat", chat_page, methods=["GET"]),
    Route("/chat/api", chat_api, methods=["POST"]),
]
