# ============================================================
# backend/routes/health.py
# KrashiMitra — /health
# ------------------------------------------------------------
#   GET /health          browser → the feature-by-feature status page
#                        curl/monitor → {"status":"ok"} exactly as before
#   GET /health/checks   the page's data, as JSON
#   GET /health/data     mandi freshness only (the `monitor` workflow's probe)
#
# ── Why /health is content-negotiated instead of a second URL ──
# The keep-alive workflow pings /health every 10 minutes so Render's free
# instance never spins down. That ping MUST stay database-free: the app's only
# other round-the-clock DB traffic (a 30-minute staleness watchdog) kept Neon's
# compute awake 24/7, burned the free compute allowance and quota-blocked the
# database — the watchdog was widened to 3 hours precisely to stop that. So:
#
#   Accept: */*                (curl, workflows)  → {"status":"ok"}, no DB
#   Accept: text/html,…        (a human's browser) → the HTML shell, no DB
#
# Neither path queries anything. The shell then asks /health/checks for the
# real data, which IS a dozen queries — but only when a person is looking at
# it, memoised for a minute (health_service.CACHE_TTL_SEC), and paused whenever
# the tab is in the background.
#
# Admin extras: /health?full=1 asks for the private cards (accounts, orders,
# storage headroom, which keys are configured) and challenges for the admin
# password. Everything the anonymous page shows is already public elsewhere on
# the site.
# ============================================================

import base64
import secrets

from fastapi import APIRouter, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse

from backend.services import health_service   # imported at start-up → BOOT_AT is the real boot

router = APIRouter()

# A status page has nothing to rank for and would only dilute the crawl budget
# the price pages need.
_NOINDEX = {"X-Robots-Tag": "noindex, nofollow", "Cache-Control": "no-store"}


def _wants_html(request: Request) -> bool:
    """True only for a real browser. curl sends `*/*`, which technically
    accepts HTML — so match the explicit type, never the wildcard."""
    return "text/html" in request.headers.get("accept", "").lower()


def _is_admin(request: Request) -> bool:
    """Same credentials as /admin, checked by hand so the route can stay open
    to anonymous callers and only challenge when full detail is asked for."""
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("basic "):
        return False
    try:
        user, _, pw = base64.b64decode(header[6:].strip()).decode("utf-8").partition(":")
    except Exception:
        return False
    from backend.routes.admin import ADMIN_USER, ADMIN_PASS
    return (secrets.compare_digest(user.encode(), ADMIN_USER.encode())
            and secrets.compare_digest(pw.encode(), ADMIN_PASS.encode()))


def _challenge() -> Response:
    return Response(status_code=401, content="admin login required",
                    headers={"WWW-Authenticate": 'Basic realm="KrashiMitra admin"'})


# ── the three endpoints ──────────────────────────────────────

@router.get("/health")
async def health(request: Request, full: int = 0):
    if not _wants_html(request):
        # Unchanged contract for keep-alive + monitor. No database, no imports,
        # no work — this is the liveness ping, nothing more.
        return JSONResponse({"status": "ok"}, headers=_NOINDEX)
    if full and not _is_admin(request):
        return _challenge()
    return HTMLResponse(_page(full=bool(full)), headers=_NOINDEX)


@router.get("/health/checks")
async def health_checks(request: Request, full: int = 0):
    """Feature-by-feature JSON. `full=1` needs the admin password and adds the
    private cards plus the numbers withheld from the public view."""
    detailed = bool(full)
    if detailed and not _is_admin(request):
        return _challenge()
    return JSONResponse(health_service.run_checks(detailed=detailed), headers=_NOINDEX)


@router.get("/health/data")
async def health_data(stale_after_hours: float = 30.0):
    """Public data-freshness probe for the external `monitor` workflow.
    Reports only how fresh the mandi feed is (nothing sensitive — the data
    date already shows on every /bhav page). `stale` flips true when no
    row-delivering mandi sync has run within stale_after_hours, so a silently
    stopped feed pages us even while nobody is watching."""
    from backend.services.sync_log_service import mandi_freshness
    return JSONResponse(mandi_freshness(stale_after_hours), headers=_NOINDEX)


