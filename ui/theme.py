"""Visual system for the Velo platform shell (light, calm, Intercom-Fin-like)."""

from __future__ import annotations

from html import escape

import streamlit as st

esc = escape

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+Arabic:wght@400;500;600;700&display=swap');
:root{--ink:#0F1B2D;--muted:#5B6778;--line:#E3E8F0;--canvas:#F5F7FA;--surface:#FFFFFF;
  --brand:#1F4FD8;--brand-soft:#EAF0FF;--ok:#0F7B5F;--ok-soft:#E1F1EC;--warn:#B4540A;
  --warn-soft:#FDEBDD;--bad:#B42318;--bad-soft:#FDE8E6}
html,body,.stApp,[data-testid="stAppViewContainer"]{background:var(--canvas)!important;color:var(--ink);
  font-family:'IBM Plex Sans Arabic',system-ui,sans-serif!important}
[data-testid="stToolbar"],#MainMenu,footer{display:none!important}
[data-testid="stHeader"]{background:transparent}
.block-container{max-width:1040px;padding:1.4rem 2rem 6rem}
p,li,span,label,button,textarea,input{font-family:inherit}

/* sidebar = platform nav */
[data-testid="stSidebar"]{background:var(--surface);border-inline-end:1px solid var(--line)}
[data-testid="stSidebar"] .block-container,[data-testid="stSidebarUserContent"]{padding-top:1.2rem}
.brand{display:flex;align-items:center;gap:10px;padding:2px 6px 18px}
.brand-mark{width:34px;height:34px;border-radius:10px;background:var(--ink);color:#fff;display:grid;
  place-items:center;font-weight:700}
.brand-name{font-weight:700;font-size:16px;line-height:1.1}
.brand-sub{font-size:11.5px;color:var(--muted)}
.nav-label{font-size:11px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);
  padding:14px 8px 6px}
