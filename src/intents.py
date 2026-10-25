"""Deterministic intent detection for Velo (English and Arabic).

These helpers decide things the model should never be trusted with, such as whether
a customer confirmed the fix. Patterns are compiled once at import time.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


def normalize(text: str) -> str:
    """Lowercase, unify apostrophes and collapse whitespace."""
    return " ".join(text.lower().replace("\u2019", "'").split())


def _compile(*patterns: str) -> re.Pattern[str]:
    return re.compile("|".join(f"(?:{p})" for p in patterns))


_NOT_FIXED = (
    r"\bnot\s+(?:fixed|resolved|solved|working)\b",
    r"\bstill\s+(?:not working|offline|broken|not fixed)\b",
    r"\b(?:doesn't|does not|didn't|did not)\s+work\b",
    r"\bnot working yet\b",
    r"\b(?:issue|problem)\s+(?:persists|continues)\b",
    r"\b(?:connection|internet) is still down\b",
    r"\bno internet\b",
    r"\bthat (?:didn't|did not) help\b",
    r"لم تنحل", r"لم ينحل", r"لم يشتغل", r"لم يعمل", r"لم تحل",
    r"ما اشتغل", r"ما انحلت", r"ما فاد", r"ما نفعت",
    r"نفس المشكل", r"ما زال", r"ماذال", r"لا يعمل",
)

_FIXED = (
    r"\b(?:it's|it is|the internet is|the connection is) (?:working|fixed|resolved|restored|back)\b",
    r"\b(?:it's|it is) solved\b",
    r"\b(?:works|working) now\b",
    r"\b(?:internet|connection|service) is back\b",
    r"\bi can (?:connect|access websites) now\b",
    r"\bthe (?:issue is fixed|problem is solved)\b",
    r"\ball working now\b",
    r"\b(?:yes,?\s*)?(?:it works|that fixed it)\b",
    r"اشتغل", r"تم الحل", r"انحلت", r"صلحت", r"انحل المشكل",
)

_NEGATED_FIX = _compile(
    r"\bno\s*,?\s*(?:it|the issue|the problem)\b",
    r"\bnot\s+(?:fixed|resolved|working|solved)\b",
    r"\b(?:still|again)\s+not\s+working\b",
    *_NOT_FIXED,
)
_NOT_FIXED_RE = _compile(*_NOT_FIXED)
_FIXED_RE = _compile(*_FIXED)

_VAGUE = frozenset(
    {
        "its broken", "its broken fix it", "it is broken", "broken", "fix it",
        "its not working", "it is not working", "not working", "doesnt work",
        "it doesnt work", "does not work", "it does not work", "help",
        "something is wrong", "something is broken", "please fix it",
        "خربان", "مش شغال", "مش شغال عندي", "صلحه", "ساعدني", "في مشكلة", "عطلان",
    }
)

_LIGHT_RE = re.compile(
    r"\b(red|orange|amber|green|blue|white|blinking|flashing|off|no light|أحمر|احمر|أخضر|اخضر|يومض)\b"
)
_SCOPE_RE = re.compile(
    r"\b(all|every|multiple devices|one device|كل الأجهزة|كل الاجهزة|جهاز واحد)\b"
)
_RESTART_RE = re.compile(
    r"\b(restarted|rebooted|power.?cycled|عدت تشغيل|اعدت تشغيل|طفيته)\b"
)


# --------------------------------------------------------------- issue topic
# Latin terms are matched as whole words, Arabic terms as substrings (Arabic attaches
# prefixes: "الاتصال", "بحسابي"). A strong term scores 1, a weak (ambiguous) one 0.5.

def _terms(*patterns: str) -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(p) for p in patterns)


_TOPICS: dict[str, tuple[tuple[re.Pattern[str], ...], tuple[re.Pattern[str], ...]]] = {
    "account": (
        _terms(r"\blog\s?in\b", r"\bsign\s?in\b", r"\bpassword", r"\baccount", r"\blocked\b",
               r"\block\s?out", r"\busername\b", r"\b2fa\b", r"\btwo-?factor\b",
               r"\bverification code\b", "حساب", "تسجيل الدخول", "تسجيل دخول", "الدخول",
               "كلمة المرور", "كلمة السر", "باسورد", "مقفل", "البريد", "المصادقة", "رمز التحقق"),
        (),
    ),
    "billing": (
        _terms(r"\brefund", r"\breturn", r"\bcharge", r"\binvoice", r"\bbilling\b", r"\bpayment",
               r"\blicen[sc]e", r"\bpurchase", "استرجاع", "استرداد", "إرجاع", "ارجاع", "فاتورة", "رخصة", "المبلغ",
               "دفع", "خصم"),
        (),
    ),
    "router": (
        _terms(r"\brouter\b", r"\bwi-?fi\b", r"\bmodem\b", r"\binternet\b", r"\bled\b",
               r"\boffline\b", r"\bnetwork\b", r"\bhard[\s_-]?fault\b", r"\bsoftware[\s_-]?glitch\b",
               "راوتر", "رواتر", "مودم", "عتاد", "انترنت", "إنترنت", "واي فاي", "وايفاي", "لمبة", "منقطع",
               "تقطع", "بطيء", "بطئ", "شبكة"),
        _terms(r"\bconnect", r"\bdiagnostic", "اتصال", "تشخيص"),
    ),
}
_TOPIC_PRIORITY = ("account", "billing", "router")   # wins a tie


def classify_topic(message: str) -> str:
    """The type of issue a message describes: account, billing, router, or other.

    Account wording beats a weak connectivity word, so "لا أستطيع الاتصال بحسابي"
    (I cannot connect to my account) is an account issue, not a router issue.
    """
    text = normalize(message)
    scores = {
        topic: sum(1 for p in strong if p.search(text)) + 0.5 * sum(1 for p in weak if p.search(text))
        for topic, (strong, weak) in _TOPICS.items()
    }
    best = max(_TOPIC_PRIORITY, key=lambda t: scores[t])
    return best if scores[best] > 0 else "other"


def is_router_topic(message: str) -> bool:
    return classify_topic(message) == "router"


def policy_topic(text: str) -> str:
    """Topic tag of a knowledge-base entry; entries about no single topic are 'general'."""
    topic = classify_topic(text)
    return "general" if topic == "other" else topic


def topic_compatible(passage_topic: str, issue_topic: str | None) -> bool:
    """A passage may be shown when it is general or about the customer's current topic."""
    if issue_topic not in ("router", "account", "billing"):
        return True
    return passage_topic in ("general", issue_topic)


