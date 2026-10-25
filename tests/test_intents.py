import pytest

from src.intents import (
    customer_confirms_resolution,
    customer_reports_unresolved,
    extract_evidence,
    is_vague_issue,
)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("it works now", True),
        ("the internet is back", True),
        ("تم الحل، الإنترنت اشتغل", True),
        ("it's not working", False),
        ("no, the problem is still there", False),
        ("ما اشتغل", False),
        ("لم يشتغل", False),
        ("ما زالت المشكلة", False),
    ],
)
def test_confirmation_is_never_fooled_by_negation(text, expected):
    assert customer_confirms_resolution(text) is expected


def test_unresolved_detection():
    assert customer_reports_unresolved("نفس المشكلة")
    assert customer_reports_unresolved("that didn't help")
    assert not customer_reports_unresolved("شكراً")


def test_evidence_tracks_what_is_missing():
    complete = extract_evidence("the light is red on all devices, I restarted it")
    assert complete.missing() == ()
    assert extract_evidence("hello").missing() == ("router_light", "device_scope", "restart")


def test_vague_issue():
    assert is_vague_issue("Help!")
    assert not is_vague_issue("my router light is red")


@pytest.mark.parametrize(
    "text,expected",
    [
        ("الإنترنت منقطع عندي بالكامل", True),
        ("لمبة الإنترنت في الراوتر حمراء", True),
        ("الاتصال بطيء ويتقطع", True),
        ("my router has no internet", True),
        ("لا أستطيع تسجيل الدخول إلى حسابي", False),
        ("I was charged twice and need a refund", False),
    ],
)
def test_router_topic_detection(text, expected):
    from src.intents import is_router_topic

    assert is_router_topic(text) is expected


@pytest.mark.parametrize(
    "text,topic",
    [
        ("الإنترنت منقطع عندي بالكامل", "router"),
        ("لمبة الإنترنت في الراوتر حمراء", "router"),
        ("الاتصال بطيء ويتقطع", "router"),
        ("My router has no internet.", "router"),
        ("لا أستطيع تسجيل الدخول إلى حسابي", "account"),
        ("لا أستطيع الاتصال بحسابي", "account"),          # "connect" + account = account issue
        ("I can't connect to my account", "account"),
        ("أدخلت كلمة المرور خطأ ثلاث مرات والحساب مقفل", "account"),
        ("I bought a digital license two days ago and want a refund.", "billing"),
        ("اشتريت رخصة رقمية قبل يومين وأريد استرجاع المبلغ", "billing"),
        ("ساعدني", "other"),
        ("ما زالت المشكلة قائمة، نفس المشكلة", "other"),
    ],
)
def test_topic_classification(text, topic):
    from src.intents import classify_topic

    assert classify_topic(text) == topic


def test_account_evidence_and_topic_filter():
    from src.intents import extract_account_evidence, topic_compatible

    assert extract_account_evidence("hello").missing() == ("error_message", "reset_attempted", "two_factor")
    full = extract_account_evidence("الخطأ يقول كذا، جربت نسيت كلمة المرور، ولا أستخدم المصادقة الثنائية")
    assert full.missing() == ()
    assert topic_compatible("general", "account") and topic_compatible("account", "account")
    assert not topic_compatible("router", "account")
    assert topic_compatible("router", None)               # unknown topic: nothing is filtered
