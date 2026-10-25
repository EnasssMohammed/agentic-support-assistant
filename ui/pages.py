"""Pages of the Velo platform: Home, Velo Agent (customer view) and Team Inbox."""

from __future__ import annotations

import logging
import os
from collections import Counter

import streamlit as st

from src.agent_loop import InvalidInputError, TerminalState, VeloAgent
from src.conversation import Conversation
from ui.theme import esc, page_header, tile
from ui.tickets import STATUS_LABELS, format_time, load_tickets, set_status

logger = logging.getLogger("velo.ui")
DEBUG = os.getenv("VELO_DEBUG") == "1"

HOME, AGENT, INBOX = "home", "agent", "inbox"

# (title, description, icon, target page or None for a placeholder)
MODULES = (
    ("Velo Agent", "Customer-facing AI agent that reads your policies, runs diagnostics and hands "
     "off to your team when it should.", "bot", AGENT),
    ("Team Inbox", "Escalated conversations with the full context: what was measured, what was "
     "tried and the suggested next step.", "inbox", INBOX),
    ("Knowledge Management Studio", "Write, review and publish the policies Velo answers from.", "book", None),
    ("Evaluation Lab", "Run test suites against the agent and compare resolution quality across models.",
     "flask", None),
    ("Analytics & Reports", "Resolution rate, escalation reasons and conversation trends.", "chart", None),
    ("Workflows", "Define handoff rules, approvals and routing for escalated cases.", "workflow", None),
    ("Integrations", "Connect your helpdesk, CRM and messaging channels.", "plug", None),
    ("Settings", "Models, tone of voice, languages and team permissions.", "settings", None),
)

WELCOME = (
    "مرحباً، أنا **Velo**، مساعد الدعم الفني بالذكاء الاصطناعي.\n\n"
    "أبحث في قاعدة المعرفة، وأجري فحوصات تشخيصية آمنة، وأحوّل حالتك إلى فريق الدعم "
    "عندما يلزم ذلك.\n\n"
    "ما المشكلة التي تواجهها؟"
)

SUGGESTIONS = (
    "الإنترنت منقطع عندي بالكامل",
    "لمبة الإنترنت في الراوتر حمراء",
    "الاتصال بطيء ويتقطع",
    "لا أستطيع تسجيل الدخول إلى حسابي",
)
QUICK_REPLIES = (
    ("تم حل المشكلة", "تم الحل، الإنترنت اشتغل"),
    ("ما زالت المشكلة قائمة", "ما زالت المشكلة قائمة، نفس المشكلة"),
)
KIND_LABELS = {
    "hard_fault": "Hardware fault confirmed",
    "unresolved": "Unresolved after repeated attempts",
    "model": "Agent judgment",
    "tool_failure": "Diagnostic tool failed",
}


# --------------------------------------------------------------------- state

def init_state() -> None:
    st.session_state.setdefault("page", HOME)
    st.session_state.setdefault("messages", [])
    st.session_state.setdefault("conversation", Conversation())
    st.session_state.setdefault("queued", None)
    st.session_state.setdefault("selected_ticket", None)


def go(page: str) -> None:
    st.session_state.page = page


def queue(text: str) -> None:
    st.session_state.queued = text


def reset_chat() -> None:
    st.session_state.messages = []
    st.session_state.conversation = Conversation()


# ---------------------------------------------------------------------- home

def render_home() -> None:
    page_header("Welcome to Velo", "Your AI support agent and the team behind it, in one workspace.")

    counts = Counter(t["status"] for t in load_tickets())
    cols = st.columns(3)
    for col, key in zip(cols, ("new", "in_progress", "closed")):
        col.markdown(
            f'<div class="stat"><b>{counts.get(key, 0)}</b><span>{STATUS_LABELS[key]} tickets</span></div>',
            unsafe_allow_html=True,
        )

    st.markdown("#### Workspace")
    for row in range(0, len(MODULES), 3):
        cols = st.columns(3)
        for col, (title, desc, icon, target) in zip(cols, MODULES[row:row + 3]):
            with col, st.container(border=True):
                live = target is not None
                st.markdown(
                    f'{tile(icon, muted=not live)}<div class="card-title">{esc(title)}</div>'
                    f'<div class="card-desc">{esc(desc)}</div>',
                    unsafe_allow_html=True,
                )
                if live:
                    st.button("Open", key=f"open_{title}", on_click=go, args=(target,),
                              use_container_width=True)
                else:  # placeholder for a future module
                    st.button("Coming soon", key=f"soon_{title}", disabled=True,
                              use_container_width=True)


