"""A dependency-free INTERACTIVE map: pan, zoom, tap-a-pin.

Why hand-rolled rather than Leaflet/MapLibre
--------------------------------------------
Zero budget is a hard constraint and this codebase already favours no-dependency implementations
(the iCal parser, the static map, the sparklines). A vendored map library would mean 40-800KB of
third-party JS plus marker assets to ship and keep patched, for a feature that needs exactly four
gestures. This module is ~150 lines of vanilla JS over the Web-Mercator maths that `staticmap`
already had, so it stays inside `script-src 'self' 'unsafe-inline'` with no CSP change and costs
nothing to run.

Tile politeness (OSM's tile usage policy is a courtesy, not a contract)
  * the map lives inside a collapsed <details>, so a visitor who never opens it fetches no tiles
  * zoom is capped, there is no prefetching, and tiles outside the viewport are dropped
  * attribution is always rendered (ODbL requires it)
  * <noscript> falls back to the static map, so the feature degrades rather than disappears

Dark mode: the tile imagery is light in both themes on purpose — tinting someone else's map data
makes it harder to read, not easier. Only the surrounding chrome follows the palette.
"""

from __future__ import annotations

import html
import json

from . import staticmap

_MIN_Z, _MAX_Z = 3, 18
_PIN_CAP = 200          # a dense city would otherwise paint thousands of nodes

TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"


def _points(rows: list[dict], vertical: str) -> list[dict]:
    """The subset of listings that can appear on a map, in list order so pin numbers match."""
    out = []
    for i, r in enumerate(rows, 1):
        if r.get("lat") is None or r.get("lng") is None:
            continue
        out.append({
            "n": i,
            "id": r.get("id"),
            "lat": float(r["lat"]),
            "lng": float(r["lng"]),
            "name": r.get("name") or "",
            "city": r.get("city") or "",
            "state": r.get("state") or "",
            "v": r.get("vertical") or vertical,     # mixed result sets link each pin correctly
            "open": r.get("open_now"),
            "rating": r.get("community_rating") or r.get("rating"),
        })
        if len(out) >= _PIN_CAP:
            break
    return out


def render(rows: list[dict], vertical: str, *, title: str = "", height: int = 380,
           collapsed: bool = True) -> str:
    """An interactive map of `rows` (the same dicts the listing cards use: id, name, lat, lng).

    Returns "" when nothing has coordinates. Pair with `CSS` in the page's <style> and include
    `staticmap.CSS` too, for the <noscript> fallback.
    """
    pts = _points(rows, vertical)
    if not pts:
        return ""

    lats = [p["lat"] for p in pts]
    lngs = [p["lng"] for p in pts]
    cfg = {
        "pins": pts,
        "tile": TILE_URL,
        "minZ": _MIN_Z,
        "maxZ": _MAX_Z,
        # the client fits these bounds to its own width, which the server cannot know
        "bounds": [min(lats), min(lngs), max(lats), max(lngs)],
        "single": len(pts) == 1,
    }
    # "</" would end the <script> element early; JSON has no other way out of it.
    blob = json.dumps(cfg, ensure_ascii=False).replace("</", "<\\/")
    cap = html.escape(title or "Map of results")
    mid = f"m{abs(hash((cap, len(pts), pts[0]['id']))) % 10**8}"

    return (
        f"<details class='imap' {'' if collapsed else 'open'}>"
        f"<summary>🗺️ <span class='imap-lbl'>Show map</span>"
        f"<span class='imap-n'>{len(pts)} pin{'' if len(pts) == 1 else 's'}</span></summary>"
        f"<div class='imap-box' id='{mid}' style='height:{int(height)}px'"
        f" role='application' aria-label='{cap}'>"
        "<div class='imap-tiles' aria-hidden='true'></div>"
        "<div class='imap-pins'></div>"
        "<div class='imap-pop' hidden></div>"
        "<div class='imap-ctl'>"
        "<button type='button' class='imap-btn' data-act='in' aria-label='Zoom in'>+</button>"
        "<button type='button' class='imap-btn' data-act='out' aria-label='Zoom out'>−</button>"
        "<button type='button' class='imap-btn' data-act='fit' aria-label='Fit all pins'>⤢</button>"
        "<button type='button' class='imap-btn' data-act='me' aria-label='Centre on my location'>◎</button>"
        "</div>"
        "<div class='imap-hint'>Drag to pan · pinch or +/− to zoom · tap a pin</div>"
        "</div>"
        "<div class='imap-attr'>© <a href='https://www.openstreetmap.org/copyright' rel='nofollow'>"
        "OpenStreetMap</a> contributors</div>"
        f"<script>naMap('{mid}',{blob})</script>"
        # No JS (or a failed script): the plain tile grid still shows, already open.
        f"<noscript>{staticmap.render(rows, vertical, title=title)}</noscript>"
        "</details>")


