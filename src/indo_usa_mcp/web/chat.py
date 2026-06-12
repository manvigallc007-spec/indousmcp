"""Human-facing chat front-end: a conversational search over the directory.

GET  /chat       -> the chat page (vanilla JS, no build step)
POST /chat/api   -> {messages, geo} -> {reply, cards, provider}  (calls assistant.reply)
"""

from __future__ import annotations

import html
import json
import time

from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Route

from .. import assistant
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


def chat_page(request: Request) -> HTMLResponse:
    if not assistant.enabled():
        return HTMLResponse("<h2>Chat is disabled.</h2>", status_code=503)
    brand = "#c1440e"
    plat = html.escape(settings.platform_name)
    mode = "live assistant" if assistant.llm_active() else "smart search"
    chips = "".join(f"<button class='chip' onclick=\"ask(this.textContent)\">{html.escape(s)}</button>"
                    for s in _SUGGESTIONS)
    doc = f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Ask · {plat}</title>
<style>
 :root{{--brand:{brand}}}
 *{{box-sizing:border-box}}
 body{{font-family:system-ui,-apple-system,Segoe UI,Arial,sans-serif;margin:0;color:#1a1a1a;
   background:#faf7f5;height:100dvh;display:flex;flex-direction:column}}
 header{{padding:14px 18px;border-bottom:1px solid #eee;background:#fff}}
 header b{{font-size:18px}} header .mode{{color:#888;font-size:12px;margin-left:6px}}
 #log{{flex:1;overflow-y:auto;padding:18px;max-width:760px;margin:0 auto;width:100%}}
 .msg{{margin:10px 0;display:flex}} .msg.user{{justify-content:flex-end}}
 .bubble{{padding:10px 14px;border-radius:14px;max-width:80%;line-height:1.45;white-space:pre-wrap}}
 .user .bubble{{background:var(--brand);color:#fff;border-bottom-right-radius:4px}}
 .bot .bubble{{background:#fff;border:1px solid #eee;border-bottom-left-radius:4px}}
 .cards{{max-width:760px;margin:0 auto;width:100%;padding:0 18px}}
 .lc{{border:1px solid #e6e6e6;border-radius:12px;padding:12px 14px;margin:8px 0;background:#fff}}
 .lc .top{{display:flex;justify-content:space-between;align-items:baseline;gap:8px}}
 .lc h4{{margin:0;font-size:16px}} .lc .cat{{color:#fff;background:#777;border-radius:20px;
   font-size:11px;padding:2px 9px;text-transform:capitalize}}
 .lc .feat{{background:var(--brand)}} .lc .open{{color:#137333;font-size:12px;font-weight:600}}
 .lc p{{margin:6px 0;color:#444;font-size:14px}} .lc a{{color:var(--brand);font-size:13px;margin-right:12px}}
 .meta{{color:#888;font-size:13px}}
 form{{display:flex;gap:8px;padding:12px 18px;border-top:1px solid #eee;background:#fff;
   max-width:760px;margin:0 auto;width:100%}}
 #q{{flex:1;padding:12px;border:1px solid #ccc;border-radius:10px;font-size:15px}}
 button.send{{background:var(--brand);color:#fff;border:0;padding:0 18px;border-radius:10px;
   font-size:15px;cursor:pointer}}
 .chips{{max-width:760px;margin:0 auto;width:100%;padding:0 18px 8px;display:flex;flex-wrap:wrap;gap:8px}}
 .chip{{background:#fff;border:1px solid #ddd;color:#333;border-radius:20px;padding:7px 12px;
   font-size:13px;cursor:pointer}}
</style></head><body>
<header><b>{plat}</b><span class="mode">· {mode}</span></header>
<div id="log"><div class="msg bot"><div class="bubble">Namaste! 🙏 Ask me for Indian
 restaurants, sweets, temples, events, classes and more across the USA. Try a category and a city.</div></div></div>
<div class="cards" id="cards"></div>
<div class="chips">{chips}</div>
<form onsubmit="return submitForm(event)">
 <input id="q" autocomplete="off" placeholder="e.g. vegetarian thali in Jersey City">
 <button class="send" type="submit">Ask</button>
</form>
<script>
const log=document.getElementById('log'), cardsEl=document.getElementById('cards');
let history=[], geo=null;
navigator.geolocation && navigator.geolocation.getCurrentPosition(
  p=>{{geo={{lat:p.coords.latitude,lng:p.coords.longitude}}}}, ()=>{{}}, {{timeout:4000}});
function bubble(role,text){{
  const m=document.createElement('div'); m.className='msg '+role;
  const b=document.createElement('div'); b.className='bubble'; b.textContent=text;
  m.appendChild(b); log.appendChild(m); log.scrollTop=log.scrollHeight; return b;
}}
function renderCards(cards){{
  cardsEl.innerHTML='';
  (cards||[]).forEach(c=>{{
    const d=document.createElement('div'); d.className='lc';
    const top=document.createElement('div'); top.className='top';
    const h=document.createElement('h4'); h.textContent=c.name||'';
    const cat=document.createElement('span'); cat.className='cat'+(c.is_featured?' feat':'');
    cat.textContent=(c.is_featured?'★ ':'')+(c.vertical||'');
    top.appendChild(h); top.appendChild(cat); d.appendChild(top);
    const loc=[c.city,c.state].filter(Boolean).join(', ');
    const meta=document.createElement('div'); meta.className='meta';
    meta.textContent=loc+(c.open_now?'  ·  ':'');
    if(c.open_now){{const o=document.createElement('span');o.className='open';o.textContent='Open now';meta.appendChild(o);}}
    d.appendChild(meta);
    if(c.description){{const p=document.createElement('p');p.textContent=c.description;d.appendChild(p);}}
    const links=document.createElement('div');
    if(c.phone){{const a=document.createElement('a');a.href='tel:'+c.phone;a.textContent='Call';links.appendChild(a);}}
    if(c.website){{const a=document.createElement('a');a.href=c.website;a.target='_blank';a.rel='noopener';a.textContent='Website';links.appendChild(a);}}
    if(loc){{const a=document.createElement('a');a.href='https://maps.google.com/?q='+encodeURIComponent((c.name||'')+' '+loc);a.target='_blank';a.rel='noopener';a.textContent='Map';links.appendChild(a);}}
    d.appendChild(links); cardsEl.appendChild(d);
  }});
}}
function ask(text){{document.getElementById('q').value=text; submitForm(new Event('x'));}}
async function submitForm(e){{
  e.preventDefault && e.preventDefault();
  const q=document.getElementById('q'); const text=q.value.trim(); if(!text) return false;
  q.value=''; bubble('user',text); history.push({{role:'user',content:text}});
  const thinking=bubble('bot','…');
  try{{
    const r=await fetch('/chat/api',{{method:'POST',headers:{{'Content-Type':'application/json'}},
      body:JSON.stringify({{messages:history,geo:geo}})}});
    const data=await r.json();
    thinking.textContent=data.reply||'(no response)';
    history.push({{role:'assistant',content:data.reply||''}});
    renderCards(data.cards);
  }}catch(err){{thinking.textContent='Sorry, something went wrong. Please try again.';}}
  return false;
}}
</script></body></html>"""
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
    if not isinstance(messages, list):
        messages = []
    # clamp lengths defensively
    for m in messages:
        if isinstance(m, dict) and isinstance(m.get("content"), str):
            m["content"] = m["content"][:1000]
    result = assistant.reply(messages, geo=geo)
    return JSONResponse(result)


routes = [
    Route("/chat", chat_page, methods=["GET"]),
    Route("/chat/api", chat_api, methods=["POST"]),
]