# ------------------------------------------------------------- customer page

@st.cache_resource(show_spinner="Starting Velo…")
def load_agent() -> VeloAgent:
    from src.model_client import get_model_client
    from src.rag_engine import RAGEngine
    from src.settings import load_settings

    provider = getattr(load_settings(), "model_provider", "openai")
    provider = getattr(provider, "value", provider)
    return VeloAgent(model=get_model_client(), rag=RAGEngine(provider=provider))


def handle_message(agent: VeloAgent, text: str) -> None:
    conv: Conversation = st.session_state.conversation
    messages = st.session_state.messages
    messages.append({"role": "user", "content": text})

    size_before = len(conv.messages)
    had_diagnostic = conv.diagnostic is not None

    try:
        result = agent.reply(conv, text)
    except InvalidInputError:
        messages.append({"role": "assistant",
                         "content": "رسالتك فارغة أو أطول من 2000 حرف. اختصرها وأعد الإرسال."})
        return
    except Exception:
        logger.exception("Unhandled error while processing a message")
        if len(conv.messages) > size_before:
            conv.drop_last()
        messages.append({"role": "assistant",
                         "content": "تعذّر إكمال طلبك الآن بسبب خلل تقني. أعد المحاولة بعد لحظات."})
        return

    actions: list[str] = []
    if result.turns_used > 0:
        actions.append("راجع قاعدة المعرفة")
    diagnostic = conv.diagnostic
    if (diagnostic is not None and not had_diagnostic
            and not str(getattr(diagnostic, "detail", "")).startswith("unverified")):
        actions.append("شغّل فحصاً تشخيصياً")
    ticket = result.ticket
    if ticket is not None:
        actions.append(f"فُتحت تذكرة {ticket.ticket_id}")

    entry = {
        "role": "assistant",
        "content": result.reply_text,
        "actions": actions,
        "quick_replies": (result.terminal_state == TerminalState.AWAITING_CUSTOMER
                          and conv.agent_replies > 0),
    }
    if DEBUG and result.error_message:
        entry["debug"] = result.error_message
    messages.append(entry)


def _render_message(index: int, message: dict, is_last: bool) -> None:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if message.get("actions"):
            chips = "".join(
                f'<span class="{"ticket" if "تذكرة" in a else ""}">{esc(a)}</span>'
                for a in message["actions"]
            )
            st.markdown(f'<div class="trace">{chips}</div>', unsafe_allow_html=True)
        if DEBUG and message.get("debug"):
            st.code(message["debug"])
    if is_last and message.get("quick_replies"):
        cols = st.columns(len(QUICK_REPLIES))
        for col, (label, text) in zip(cols, QUICK_REPLIES):
            col.button(label, key=f"qr_{index}_{label}", on_click=queue, args=(text,))


def render_customer() -> None:
    page_header("Velo Agent", "AI-assisted support, exactly as your customers see it.", "Customer view")
    try:
        agent = load_agent()
    except Exception:
        logger.exception("Agent failed to start")
        st.error("Velo could not start. Check the model settings in your .env file and reload.")
        return

    messages = st.session_state.messages
    if messages:
        st.button("New conversation", on_click=reset_chat)

    # Shown by the UI, not stored in the conversation, so it never counts as an agent reply.
    with st.chat_message("assistant"):
        st.markdown(WELCOME)

    if not messages:
        cols = st.columns(2)
        for i, text in enumerate(SUGGESTIONS):
            cols[i % 2].button(text, key=f"sg_{i}", on_click=queue, args=(text,),
                               use_container_width=True)

    for i, message in enumerate(messages):
        _render_message(i, message, is_last=i == len(messages) - 1)

    prompt = st.chat_input("اكتب رسالتك هنا") or st.session_state.queued
    st.session_state.queued = None
    if prompt and prompt.strip():
        with st.chat_message("user"):
            st.markdown(prompt)
        with st.spinner("Velo is looking into it…"):
            handle_message(agent, prompt.strip())
        st.rerun()


