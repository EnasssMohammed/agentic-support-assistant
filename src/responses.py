"""Customer-facing replies for deterministic paths of the Velo agent.

Voice: calm, specific, no filler. Every reply says what happened and what happens next.
Keeping the text here (not inside control flow) makes tone reviewable and testable.
"""

from __future__ import annotations

import re
from enum import Enum


class EscalationKind(str, Enum):
    HARD_FAULT = "hard_fault"      # Policy Rule #1
    UNRESOLVED = "unresolved"      # Policy Rule #2
    MODEL = "model"                # the model decided to escalate
    TOOL_FAILURE = "tool_failure"  # the diagnostic tool itself failed


MISSING_LABELS = {
    "router_light": "لون لمبة الإنترنت في الراوتر وحالتها (ثابتة أم تومض)",
    "device_scope": "هل المشكلة في كل الأجهزة أم في جهاز واحد",
    "restart": "هل أعدت تشغيل الراوتر، وما الذي تغيّر بعدها",
    "error_message": "رسالة الخطأ التي تظهر لك بالضبط",
    "reset_attempted": "هل جرّبت خيار «نسيت كلمة المرور»، وهل وصلتك رسالة إعادة التعيين",
    "two_factor": "هل حسابك يستخدم المصادقة الثنائية (رمز تحقق)",
}


def resolved() -> str:
    return (
        "سعدنا بحل المشكلة. أغلقنا هذه المحادثة.\n\n"
        "إذا عاد العطل أو ظهرت مشكلة أخرى، اكتب لنا وسنكمل من حيث توقفنا."
    )


def cannot_share_instructions() -> str:
    return (
        "لا أستطيع تغيير تعليماتي الداخلية أو مشاركتها.\n\n"
        "اكتب لي مشكلتك مع الإنترنت أو الحساب وسأساعدك فيها."
    )


def ask_for_details() -> str:
    return (
        "لأساعدك بسرعة أحتاج أن أعرف نوع المشكلة. صفها بكلماتك، أو اختر الأقرب:\n\n"
        "- لا يوجد اتصال بالإنترنت\n"
        "- الاتصال بطيء أو يتقطع\n"
        "- مشكلة في الحساب أو تسجيل الدخول"
    )


def request_missing_details(missing: tuple[str, ...]) -> str:
    items = "\n".join(f"- {MISSING_LABELS[key]}" for key in missing if key in MISSING_LABELS)
    return (
        "شكراً على التحديث. حتى لا أكرر خطوات جرّبتها، أحتاج منك:\n\n"
        f"{items}"
    )


def escalation_notice(
    kind: EscalationKind,
    ticket_id: str | None = None,
    attempts: int = 3,
) -> str:
    """What the customer is told when a case is handed to a human.

    Always deterministic. The model's own wording is deliberately not used: what the customer is promised
    must match what actually happened (a ticket exists), and free text from the model can promise more,
    or format it as invented steps. The model's reasoning travels in the ticket for the human instead.
    """
    if kind is EscalationKind.HARD_FAULT:
        body = (
            "أظهر الفحص عطلاً في العتاد لا يمكن إصلاحه عن بُعد، "
            "لذلك حوّلت حالتك مباشرة إلى فريق الصيانة مع نتيجة الفحص."
        )
    elif kind is EscalationKind.TOOL_FAILURE:
        body = (
            "تعذّر إجراء الفحص التشخيصي الآن، فحوّلت حالتك إلى فريق الدعم "
            "مع تفاصيل ما جرى."
        )
    elif kind is EscalationKind.UNRESOLVED:
        body = (
            f"لم نصل إلى حل بعد {attempts} محاولات، فحوّلت حالتك إلى فريق الدعم "
            "مع سجل المحادثة وما جرّبناه."
        )
    else:
        body = "هذه الحالة تحتاج إلى فريق الدعم، وقد حوّلتها إليه."

    if ticket_id is None:
        return body
    return (
        f"{body}\n\n"
        f"رقم المرجع: **{ticket_id}**\n"
        "سيتابع الفريق حالتك بكامل التفاصيل، ولن تحتاج إلى شرح المشكلة من جديد."
    )


def escalation_failed() -> str:
    return (
        "لم أتمكن من فتح تذكرة لحالتك الآن، وحالتك لم تُحوَّل بعد. "
        "أعد المحاولة بعد قليل، أو تواصل مع الدعم المباشر."
    )


def already_escalated(ticket_id: str) -> str:
    return (
        f"حالتك لدى فريق الدعم برقم المرجع **{ticket_id}**. "
        "الفريق هو من سيتابعها من هنا وسيتواصل معك مباشرة."
    )


def temporarily_unavailable() -> str:
    return (
        "تعذّر إكمال طلبك الآن بسبب خلل تقني مؤقت. لم تتأثر حالتك، "
        "أعد إرسال رسالتك بعد لحظات."
    )


_STEP = re.compile(r"(?:(?<=\s)|^)(\d{1,2})[\)\.]\s+(?=\S)")


def tidy(text: str) -> str:
    """Put numbered steps ("1) ... 2) ...") on their own lines so they render as a list."""
    expected, marks = 1, []
    for match in _STEP.finditer(text):
        if int(match.group(1)) == expected:
            marks.append(match)
            expected += 1
    if len(marks) < 2:
        return text.strip()
    parts, last = [], 0
    for i, match in enumerate(marks):
        parts.append(text[last:match.start()].rstrip())
        parts.append(("\n\n" if i == 0 else "\n") + f"{match.group(1)}. ")
        last = match.end()
    parts.append(text[last:])
    return "".join(parts).strip()