[data-testid="stSidebar"] [role="radiogroup"]{gap:2px}
[data-testid="stSidebar"] [role="radiogroup"] label{padding:9px 12px;border-radius:10px;width:100%;cursor:pointer}
[data-testid="stSidebar"] [role="radiogroup"] label>div:first-child{display:none}
[data-testid="stSidebar"] [role="radiogroup"] label:hover{background:var(--canvas)}
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked){background:var(--brand-soft)}
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) p{color:var(--brand);font-weight:600}
.nav-soon{display:flex;justify-content:space-between;align-items:center;padding:8px 12px;font-size:14px;
  color:#8A94A6;border-radius:10px}
.nav-soon i{font-style:normal;font-size:10.5px;background:var(--canvas);border:1px solid var(--line);
  border-radius:999px;padding:1px 8px;color:var(--muted)}

/* page header */
.ph{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;margin:2px 0 20px}
.ph h1{font-size:26px;font-weight:700;margin:0 0 4px;line-height:1.3}
.ph p{margin:0;color:var(--muted);font-size:14.5px}

/* badges */
.badge{display:inline-block;font-size:12px;font-weight:600;border-radius:999px;padding:2px 10px;
  background:var(--canvas);color:var(--muted);border:1px solid var(--line)}
.badge.new{background:var(--warn-soft);color:var(--warn);border-color:transparent}
.badge.in_progress{background:var(--brand-soft);color:var(--brand);border-color:transparent}
.badge.closed{background:var(--ok-soft);color:var(--ok);border-color:transparent}
.badge.high{background:var(--bad-soft);color:var(--bad);border-color:transparent}
.badge.live{background:var(--ok-soft);color:var(--ok);border-color:transparent}

/* cards and tiles */
[data-testid="stVerticalBlockBorderWrapper"]{background:var(--surface);border-radius:14px;border-color:var(--line)}
.tile{width:38px;height:38px;border-radius:10px;background:var(--brand-soft);color:var(--brand);
  display:grid;place-items:center;margin-bottom:10px}
.tile.muted{background:var(--canvas);color:#8A94A6}
.tile svg{width:20px;height:20px;fill:none;stroke:currentColor;stroke-width:1.8;stroke-linecap:round;
  stroke-linejoin:round}
.card-title{font-weight:600;font-size:15.5px;margin-bottom:2px}
.card-desc{color:var(--muted);font-size:13.5px;line-height:1.7;min-height:46px}
.stat{background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:14px 18px}
.stat b{display:block;font-size:26px;line-height:1.2}
.stat span{color:var(--muted);font-size:13px}

/* buttons */
.stButton>button{background:var(--surface);border:1px solid var(--line);border-radius:10px;color:var(--ink);
  font-weight:500;justify-content:flex-start;text-align:start;unicode-bidi:plaintext}
.stButton>button:hover:not(:disabled){border-color:var(--brand);color:var(--brand);background:var(--surface)}
.stButton>button:disabled{background:var(--canvas);color:#8A94A6;border-color:var(--line);cursor:not-allowed}
.stButton>button:focus-visible{outline:2px solid var(--brand);outline-offset:2px}
.stButton>button[kind="primary"],.stButton>button[data-testid="stBaseButton-primary"]{
  background:var(--brand-soft);color:var(--brand);border-color:#BFD0F7}

/* chat */
[data-testid="stChatMessage"]{background:transparent;padding:6px 0;gap:12px}
[data-testid="stChatMessage"] p,[data-testid="stChatMessage"] li{font-size:15.5px;line-height:1.9;
  unicode-bidi:plaintext;text-align:start}
[data-testid="stChatMessageAvatarAssistant"]{background:var(--ink)!important;color:#fff!important;border-radius:10px}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]){background:var(--brand);
  border-radius:16px 16px 4px 16px;padding:8px 16px;width:fit-content;max-width:85%;margin-inline-start:auto}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) *{color:#fff!important}
[data-testid="stChatMessageAvatarUser"]{display:none}
.trace{display:flex;flex-wrap:wrap;gap:6px;margin-top:6px}
.trace span{font-size:12.5px;color:var(--muted);background:var(--surface);border:1px solid var(--line);
  border-radius:999px;padding:3px 11px}
.trace span.ticket{color:var(--brand);border-color:#BFD0F7;background:var(--brand-soft);font-weight:600}
[data-testid="stBottom"]>div{background:var(--canvas)}
[data-testid="stChatInput"]{background:var(--surface);border:1px solid var(--line);border-radius:14px}
[data-testid="stChatInput"]:focus-within{border-color:var(--brand);box-shadow:0 0 0 3px rgba(31,79,216,.15)}
[data-testid="stChatInput"] textarea{font-size:15px;unicode-bidi:plaintext;text-align:start}
.hero{text-align:center;padding:30px 0 18px}
.hero h2{font-size:28px;font-weight:700;margin:0 0 8px;unicode-bidi:plaintext}
.hero p{color:var(--muted);font-size:15px;line-height:1.8;max-width:52ch;margin:0 auto;unicode-bidi:plaintext}

/* ticket detail */
.tk-head{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin-bottom:14px}
.tk-head code{font-weight:700;font-size:16px;color:var(--brand);background:none}
.tk-sec{margin:0 0 14px}
.tk-sec .k{font-size:11.5px;font-weight:600;letter-spacing:.05em;text-transform:uppercase;color:var(--muted);
  margin-bottom:3px}
.tk-sec .v{font-size:14.5px;line-height:1.8;white-space:pre-wrap;unicode-bidi:plaintext;text-align:start}
@media (max-width:640px){.block-container{padding:1rem}.ph h1{font-size:22px}}
</style>
"""

ICONS = {
    "bot": '<rect x="4" y="8" width="16" height="12" rx="3"/><path d="M12 8V4M9 13v2M15 13v2"/>',
    "inbox": '<path d="M3 13l3-8h12l3 8v6H3z"/><path d="M3 13h5l1 2h6l1-2h5"/>',
    "book": '<path d="M4 5a2 2 0 012-2h13v16H6a2 2 0 00-2 2z"/><path d="M4 19V5"/>',
    "flask": '<path d="M9 3h6M10 3v6l-5 9a2 2 0 002 3h10a2 2 0 002-3l-5-9V3"/>',
    "chart": '<path d="M4 20V4M4 20h16M8 16v-5M13 16V8M18 16v-3"/>',
    "workflow": '<rect x="3" y="3" width="6" height="6" rx="1"/><rect x="15" y="15" width="6" height="6" rx="1"/>'
    '<path d="M9 6h4a2 2 0 012 2v7"/>',
    "plug": '<path d="M9 3v5M15 3v5M7 8h10v3a5 5 0 01-10 0zM12 16v5"/>',
    "settings": '<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M19 5l-2 2M7 17l-2 2"/>',
}


def inject() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def tile(icon: str, muted: bool = False) -> str:
    cls = "tile muted" if muted else "tile"
    return f'<div class="{cls}"><svg viewBox="0 0 24 24">{ICONS[icon]}</svg></div>'


def page_header(title: str, subtitle: str, badge: str = "") -> None:
    right = f'<span class="badge live">{esc(badge)}</span>' if badge else ""
    st.markdown(
        f'<div class="ph"><div><h1>{esc(title)}</h1><p>{esc(subtitle)}</p></div>{right}</div>',
        unsafe_allow_html=True,
    )