# --------------------------------------------------------------------------------------- client
# One function, defined once per page, driving every map instance on it. Pointer events cover mouse
# and touch with the same code path; wheel is passive:false only so a zoom over the map doesn't
# scroll the page underneath it.
JS = """
window.naMap=window.naMap||function(id,cfg){
 var box=document.getElementById(id); if(!box) return;
 var T=256, tiles=box.querySelector('.imap-tiles'), pinL=box.querySelector('.imap-pins'),
     pop=box.querySelector('.imap-pop');
 var z=13, cx=0, cy=0, live={};           // cx,cy = centre in world pixels at zoom z

 function lon2x(l,zz){return (l+180)/360*Math.pow(2,zz)*T;}
 function lat2y(l,zz){var r=Math.max(Math.min(l,85.05),-85.05)*Math.PI/180;
   return (1-Math.log(Math.tan(r)+1/Math.cos(r))/Math.PI)/2*Math.pow(2,zz)*T;}
 function W(){return box.clientWidth;} function H(){return box.clientHeight;}

 function fit(){
  var b=cfg.bounds, zz;
  if(cfg.single){zz=15;}
  else{
   for(zz=cfg.maxZ; zz>cfg.minZ; zz--){
    var dx=Math.abs(lon2x(b[3],zz)-lon2x(b[1],zz)), dy=Math.abs(lat2y(b[0],zz)-lat2y(b[2],zz));
    if(dx<=W()*0.88 && dy<=H()*0.88) break;
   }
  }
  z=Math.max(cfg.minZ,Math.min(cfg.maxZ,zz));
  cx=(lon2x(b[1],z)+lon2x(b[3],z))/2; cy=(lat2y(b[0],z)+lat2y(b[2],z))/2;
  draw();
 }

 function draw(){
  var w=W(), h=H(), tlx=cx-w/2, tly=cy-h/2, n=Math.pow(2,z), seen={};
  var x0=Math.floor(tlx/T), x1=Math.floor((tlx+w)/T), y0=Math.floor(tly/T), y1=Math.floor((tly+h)/T);
  for(var tx=x0; tx<=x1; tx++){
   for(var ty=y0; ty<=y1; ty++){
    if(ty<0||ty>=n) continue;
    var wx=((tx%n)+n)%n, k=z+'/'+tx+'/'+ty, im=live[k];
    if(!im){
     // No loading="lazy": we only ever create tiles that are already in view, and a transformed
     // element inside an overflow-hidden box can confuse the lazy heuristic into never loading.
     im=document.createElement('img'); im.alt=''; im.decoding='async'; im.width=T; im.height=T;
     im.src=cfg.tile.replace('{z}',z).replace('{x}',wx).replace('{y}',ty);
     im.className='imap-t'; tiles.appendChild(im); live[k]=im;
    }
    im.style.transform='translate3d('+(tx*T-tlx)+'px,'+(ty*T-tly)+'px,0)';
    seen[k]=1;
   }
  }
  for(var k2 in live){ if(!seen[k2]){ live[k2].remove(); delete live[k2]; } }
  drawPins(tlx,tly);
 }

 function drawPins(tlx,tly){
  if(!pinL.children.length){
   cfg.pins.forEach(function(p,i){
    var a=document.createElement('button');
    a.type='button'; a.className='imap-pin'; a.textContent=p.n;
    a.setAttribute('aria-label',p.name||('Pin '+p.n));
    a.onclick=function(e){e.stopPropagation(); showPop(p);};
    pinL.appendChild(a);
   });
  }
  var w=W(), h=H();
  cfg.pins.forEach(function(p,i){
   var el=pinL.children[i];
   var px=lon2x(p.lng,z)-tlx, py=lat2y(p.lat,z)-tly;
   var vis=(px>-30 && px<w+30 && py>-40 && py<h+20);
   el.hidden=!vis;
   if(vis) el.style.transform='translate3d('+px+'px,'+py+'px,0) translate(-50%,-100%)';
  });
 }

 function showPop(p){
  var loc=[p.city,p.state].filter(Boolean).join(', ');
  var bits='<b>'+esc(p.name)+'</b>';
  if(loc) bits+='<span class="imap-pop-l">'+esc(loc)+'</span>';
  if(p.rating) bits+='<span class="imap-pop-r">★ '+p.rating+'</span>';
  if(p.open===true) bits+='<span class="imap-pop-o">● Open now</span>';
  bits+='<a class="imap-pop-a" href="/listing/'+p.v+'/'+p.id+'">View details →</a>';
  pop.innerHTML=bits+'<button type="button" class="imap-pop-x" aria-label="Close">×</button>';
  pop.querySelector('.imap-pop-x').onclick=function(){pop.hidden=true;};
  pop.hidden=false;
 }
 function esc(s){var d=document.createElement('span'); d.textContent=s||''; return d.innerHTML;}

 function setZoom(nz,ax,ay){
  nz=Math.max(cfg.minZ,Math.min(cfg.maxZ,nz)); if(nz===z) return;
  // keep the point under (ax,ay) fixed while the scale changes
  var w=W(), h=H(), gx=cx-w/2+(ax===undefined?w/2:ax), gy=cy-h/2+(ay===undefined?h/2:ay);
  var f=Math.pow(2,nz-z);
  cx=gx*f-((ax===undefined?w/2:ax)-w/2); cy=gy*f-((ay===undefined?h/2:ay)-h/2);
  z=nz; for(var k in live){live[k].remove(); delete live[k];} tiles.innerHTML=''; draw();
 }

 // --- drag to pan (mouse + touch through pointer events)
 var down=null;
 box.addEventListener('pointerdown',function(e){
  if(e.target.closest('.imap-pin,.imap-ctl,.imap-pop')) return;
  down={x:e.clientX,y:e.clientY,cx:cx,cy:cy}; box.setPointerCapture(e.pointerId);
  box.classList.add('is-drag');
 });
 box.addEventListener('pointermove',function(e){
  if(!down) return;
  cx=down.cx-(e.clientX-down.x); cy=down.cy-(e.clientY-down.y); draw();
 });
 function endDrag(){down=null; box.classList.remove('is-drag');}
 box.addEventListener('pointerup',endDrag); box.addEventListener('pointercancel',endDrag);

 // --- wheel + double-click zoom, anchored where the cursor is
 box.addEventListener('wheel',function(e){
  e.preventDefault(); var r=box.getBoundingClientRect();
  setZoom(z+(e.deltaY<0?1:-1), e.clientX-r.left, e.clientY-r.top);
 },{passive:false});
 box.addEventListener('dblclick',function(e){
  var r=box.getBoundingClientRect(); setZoom(z+1,e.clientX-r.left,e.clientY-r.top);
 });

 // --- pinch
 var pinch=null;
 box.addEventListener('touchstart',function(e){
  if(e.touches.length===2){endDrag();
   pinch={d:dist(e.touches),z:z};}
 },{passive:true});
 box.addEventListener('touchmove',function(e){
  if(pinch&&e.touches.length===2){
   var k=dist(e.touches)/pinch.d;
   setZoom(pinch.z+Math.round(Math.log(k)/Math.log(2)));
  }
 },{passive:true});
 box.addEventListener('touchend',function(){pinch=null;});
 function dist(t){var dx=t[0].clientX-t[1].clientX, dy=t[0].clientY-t[1].clientY;
  return Math.sqrt(dx*dx+dy*dy)||1;}

 // --- controls
 box.querySelector('.imap-ctl').addEventListener('click',function(e){
  var b=e.target.closest('.imap-btn'); if(!b) return;
  var a=b.dataset.act;
  if(a==='in') setZoom(z+1); else if(a==='out') setZoom(z-1);
  else if(a==='fit') fit();
  else if(a==='me'&&navigator.geolocation){
   b.disabled=true;
   navigator.geolocation.getCurrentPosition(function(pos){
    b.disabled=false; z=Math.max(z,14);
    cx=lon2x(pos.coords.longitude,z); cy=lat2y(pos.coords.latitude,z);
    for(var k in live){live[k].remove(); delete live[k];} tiles.innerHTML=''; draw();
   },function(){b.disabled=false;},{timeout:8000});
  }
 });
 box.addEventListener('click',function(e){
  if(!e.target.closest('.imap-pin,.imap-pop')) pop.hidden=true;
 });
 // keyboard panning, so the map is usable without a pointer
 box.tabIndex=0;
 box.addEventListener('keydown',function(e){
  var step=80, k=e.key;
  if(k==='ArrowLeft')cx-=step; else if(k==='ArrowRight')cx+=step;
  else if(k==='ArrowUp')cy-=step; else if(k==='ArrowDown')cy+=step;
  else if(k==='+'||k==='=')return setZoom(z+1); else if(k==='-')return setZoom(z-1);
  else return;
  e.preventDefault(); draw();
 });

 // Tiles are only fetched once the <details> is actually open — that is the politeness guarantee.
 var det=box.closest('details');
 function start(){ if(!box.dataset.ready){ box.dataset.ready='1'; fit(); } }
 if(det&&!det.open){ det.addEventListener('toggle',function(){ if(det.open) start(); }); }
 else { start(); }
 var rt; window.addEventListener('resize',function(){ if(!box.dataset.ready)return;
  clearTimeout(rt); rt=setTimeout(draw,150); });
};
"""