def customer_confirms_resolution(message: str) -> bool:
    """True only for an explicit, non-negated confirmation that the issue is fixed."""
    text = normalize(message)
    return not _NEGATED_FIX.search(text) and bool(_FIXED_RE.search(text))


def customer_reports_unresolved(message: str) -> bool:
    """True when the customer clearly says the issue is still there."""
    return bool(_NOT_FIXED_RE.search(normalize(message)))


# Instruction-override / prompt-extraction attempts. Deliberately narrow: each pattern needs both an
# override or extraction verb AND a noun that names the assistant's own instructions, so ordinary support
# text ("show me the instructions to reset my password", "اعرض إعدادات النظام") never matches.
_OVERRIDE_RE = _compile(
    r"\b(?:ignore|disregard|forget|override|bypass)\b[^.!?\n]{0,30}?"
    r"\b(?:previous|prior|earlier|above|all|your)\b[^.!?\n]{0,30}?"
    r"\b(?:instructions?|rules?|prompt|guidelines?)\b",
    r"\b(?:system|developer|hidden|secret)\s+(?:prompt|instructions?)\b",
    r"\b(?:reveal|print|show|repeat|output|display|leak)\b[^.!?\n]{0,30}?\b(?:initial|original)\s+prompt\b",
    r"تجاهل(?:ي)?\s+(?:كل\s+|جميع\s+)?(?:التعليمات|الأوامر|الاوامر|القواعد)",
    r"(?:اطبع|اعرض|أظهر|اظهر|كرر|اكشف)[^.!?\n]{0,25}(?:التعليمات|البرومبت|موجه النظام|رسالة النظام)",
    r"(?:تعليمات|موجه|رسالة)\s+النظام",
)


def is_instruction_override(message: str) -> bool:
    """True for an attempt to override the assistant's rules or to extract its prompt.

    Defence in depth next to the prompt's SECURITY BOUNDARY: a match is answered by a fixed refusal,
    never reaches the model and can never open a ticket (a flood of such messages must not become
    work for human agents). It is not a complete injection filter; the adversarial suite measures that.
    """
    return bool(_OVERRIDE_RE.search(normalize(message)))


def is_vague_issue(message: str) -> bool:
    """True when the message gives too little detail to act on."""
    cleaned = " ".join(re.sub(r"[^\w\s]", "", message.lower()).split())
    return cleaned in _VAGUE


@dataclass(frozen=True)
class Evidence:
    """What the customer has already told us about the router problem."""

    router_light: bool
    device_scope: bool
    restart_attempted: bool

    def missing(self) -> tuple[str, ...]:
        names = (
            ("router_light", self.router_light),
            ("device_scope", self.device_scope),
            ("restart", self.restart_attempted),
        )
        return tuple(name for name, present in names if not present)


def extract_evidence(customer_text: str) -> Evidence:
    text = normalize(customer_text)
    return Evidence(
        router_light=bool(_LIGHT_RE.search(text)),
        device_scope=bool(_SCOPE_RE.search(text)),
        restart_attempted=bool(_RESTART_RE.search(text)),
    )


@dataclass(frozen=True)
class AccountEvidence:
    """What the customer has already told us about an account / login problem."""

    error_message: bool
    reset_attempted: bool
    two_factor_known: bool

    def missing(self) -> tuple[str, ...]:
        names = (
            ("error_message", self.error_message),
            ("reset_attempted", self.reset_attempted),
            ("two_factor", self.two_factor_known),
        )
        return tuple(name for name, present in names if not present)


_ERROR_RE = re.compile(r"\berror\b|\bcode\b|خطأ|رسالة|رمز الخطأ")
_RESET_RE = re.compile(r"\breset\b|\bforgot|نسيت|إعادة تعيين|اعادة تعيين|أعدت تعيين|اعدت تعيين")
_TWO_FACTOR_RE = re.compile(r"\b2fa\b|\btwo-?factor\b|\bverification code\b|المصادقة|رمز التحقق")


def extract_account_evidence(customer_text: str) -> AccountEvidence:
    text = normalize(customer_text)
    return AccountEvidence(
        error_message=bool(_ERROR_RE.search(text)),
        reset_attempted=bool(_RESET_RE.search(text)),
        two_factor_known=bool(_TWO_FACTOR_RE.search(text)),
    )


def extract_topic_evidence(topic: str | None, customer_text: str):
    """Evidence tracker for a topic, or None when the topic has no deterministic follow-up."""
    if topic == "router":
        return extract_evidence(customer_text)
    if topic == "account":
        return extract_account_evidence(customer_text)
    return None
