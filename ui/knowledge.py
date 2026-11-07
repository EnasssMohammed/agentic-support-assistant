"""Knowledge Management Studio: upload, write, review, publish, version and audit the policies Velo answers from.

All rules live in src/knowledge.py; this module only draws them. Publishing indexes the new knowledge base
before it goes live, and any failure restores the previous one.
"""

from __future__ import annotations

import logging

import streamlit as st

from src.knowledge import (
    ALLOWED_SUFFIXES,
    KnowledgeError,
    KnowledgeStore,
    Review,
    check_pin,
    pin_required,
)
from ui import runtime
from ui.theme import esc, page_header

logger = logging.getLogger("velo.ui.knowledge")

TEMPLATE = """# Policy title

## 1. First topic:
State the rule in full sentences. Keep one topic under each heading.
* Each bullet is one condition or one step.

## 2. Second topic:
Say who does what, and within how long.
"""

FORMAT_GUIDE = """
**Best results: a heading per topic.** Velo cuts a document at its headings, so each answer is built from a whole
rule with its heading, never half a rule.

* Markdown headings: `## 1. Refunds` or numbered headings: `1. Refunds:`
* Or entries: `- [Return Window]:` followed by the rule (the format of the built-in manual)
* Write **only what Velo can actually do or tell the customer.** If a policy says "a technician is dispatched within
  48 hours", Velo may promise that to a customer, but it has no tool that does it. Describe human processes as
  handled by "the support team".
* If two documents define the same rule (for example "Rule #2"), keep one wording. The review warns you.
"""


def _store() -> KnowledgeStore:
    return KnowledgeStore()


def _verify(files) -> None:
    runtime.build_rag(tuple(str(f) for f in files))


def _gate() -> bool:
    if not pin_required():
        st.warning("No access control: anyone who can open this app can change the policies Velo answers from. "
                   "Set `VELO_STUDIO_PIN` in `.env` before sharing it.")
        return True
    if st.session_state.get("studio_unlocked"):
        return True
    st.info("The Knowledge Management Studio is protected. Enter the PIN to continue.")
    pin = st.text_input("Studio PIN", type="password", key="studio_pin_input")
    if st.button("Unlock", key="studio_unlock"):
        if check_pin(pin):
            st.session_state.studio_unlocked = True
            st.rerun()
        st.error("Wrong PIN.")
    return False


def _review_card(review: Review) -> None:
    with st.container(border=True):
        state = "Ready to publish" if review.ok else "Blocked"
        st.markdown(f"**{esc(review.name)}** &nbsp; <span class='badge {'live' if review.ok else 'high'}'>"
                    f"{state}</span>", unsafe_allow_html=True)
        for problem in review.problems:
            st.error(problem)
        for warning in review.warnings:
            st.warning(warning)
        if review.ok:
            replaces = " · replaces the published version" if review.replaces else ""
            st.caption(f"{review.structure} · {review.entries} searchable pieces · {review.size / 1024:.1f} KB{replaces}")
            with st.expander("Preview"):
                st.markdown(f'<div dir="auto" style="white-space:pre-wrap">{esc(review.text[:2500])}</div>',
                            unsafe_allow_html=True)


def _publish_controls(reviews: list[Review], items: list[tuple[str, bytes]], key: str, author: str) -> None:
    """Note, acknowledgement and the publish button, shared by Upload and Write."""
    if not reviews:
        return
    blocked = any(not r.ok for r in reviews)
    has_warnings = any(r.warnings for r in reviews)
    note = st.text_input("What changed and why (kept in the activity log)", key=f"{key}_note", max_chars=300)
    acknowledged = (st.checkbox("I read every warning above and they are acceptable", key=f"{key}_ack")
                    if has_warnings and not blocked else False)
    ready = not blocked and bool(author.strip()) and (acknowledged or not has_warnings)
    if not author.strip():
        st.caption("Enter your name at the top of the page to publish.")
    label = f"Publish {len(reviews)} document{'s' if len(reviews) > 1 else ''}"
    if st.button(label, type="primary", disabled=not ready, key=f"{key}_go"):
        if _act(lambda: _store().publish_many(items, author, note, acknowledged, verify=_verify),
                f"Published {len(reviews)} document(s)."):
            st.session_state[f"{key}_serial"] = st.session_state.get(f"{key}_serial", 0) + 1
            st.rerun()