# ----------------------------------------------------------------- team inbox

def _section(label: str, body: str) -> None:
    st.markdown(
        f'<div class="tk-sec"><div class="k">{esc(label)}</div><div class="v">{esc(body)}</div></div>',
        unsafe_allow_html=True,
    )


def _select(ticket_id: str) -> None:
    st.session_state.selected_ticket = ticket_id


def _render_ticket(ticket: dict) -> None:
    tid, status = ticket["ticket_id"], ticket["status"]
    priority = ticket.get("priority", "normal")
    kind = KIND_LABELS.get(ticket.get("escalation_kind"), "Escalated")
    high = '<span class="badge high">High priority</span>' if priority == "high" else ""
    st.markdown(
        f'<div class="tk-head"><code>#{esc(tid)}</code>{high}'
        f'<span class="badge {status}">{STATUS_LABELS[status]}</span>'
        f'<span class="badge">{esc(kind)}</span>'
        f'<span class="badge">{esc(format_time(ticket.get("created_at")))}</span></div>',
        unsafe_allow_html=True,
    )

    a, b, c = st.columns(3)
    a.button("Take ownership", key=f"take_{tid}", on_click=set_status, args=(tid, "in_progress"),
             disabled=status != "new", use_container_width=True)
    b.button("Mark resolved", key=f"done_{tid}", on_click=set_status, args=(tid, "closed"),
             disabled=status == "closed", use_container_width=True)
    c.button("Reopen", key=f"reopen_{tid}", on_click=set_status, args=(tid, "new"),
             disabled=status != "closed", use_container_width=True)
    st.write("")

    diag = ticket.get("diagnostic_result")
    diag_text = (f'{diag.get("status", "?")}: {diag.get("detail", "")}' if isinstance(diag, dict)
                 else "No diagnostic was run.")

    _section("Customer request", ticket.get("customer_message", "—"))
    _section("Suggested next step", ticket.get("suggested_human_action", "—"))
    _section("Diagnostic result", diag_text)
    if ticket.get("customer_reply"):
        _section("What Velo told the customer", ticket["customer_reply"])

    with st.expander("Agent reasoning and policy"):
        _section("Reasoning", ticket.get("agent_reasoning", "—"))
        _section("Policy cited", ticket.get("policy_cited", "—"))
    if ticket.get("conversation_transcript"):
        with st.expander("Full conversation"):
            st.text(ticket["conversation_transcript"])


def render_inbox() -> None:
    page_header("Team Inbox", "Conversations Velo escalated to a human. Newest first.")
    tickets = load_tickets()

    top, refresh = st.columns([5, 1])
    flt = top.radio("Filter", ("all", "new", "in_progress", "closed"), horizontal=True,
                    label_visibility="collapsed", key="inbox_filter",
                    format_func=lambda v: "All" if v == "all" else STATUS_LABELS[v])
    refresh.button("Refresh", use_container_width=True)

    visible = [t for t in tickets if flt == "all" or t["status"] == flt]
    if not visible:
        st.info("No tickets here yet. Escalated conversations will appear automatically.")
        return

    ids = [t["ticket_id"] for t in visible]
    selected = st.session_state.selected_ticket
    if selected not in ids:
        selected = ids[0]

    left, right = st.columns([2, 3])
    with left:
        for t in visible:
            preview = (t.get("customer_message", "") or "—").replace("\n", " ")[:46]
            flag = "High · " if t.get("priority") == "high" else ""
            st.button(f"#{t['ticket_id']}  {flag}{preview}", key=f"pick_{t['ticket_id']}",
                      on_click=_select, args=(t["ticket_id"],), use_container_width=True,
                      type="primary" if t["ticket_id"] == selected else "secondary")
    with right, st.container(border=True):
        _render_ticket(next(t for t in visible if t["ticket_id"] == selected))