CSS = """
 .imap{margin:6px 0 16px}
 .imap summary{cursor:pointer;font-weight:600;color:var(--brand-strong);list-style:none;
   padding:9px 0;min-height:44px;display:flex;align-items:center;gap:9px}
 .imap summary::-webkit-details-marker{display:none}
 .imap-n{color:var(--muted);font-weight:500;font-size:13px}
 .imap-box{position:relative;overflow:hidden;border:1px solid var(--line);
   border-radius:var(--r-lg);background:var(--map-ground);touch-action:none;cursor:grab;
   max-width:100%}
 .imap-box.is-drag{cursor:grabbing}
 .imap-box:focus-visible{outline:2px solid var(--brand);outline-offset:2px}
 .imap-tiles,.imap-pins{position:absolute;inset:0}
 .imap-pins{pointer-events:none}
 .imap-t{position:absolute;top:0;left:0;width:256px;height:256px;will-change:transform;
   user-select:none;-webkit-user-drag:none}
 .imap-pin{position:absolute;top:0;left:0;pointer-events:auto;min-width:24px;height:24px;
   padding:0 6px;border-radius:12px;border:2px solid #fff;background:var(--brand-strong);
   color:#fff;font:700 11px/20px system-ui,sans-serif;cursor:pointer;
   box-shadow:0 1px 4px rgba(0,0,0,.45);will-change:transform}
 .imap-pin:hover,.imap-pin:focus-visible{background:var(--brand-strong-d);z-index:5}
 .imap-ctl{position:absolute;right:10px;top:10px;display:flex;flex-direction:column;gap:6px;z-index:6}
 .imap-btn{width:38px;height:38px;border-radius:10px;border:1px solid var(--line);
   background:var(--panel);color:var(--ink);font-size:17px;font-weight:700;cursor:pointer;
   box-shadow:var(--shadow-2);line-height:1}
 .imap-btn:hover{border-color:var(--brand);color:var(--brand-strong)}
 .imap-btn[disabled]{opacity:.5;cursor:default}
 .imap-pop{position:absolute;left:10px;bottom:10px;right:58px;z-index:7;background:var(--panel);
   border:1px solid var(--line);border-radius:var(--r-md);box-shadow:var(--shadow-3);
   padding:11px 34px 11px 13px;font-size:14px;line-height:1.45;color:var(--ink)}
 .imap-pop[hidden]{display:none!important}
 .imap-pop b{display:block;font-size:15px}
 .imap-pop-l{display:block;color:var(--muted);font-size:13px}
 .imap-pop-r{color:var(--star);font-weight:600;font-size:13px;margin-right:9px}
 .imap-pop-o{color:var(--ok);font-weight:600;font-size:13px}
 .imap-pop-a{display:inline-block;margin-top:5px;font-weight:600;color:var(--brand-strong)}
 .imap-pop-x{position:absolute;right:4px;top:4px;width:30px;height:30px;border:0;background:none;
   color:var(--muted);font-size:19px;cursor:pointer;line-height:1}
 .imap-hint{position:absolute;left:10px;top:10px;z-index:6;background:var(--panel);
   border:1px solid var(--line);border-radius:var(--r-pill);padding:4px 11px;font-size:11.5px;
   color:var(--muted);pointer-events:none;max-width:calc(100% - 70px);overflow:hidden;
   text-overflow:ellipsis;white-space:nowrap}
 .imap-attr{font-size:11px;color:var(--faint);margin-top:4px}
 .imap-attr a{color:var(--faint);text-decoration:underline}
 @media (max-width:560px){.imap-hint{display:none}}
 @media (prefers-reduced-motion:reduce){.imap-t,.imap-pin{will-change:auto}}
"""