def _act(action, success: str) -> bool:
    """Run a store change with a spinner. Always drops the cached agent, because a rolled-back change may have
    rebuilt the index in between."""
    try:
        with st.spinner("Working on the knowledge base…"):
            action()
    except KnowledgeError as exc:
        runtime.clear_caches()
        st.error(str(exc))
        return False
    runtime.clear_caches()
    st.session_state.studio_flash = f"{success} Knowledge base version {_store().version()[:12]}."
    return True


# ------------------------------------------------------------------------------------------- tabs

def _library(store: KnowledgeStore, author: str) -> None:
    builtin = store.builtin_info()
    if builtin:
        with st.container(border=True):
            st.markdown(f"**{esc(builtin.name)}** &nbsp; <span class='badge'>Built-in manual</span>",
                        unsafe_allow_html=True)
            st.caption(f"{builtin.structure} · {builtin.entries} searchable pieces · read-only here. It is changed "
                       "through a pull request, so the evaluation suite runs on every change.")
    docs = store.documents()
    if not docs:
        st.info("No documents published yet. Use **Upload** to add your policy files, or **Write** to create one.")
    for doc in docs:
        with st.container(border=True):
            st.markdown(f"**{esc(doc.name)}** &nbsp; <span class='badge live'>Published</span>", unsafe_allow_html=True)
            st.caption(f"{doc.structure} · {doc.entries} searchable pieces · {doc.size / 1024:.1f} KB · "
                       f"updated {doc.modified} · {doc.sha256[:8]}")
            with st.expander("Preview"):
                st.markdown(f'<div dir="auto" style="white-space:pre-wrap">{esc(store.read(doc.name)[:6000])}</div>',
                            unsafe_allow_html=True)
            if doc.versions:
                with st.expander(f"Earlier versions ({doc.versions})"):
                    for version in store.versions(doc.name):
                        left, right = st.columns([4, 1])
                        left.caption(f"{version.saved} · {version.size / 1024:.1f} KB · {version.sha256[:8]}")
                        if right.button("Restore", key=f"restore_{doc.name}_{version.id}", disabled=not author.strip()):
                            if _act(lambda d=doc.name, v=version.id: store.restore(
                                    d, v, author, acknowledged=True, verify=_verify), f"Restored {doc.name}."):
                                st.rerun()
            if st.session_state.get("studio_confirm_delete") == doc.name:
                st.warning(f"Delete {doc.name}? It stays in the earlier versions, so it can be restored.")
                yes, no = st.columns(2)
                if yes.button("Yes, delete", key=f"yes_{doc.name}", disabled=not author.strip()):
                    st.session_state.studio_confirm_delete = None
                    if _act(lambda d=doc.name: store.delete(d, author, verify=_verify), f"Deleted {doc.name}."):
                        st.rerun()
                if no.button("Cancel", key=f"no_{doc.name}"):
                    st.session_state.studio_confirm_delete = None
                    st.rerun()
            elif st.button("Delete", key=f"del_{doc.name}"):
                st.session_state.studio_confirm_delete = doc.name
                st.rerun()


def _upload(store: KnowledgeStore, author: str) -> None:
    st.caption("Upload `.txt` or `.md` files saved as UTF-8. Each file is reviewed before anything is published.")
    serial = st.session_state.get("up_serial", 0)
    files = st.file_uploader("Policy documents", type=[s.lstrip(".") for s in ALLOWED_SUFFIXES],
                             accept_multiple_files=True, key=f"studio_upload_{serial}",
                             label_visibility="collapsed")
    items = [(f.name, f.getvalue()) for f in files or []]
    reviews = [store.review(name, data) for name, data in items]
    for review in reviews:
        _review_card(review)
    _publish_controls(reviews, items, "up", author)


