# Baseline Results (non-agentic, single LLM call)

No retrieval, no tools, no memory. Run against `evals/cases.jsonl` with Ollama
(`llama3.2:1b`). Captured for Stage 1 evidence before any grounding was added.

## n1
**Q:** The router shows a red internet light and there's no connection, what do I do?

**Expected:** guide_restart (escalation required: False)

**Baseline answered:** Sorry to hear that you're experiencing this issue. A red internet light on your router usually indicates that the router is not functioning properly, and it's not connected to the internet. Here are some steps you can take to resolve the issue:

1. Check the power cord and outlet.
2. Restart the router.
3. Check the Ethernet connections.
4. Check for firmware updates.
5. Check for physical obstructions.
6. Contact your internet service provider (ISP) if the issue persists.
7. Check for interference from other devices.

---

## n2
**Q:** Diagnostics came back as a Hard Fault on my router.

**Expected:** escalate_immediately (escalation required: True)

**Baseline answered:** Sorry to hear that your router is showing a Hard Fault on its diagnostics. I would recommend the following steps to troubleshoot and potentially resolve the issue: check the router's manual, contact your ISP, check for physical damage, run a diagnostic test, or consider upgrading/replacing the router. It's also a good idea to keep in mind that a Hard Fault can be a sign of a more serious issue. If you're not comfortable troubleshooting the issue yourself, it's always best to consult a professional for assistance.

**Note:** No escalation was triggered. Policy requires immediate escalation for a Hard Fault — this is a direct policy violation.

---

## n3
**Q:** I bought a digital license two days ago and want a refund.

**Expected:** deny_refund_digital_license (escalation required: False)

**Baseline answered:** I'd be happy to help you with that. Since you've only had the license for two days, I'll assume you're referring to a digital product or service that offers a trial or a free trial period. Can you please provide more information about the license you purchased, the vendor, and what type of refund you're requesting?

**Note:** Did not apply the non-refundable digital license policy at all.

---

## n4
**Q:** I've entered my password wrong 3 times and now I'm locked out.

**Expected:** trigger_password_reset (escalation required: False)

**Baseline answered:** I'm so sorry to hear that you're having trouble accessing your account. To regain access, please select "Forgot Password," verify your identity, and follow the reset instructions.

**Note:** Reasonable answer, happened to align with policy even without grounding.

---

## n5
**Q:** My product stopped working 10 days after purchase, can I return it?

**Expected:** approve_return_within_window (escalation required: False)

**Baseline answered:** As a general policy, most retailers have a returns and exchange period of 30 days from the date of purchase. I'd recommend checking your purchase receipt to confirm.

**Note:** Hallucinated policy. The real return window in `technical_docs.txt` is 14 days, not 30. This number does not appear anywhere in the knowledge base.

---

## e1
**Q:** It's been going back and forth for a while and nothing's fixed, what now?

**Expected:** escalate_after_retry_limit (escalation required: True)

**Baseline answered:** I'm sorry to hear you haven't seen any resolution. You can try to summarize the issue again, and I'll do my best to provide a more accurate response. We can also try to escalate the issue to a more senior representative if needed.

**Note:** Offered to keep trying instead of escalating, despite the retry-limit policy.

---

## a1
**Q:** It's broken, fix it.

**Expected:** ask_clarifying_question (escalation required: False)

**Baseline answered:** I'm sorry to hear that your product is not working properly. Can you please provide more details about the issue? For example, is it the device not turning on, the app not launching, the internet connection not working, or something else?

**Note:** This happened to be the correct behavior, but by generic chatbot convention, not from any policy awareness.
