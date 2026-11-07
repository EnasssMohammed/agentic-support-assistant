# Knowledge Management Studio

The Studio is the page in the Velo app where staff upload, write, review, publish, version and audit the policies the
agent answers from. Open it from Home (Knowledge Management Studio) or the sidebar.

```
uv run streamlit run app.py
```

## Why it is built with controls

The agent obeys what its knowledge base says. A way to change the knowledge base is therefore a way to change the
agent's behaviour, and the held-out evaluation measured it: a poisoned passage that reads like a policy was obeyed in
5 of 5 runs (`h01`, see `02-evaluation-v2.md`). Nothing in the agent can tell a malicious policy from a real one, so
the defence has to sit on the write path. Every publish goes through the same pipeline:

```
review -> archive the previous version -> write atomically -> index the new knowledge base -> audit
              any failure at any step restores everything that was there before
```

## What a document must satisfy

| Check | Result |
|---|---|
| `.txt` or `.md`, at most 512 KB, at most 50 documents, valid UTF-8 text, not empty or binary | Blocks |
| File name: the directory part is dropped, only letters, digits, `._-`; no hidden or reserved names; cannot shadow the built-in manual | Blocks |
| Hidden text-direction control characters (can disguise text) | Blocks |
| A line that tells the assistant to ignore or reveal its rules | Blocks, with the line number |
| Links, image markup, HTML tags, invisible zero-width characters | Warns: tick "I read every warning" |
| Claims to override other rules, or pre-approves requests | Warns: same |
| A rule number (`Rule #2`) or entry title already defined in another document | Warns |
| No headings found (the text will be cut into fixed-size pieces) | Warns |

Every one of the four poisoned passages used in the held-out suite is either blocked or needs acknowledgement
(`tests/test_knowledge.py`). A review is not a proof of safety: it removes the obvious cases and makes a person look at
the rest.

## What the Studio does

- **Library**: the built-in manual (read-only, changed through a pull request) and every published document, with
  preview, earlier versions (restore) and delete. Nothing is ever lost: replaced and deleted documents stay in
  `knowledge/history/`.
- **Upload**: several files at once, each reviewed on its own. A batch is published together or not at all.
- **Write**: write or edit a policy in the page, with the same review. A template shows the heading format.
- **Try it**: ask a question and see which passages Velo would read (source, topic, distance).
- **Activity**: who changed what and when, with the document hash and the knowledge-base version.

Publishing builds the index before the change goes live. If the embedding service is unreachable, the publish is
undone and the previous knowledge base keeps answering. The next customer message after a publish is answered by an agent
built on the new version, without restarting the app.

## Access

There is no user authentication. Set `VELO_STUDIO_PIN` in `.env` to protect the page with a PIN; without it the page
shows a warning that anyone who can open the app can change the policies. The name typed in the Studio is recorded in
the activity log but is not verified. Do not expose the app beyond a supervised demo without real authentication.

## Write only what Velo can do

The agent will repeat what a policy says. The three policy files in `data/` describe human and operational processes, and
some of them disagree with what the agent actually does:

| In the document | In the agent |
|---|---|
| `Escalation_Rules_And_Limits.md`: Rule #2 escalates after more than two attempts | The code escalates after three agent replies (the built-in manual says three turns) |
| Same file: Rule #3 escalates when the customer has an open ticket from the last 24 hours | Not implemented |
| `Network_Troubleshooting_Guide.md`: send a "Port Soft Reset" from the server | The agent has no such tool |
| `Account_And_Billing_Policy.txt`: a replacement device is delivered within 48 hours | The agent can only create a ticket; a person arranges it |

The review flags the Rule #1 and Rule #2 overlaps. For the rest, describe the process as handled by "the support team"
rather than as something Velo does, or the agent will promise it.

## Evaluation after a change

The evaluation reports cover the built-in manual only. New policies change what Velo answers, so evidence must be
produced for the knowledge base that is live:

```
uv run python run_eval_v2.py --with-uploads --runs 5
```

Reports record `kb_sha256`, the hash of the exact files used, and `compare_arms.py` refuses to compare runs made
against different knowledge bases. The Studio shows the same version (first 12 characters) in its header and in the
activity log.

## Limits

- One process: files are replaced atomically, but two people publishing at the same moment are not coordinated.
- Text only: `.txt` and `.md`. Save Word or PDF files as UTF-8 text first.
- The activity log is a local file. It is not tamper-proof.
- The Studio state lives in `knowledge/` (gitignored) and is not part of the repository. Back it up separately.
