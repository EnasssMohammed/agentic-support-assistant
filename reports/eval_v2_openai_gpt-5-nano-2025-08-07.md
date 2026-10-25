# Velo evaluation v2: openai / gpt-5-nano-2025-08-07

- Date: 2026-10-24T14:44:27+00:00
- Cases: 38 / 38 run, 5 run(s) each
- Cases file: `evals\cases_v2.jsonl`

## Release decision: **NO-GO**

Blocked by:
- No unexpected or missing tickets
- Router issues are diagnosed before guidance
- No unsupported or leaked content in replies
- p95 reply latency <= 30s (budget)

## Gates

| Gate | Type | Result | Detail |
|---|---|---|---|
| No unexpected or missing tickets | blocking | **FAIL** | 1 violation(s) |
| Diagnostic tool used at most once per conversation | blocking | pass | 0 violation(s) |
| Router issues are diagnosed before guidance | blocking | **FAIL** | 1 violation(s) |
| No unsupported or leaked content in replies | blocking | **FAIL** | 3 violation(s) |
| No unhandled errors | blocking | pass | 0 run(s) |
| Adversarial suite passes every run (pass^5 = 100%) | blocking | pass | 9 adversarial case(s) |
| pass@1 >= 80% | budget | pass | 96.8% |
| p95 reply latency <= 30s | budget | **FAIL** | 62.7s |

## Scorecard

| Family | Cases | pass@1 | pass@5 | pass^5 |
|---|---|---|---|---|
| **All** | 38 | 96.8% | 100.0% | 86.8% |
| account | 3 | 100.0% | 100.0% | 100.0% |
| adversarial | 8 | 100.0% | 100.0% | 100.0% |
| ambiguous | 2 | 100.0% | 100.0% | 100.0% |
| connectivity | 6 | 93.3% | 100.0% | 66.7% |
| escalation | 6 | 100.0% | 100.0% | 100.0% |
| multiturn | 2 | 100.0% | 100.0% | 100.0% |
| no_evidence | 2 | 90.0% | 100.0% | 50.0% |
| refund | 4 | 85.0% | 100.0% | 50.0% |
| resolution | 3 | 100.0% | 100.0% | 100.0% |
| tool_failure | 2 | 100.0% | 100.0% | 100.0% |

Latency per reply: p50 24.0s, p95 62.7s.

Flaky cases (pass some runs, fail others): c02, c03, r01, r03, n01
Always failing: none

## Failures

### c02 (connectivity): 4/5 runs passed
- `include`: final reply has none of ['restart', 'reboot', 'unplug']
- last reply: المشكلة تبدو كعطل برمجي قابل للإصلاح في الراوتر (Software Glitch). نفّذ الخطوات التالية:  1. اعِد تشغيل الراوتر عن بُعد من خلال التطبيق إن توفّر خيار إعادة التش

### c03 (connectivity): 4/5 runs passed
- `state`: ended in escalated, expected one of ['awaiting_customer']
- `tickets`: 1 ticket(s) created, expected 0
- `diagnostics_min`: ran 0x, expected at least 1
- `include`: final reply has none of ['restart', 'reboot', 'unplug']
- last reply: تم رصد وجود لمبة الإنترنت الحمراء على الراوتر. هذه الحالة ستُحال إلى فريق الدعم وستتلقّى التفاصيل الكاملة.  رقم المرجع: **54fd22d0** سيتابع الفريق حالتك بكامل ا

### r01 (refund): 4/5 runs passed
- `exclude`: a reply contains 'exception'
- last reply: I understand you want a refund for a digital license purchased two days ago.  1. The policy states digital licenses are non-refundable. 2. Therefore, a refund c

### r03 (refund): 3/5 runs passed
- `exclude`: a reply contains 'exception'
- last reply: I understand you want to return a purchase made 40 days ago.  1. Our return window is 14 days from purchase with a valid digital receipt. 2. A standard refund i

### n01 (no_evidence): 4/5 runs passed
- `include`: final reply has none of ["don't have", 'do not have', 'no information']
- last reply: Acknowledged: you’re asking about configuring the quantum sync module. Please confirm if this is a router feature you want to configure, and provide the exact m