def _write(store: KnowledgeStore, author: str) -> None:
    with st.expander("How to write a policy Velo answers well"):
        st.markdown(FORMAT_GUIDE)
    names = ["New document", *[d.name for d in store.documents()]]
    choice = st.selectbox("Start from", names, key="studio_start")
    if st.session_state.get("studio_loaded") != choice:
        st.session_state.studio_loaded = choice
        st.session_state.studio_write_name = "" if choice == names[0] else choice
        st.session_state.studio_write_text = TEMPLATE if choice == names[0] else store.read(choice)
    name = st.text_input("File name", key="studio_write_name", placeholder="refund_policy.md")
    text = st.text_area("Policy text", key="studio_write_text", height=340)
    if name and not name.lower().endswith(ALLOWED_SUFFIXES):
        name += ".md"
    if not (name.strip() and text.strip()):
        return
    items = [(name, text.encode("utf-8"))]
    reviews = [store.review(name, items[0][1])]
    _review_card(reviews[0])
    _publish_controls(reviews, items, "wr", author)


def _try_it() -> None:
    st.caption("Ask a question a customer might ask and see which passages Velo would read. "
               "This calls the embedding service.")
    query = st.text_input("Question", key="studio_query")
    topic = st.selectbox("Topic filter", ["No filter", "router", "account", "billing"], key="studio_topic")
    if st.button("Search", key="studio_search") and query.strip():
        try:
            rag = runtime.load_rag(*runtime.current_kb())
            passages = rag.retrieve_passages(query, k=4, topic=None if topic == "No filter" else topic)
        except Exception:
            logger.exception("Knowledge search failed")
            st.error("The knowledge base could not be searched. Check the model settings in your .env file.")
            return
        if not passages:
            st.info("Nothing relevant was found. Velo would say it has no evidence and ask for details or escalate.")
        for passage in passages:
            with st.container(border=True):
                distance = f"{passage.distance:.3f}" if passage.distance is not None else "n/a"
                st.caption(f"{passage.source} · topic: {passage.topic} · distance {distance} (lower is closer)")
                st.markdown(f'<div dir="auto" style="white-space:pre-wrap">{esc(passage.text)}</div>',
                            unsafe_allow_html=True)


def _activity(store: KnowledgeStore) -> None:
    rows = store.audit()
    if not rows:
        st.info("No changes yet.")
        return
    st.dataframe(
        [{"When (UTC)": r.get("time", ""), "Action": r.get("action", ""),
          "Documents": ", ".join(r.get("documents", [])), "By": r.get("author", ""),
          "Note": r.get("note", ""), "KB version": r.get("kb_version", "")} for r in rows],
        use_container_width=True, hide_index=True,
    )


# -------------------------------------------------------------------------------------------- page

def render_knowledge() -> None:
    page_header("Knowledge Management Studio", "Upload, review and publish the policies Velo answers from.",
                "Staff view")
    if not _gate():
        return
    store = _store()
    if flash := st.session_state.pop("studio_flash", None):
        st.success(flash)

    builtin, docs = store.builtin_info(), store.documents()
    pieces = (builtin.entries if builtin else 0) + sum(d.entries for d in docs)
    stats = (("Documents", str(len(docs) + (1 if builtin else 0))), ("Searchable pieces", str(pieces)),
             ("Version", store.version()[:12]), ("Changes logged", str(len(store.audit(1000)))))
    for col, (label, value) in zip(st.columns(4), stats):
        col.markdown(f'<div class="stat"><b>{esc(value)}</b><span>{esc(label)}</span></div>', unsafe_allow_html=True)

    st.text_input("Your name (recorded in the activity log)", key="studio_author", max_chars=60)
    author = st.session_state.get("studio_author", "")
    if docs:
        st.info("The evaluation reports in `reports/` cover the built-in manual only. After publishing, run "
                "`uv run python run_eval_v2.py --with-uploads --runs 5` and compare, because new policies change "
                "what Velo answers.")

    library, upload, write, try_it, activity = st.tabs(["Library", "Upload", "Write", "Try it", "Activity"])
    with library:
        _library(store, author)
    with upload:
        _upload(store, author)
    with write:
        _write(store, author)
    with try_it:
        _try_it()
    with activity:
        _activity(store)
