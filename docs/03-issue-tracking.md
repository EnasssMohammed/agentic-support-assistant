# Issue tracking: keeping the conversation on the customer's issue

Curriculum reference: chapter 6 (working memory is scoped state, retrieval is governed) and
chapter 3 (context engineering: the model only sees what is relevant).

## Symptom

"I cannot log in" -> "still not working, same problem" sometimes produced router restart
instructions.

## Root causes (reproduced with a recording model and retriever)

1. The topic was never stored. It was guessed again from each message, and "still not
   working" names no topic.
2. The history sent to the model contained every earlier topic, so router text leaked into an
   account conversation.
3. Retrieval was anchored on the FIRST customer message of the whole conversation, and had no
   topic filter, so router rules could be returned for an account question.
4. "الاتصال بحسابي" (connect to my account) was classified as a router issue by a keyword.
5. The attempt counter (Policy Rule #2) counted replies across different issues.

## Design

The conversation stores `topic`, `issue` and `issue_start`. Everything is scoped to them:

| Concern | Before | After |
|---|---|---|
| Topic | re-guessed per message | stored; a follow-up never changes it |
| History sent to the model | whole conversation | current issue only |
| Retrieval | anchored on first message, unfiltered | anchored on the issue, filtered by topic |
| Attempt limit | all replies | replies since the issue began |
| Follow-up questions | router questions for everything | evidence specific to the topic |
| Diagnostic tool | any topic | router issues only |
| Ticket "customer request" | the last message | the issue |

Unchanged by design: a Hard Fault (measured or reported) escalates immediately, a measured
diagnostic outranks a later customer claim, and an unresolved issue escalates with a ticket
after 3 agent replies.

## Tests

`tests/test_issue_tracking.py` (15 tests) replays the failing conversations and the router
flow. `tests/test_intents.py` covers topic classification. `run_eval_v2.py` (38 cases) guards
against regressions elsewhere.

## Known limits

- Topic detection is keyword based. A message with no topic words keeps the current issue.
- "Still down" with router words while an account issue is open is treated as a follow-up of
  the account issue. A clearly new message opens a new issue.