# ── the page ─────────────────────────────────────────────────
# Deliberately standalone: no km-shell.css, no drawer-menu.js, no fonts, no
# icons, nothing fetched from anywhere. Every other page shares the universal
# shell, but a status page that needs the static site to be healthy in order to
# render is a status page that goes dark exactly when it is needed. It borrows
# the shell's palette so it still looks like KrashiMitra.

_CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{background:#f5f7f4;color:#1a2e23;
  font-family:'DM Sans','Noto Sans Devanagari',system-ui,-apple-system,'Segoe UI',sans-serif;
  line-height:1.5;padding:0 0 48px}
.wrap{max-width:1080px;margin:0 auto;padding:0 16px}
header.bar{background:#1a3c2e;color:#fff;padding:14px 0}
header.bar .wrap{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.brand{font-family:'Noto Serif Devanagari',Georgia,serif;font-weight:800;font-size:18px}
.bar a{color:#d8f3dc;text-decoration:none;font-size:13px;font-weight:600}
.bar .sp{flex:1}
.banner{margin:18px 0;padding:16px 18px;border-radius:14px;display:flex;gap:14px;
  align-items:center;border:1px solid #e5e9e6;background:#fff}
.banner .dot{width:14px;height:14px;border-radius:50%;flex:none}
.banner h1{font-size:19px;font-weight:800;line-height:1.3}
.banner p{font-size:13px;color:#4a5a52;margin-top:2px}
.banner.ok{background:#eefaf1;border-color:#b7e4c7}
.banner.warn{background:#fff8e6;border-color:#f2d99b}
.banner.down{background:#fdecec;border-color:#f3b5b5}
.dot.ok{background:#2d6a4f}.dot.warn{background:#e9a825}.dot.down{background:#c92a2a}
.dot.off{background:#adb5bd}
h2.grp{font-size:14px;font-weight:800;color:#1a3c2e;margin:26px 0 2px;
  text-transform:none;letter-spacing:.01em}
p.note{font-size:12px;color:#7c8983;margin-bottom:10px}
.grid{display:grid;gap:12px;grid-template-columns:repeat(auto-fill,minmax(272px,1fr))}
.card{background:#fff;border:1px solid #e5e9e6;border-radius:14px;padding:14px;
  border-left:4px solid #adb5bd}
.card.ok{border-left-color:#2d6a4f}.card.warn{border-left-color:#e9a825}
.card.down{border-left-color:#c92a2a}.card.off{border-left-color:#ced4da}
.card .top{display:flex;align-items:center;gap:8px}
.card .ico{font-size:17px;line-height:1}
.card .name{font-weight:700;font-size:14.5px;flex:1}
.pill{font-size:11px;font-weight:800;padding:3px 9px;border-radius:999px;white-space:nowrap}
.pill.ok{background:#d8f3dc;color:#1b4332}.pill.warn{background:#fdf0d0;color:#7a5a05}
.pill.down{background:#ffdede;color:#8b1a1a}.pill.off{background:#eceff1;color:#5a6a63}
.card .detail{font-size:13px;color:#344e41;margin-top:8px}
.card dl{margin-top:10px;border-top:1px dashed #e5e9e6;padding-top:8px;
  display:grid;grid-template-columns:auto 1fr;gap:3px 10px;font-size:11.5px}
.card dt{color:#7c8983;white-space:nowrap}
.card dd{color:#4a5a52;text-align:right;word-break:break-word}
footer{margin-top:26px;font-size:12px;color:#7c8983;display:flex;gap:12px;
  flex-wrap:wrap;align-items:center}
footer a{color:#2d6a4f}
.muted{color:#7c8983;font-size:13px;padding:20px 0}
@media (max-width:520px){.grid{grid-template-columns:1fr}}
"""

_JS = """
const FULL = %(full)s;
const L = {ok:'ठीक', warn:'ध्यान दें', down:'बंद', off:'चालू नहीं'};
const HEAD = {
  ok:  ['सब ठीक चल रहा है','हर सुविधा अपना काम कर रही है।'],
  warn:['कुछ चीज़ों पर ध्यान चाहिए','साइट चल रही है, पर नीचे पीले कार्ड देखिए।'],
  down:['कुछ बंद है','नीचे लाल कार्ड वाली सुविधा अभी काम नहीं कर रही।']
};
const el = (t,c,x)=>{const n=document.createElement(t); if(c)n.className=c;
  if(x!=null)n.textContent=x; return n;};

function card(c){
  const d = el('div','card '+c.status);
  const top = el('div','top');
  top.append(el('span','ico',c.icon), el('span','name',c.label),
             el('span','pill '+c.status, L[c.status]||c.status));
  d.append(top, el('div','detail',c.detail||''));
  if(c.facts && c.facts.length){
    const dl = el('dl');
    for(const [k,v] of c.facts){ dl.append(el('dt',null,k), el('dd',null,String(v))); }
    d.append(dl);
  }
  return d;
}

function render(p){
  const root = document.getElementById('out');
  root.textContent = '';
  const b = el('div','banner '+p.status);
  const txt = el('div');
  txt.append(el('h1',null,HEAD[p.status][0]), el('p',null,
    HEAD[p.status][1] + '  ·  ' + p.counts.ok + ' ठीक, ' + p.counts.warn +
    ' ध्यान, ' + p.counts.down + ' बंद'));
  b.append(el('div','dot '+p.status), txt);
  root.append(b);
  for(const g of p.groups){
    root.append(el('h2','grp',g.label), el('p','note',g.note));
    const grid = el('div','grid');
    g.checks.forEach(c=>grid.append(card(c)));
    root.append(grid);
  }
  document.getElementById('stamp').textContent =
    'जाँचा गया: ' + p.checked_at + ' · ' + p.took_ms + ' ms';
  document.title = (p.status==='ok'?'✅':p.status==='warn'?'⚠️':'🛑')
    + ' सिस्टम स्थिति — कृषि मित्र';
}

async function load(){
  try{
    const r = await fetch('/health/checks' + (FULL ? '?full=1' : ''),
                          {credentials:'same-origin'});
    if(r.status === 401){
      document.getElementById('stamp').textContent =
        'एडमिन विवरण के लिए लॉगिन चाहिए — /health?full=1 दोबारा खोलिए।';
      return;
    }
    render(await r.json());
  }catch(e){
    document.getElementById('stamp').textContent =
      'स्थिति नहीं मिल पाई — सर्वर जवाब नहीं दे रहा। (' + e + ')';
  }
}

// Poll only while somebody is actually looking. A status page left open in a
// background tab used to be exactly the kind of round-the-clock database
// traffic that keeps Neon's compute awake and burns the free allowance, so
// polling stops on tab-hide and is capped per visible stretch.
let ticks = 0, timer = null;
function start(){
  stop(); ticks = 0;
  timer = setInterval(()=>{
    if(document.visibilityState !== 'visible' || ++ticks > 30){ stop(); return; }
    load();
  }, 60000);
}
function stop(){ if(timer){ clearInterval(timer); timer = null; } }
document.addEventListener('visibilitychange', ()=>{
  if(document.visibilityState === 'visible'){ load(); start(); } else { stop(); }
});
load(); start();
"""


def _page(full: bool = False) -> str:
    js       = _JS % {"full": "true" if full else "false"}
    json_url = "/health/checks?full=1" if full else "/health/checks"
    admin_link = ("" if full else
                  '<span>·</span><a href="/health?full=1">एडमिन विवरण</a>')
    return f"""<!doctype html>
<html lang="hi"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>सिस्टम स्थिति — कृषि मित्र</title>
<style>{_CSS}</style>
</head><body>
<header class="bar"><div class="wrap">
  <span class="brand">कृषि मित्र</span>
  <span style="font-size:13px;opacity:.85">सिस्टम स्थिति</span>
  <span class="sp"></span>
  <a href="/">साइट पर जाएँ</a>
</div></header>
<div class="wrap">
  <div id="out"><p class="muted">जाँच हो रही है…</p></div>
  <footer>
    <span id="stamp"></span>
    <span>·</span>
    <a href="{json_url}">JSON</a>
    {admin_link}
  </footer>
</div>
<script>{js}</script>
</body></html>"""
