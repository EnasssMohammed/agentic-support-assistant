"""
Knowledge Management Studio backend: review, publish, version, roll back and audit policy documents.

No Streamlit in here, so every rule is testable. The UI is a thin layer on top (ui/knowledge.py).

Why this is more than "save the file": the agent obeys whatever its knowledge base says, so a write path into
the knowledge base is a write path into the agent's behaviour (threat T3 in docs/06-threat-model.md). Every
publish therefore goes through the same pipeline:

    review (blocking problems, warnings that need acknowledgement)
      -> archive the previous version -> write atomically -> verify (the index must build)
      -> on any failure, restore everything -> append to the audit log

Layout (under VELO_KNOWLEDGE_DIR, default ./knowledge, gitignored):

    published/<name>             documents the agent answers from, next to the built-in manual
    history/<name>/<id><suffix>  every previous version, for rollback
    audit.jsonl                  one line per change: who, when, what, hash, note
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import unicodedata
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from langchain_text_splitters import RecursiveCharacterTextSplitter

from src.intents import is_instruction_override
from src.rag_engine import CHUNK_OVERLAP, CHUNK_SIZE, split_policy_entries, split_sections

BUILTIN = Path("data/technical_docs.txt")
ALLOWED_SUFFIXES = (".txt", ".md")
MAX_FILE_BYTES = 512 * 1024
MAX_DOCUMENTS = 50
MAX_NAME_LENGTH = 100
MAX_NOTE_LENGTH = 300

_RESERVED_NAMES = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}
_VERSION_ID_RE = re.compile(r"^\d{8}T\d{12}Z-[0-9a-f]{8}$")

# A hidden text-direction override can make text read differently from how it is stored ("Trojan Source").
_BIDI_CONTROL_RE = re.compile("[\u202a-\u202e\u2066-\u2069]")
# Zero-width characters are legitimate in Persian and Arabic shaping, so they warn instead of blocking.
_INVISIBLE_RE = re.compile("[\u200b-\u200d\u2060\ufeff]")
_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
_IMAGE_RE = re.compile(r"!\[[^\]]*\]\(")
_HTML_RE = re.compile(r"<\s*/?\s*(script|iframe|img|a|style|object|embed|form)\b", re.IGNORECASE)
# A policy states what is true. It does not rank itself above the other policies or approve things in advance:
# that is how a poisoned entry takes control of the agent (indirect injection, held-out case h01).
_AUTHORITY_RE = re.compile(
    r"\b(?:supersede[sd]?|overrid(?:e|es|ing)|takes?\s+precedence|replaces?\s+(?:all|any)\s+(?:earlier|previous|other))"
    r"\b[^.\n]{0,60}\b(?:rules?|polic(?:y|ies)|instructions?)\b"
    r"|(?:\u062a\u0644\u063a\u064a|\u062a\u062d\u0644\s+\u0645\u062d\u0644)[^.\n]{0,40}"
    r"(?:\u0627\u0644\u0642\u0648\u0627\u0639\u062f|\u0627\u0644\u0633\u064a\u0627\u0633\u0627\u062a|\u0627\u0644\u062a\u0639\u0644\u064a\u0645\u0627\u062a)",
    re.IGNORECASE)
_PREAPPROVAL_RE = re.compile(r"\b(?:pre-?approved|automatically\s+approved|always\s+approve|approve\s+(?:every|all|any))\b",
                             re.IGNORECASE)
_RULE_LABEL_RE = re.compile(r"\b(?:policy\s+)?rule\s*#\s*(\d+)\b|\u0627\u0644\u0642\u0627\u0639\u062f\u0629\s*#?\s*(\d+)",
                            re.IGNORECASE)
_ENTRY_TITLE_RE = re.compile(r"^-\s*\[(?P<title>[^\]]+)\]", re.MULTILINE)


class KnowledgeError(Exception):
    """A change was refused or had to be rolled back. The message is meant for the person using the Studio."""


# ----------------------------------------------------------------------------------------- helpers

def knowledge_version(files: Iterable[Path]) -> str:
    """One hash for a set of knowledge files: names and content, with line endings normalised."""
    digest = hashlib.sha256()
    for path in sorted((Path(f) for f in files), key=lambda p: p.name):
        digest.update(path.name.encode() + b"\0" + path.read_bytes().replace(b"\r\n", b"\n") + b"\0")
    return digest.hexdigest()


def pin_required() -> bool:
    return bool(os.getenv("VELO_STUDIO_PIN", ""))


def check_pin(entered: str) -> bool:
    """True when no PIN is configured, or the entered one matches (constant-time comparison)."""
    expected = os.getenv("VELO_STUDIO_PIN", "")
    return not expected or hmac.compare_digest(entered.encode(), expected.encode())


def clean_name(raw: str) -> tuple[str, list[str], list[str]]:
    """(safe name, problems, warnings) for an uploaded file name. Never trusts the directory part."""
    problems: list[str] = []
    warnings: list[str] = []
    base = re.split(r"[\\/]", raw.strip())[-1]
    name = re.sub(r"\s+", "_", unicodedata.normalize("NFC", base))
    name = "".join(ch if (ch.isalnum() or ch in "._-") else "_" for ch in name)
    if name != base:
        warnings.append(f'The file name was changed from "{base}" to "{name}".')
    stem, suffix = os.path.splitext(name)
    if not stem or name.startswith("."):
        problems.append("The file name is empty or starts with a dot.")
    if suffix.lower() not in ALLOWED_SUFFIXES:
        problems.append(f"Only {', '.join(ALLOWED_SUFFIXES)} files are accepted (this one is \"{suffix or 'no extension'}\").")
    else:
        name = stem + suffix.lower()
    if len(name) > MAX_NAME_LENGTH:
        problems.append(f"The file name is longer than {MAX_NAME_LENGTH} characters.")
    if stem.lower() in _RESERVED_NAMES:
        problems.append(f'"{stem}" is a reserved name on Windows.')
    if name == BUILTIN.name:
        problems.append(f"{BUILTIN.name} is the built-in manual. It is changed through a pull request, not here.")
    return name, problems, warnings


def rule_labels(text: str) -> set[str]:
    """'Rule #2' style labels in a document, so two documents defining the same rule can be flagged."""
    return {f"Rule #{a or b}" for a, b in _RULE_LABEL_RE.findall(text)}


def entry_titles(text: str) -> set[str]:
    return {m.group("title").strip().lower() for m in _ENTRY_TITLE_RE.finditer(text)}


def analyse(text: str) -> tuple[str, int]:
    """(structure, chunk count) exactly as the knowledge base will split the text."""
    entries = split_policy_entries(text)
    if entries:
        return "entries", len(entries)
    sections = split_sections(text)
    if sections:
        return "sections", len(sections)
    pieces = RecursiveCharacterTextSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP).split_text(text)
    return "plain", len(pieces)


def _stamp(now: datetime) -> str:
    return now.strftime("%Y%m%dT%H%M%S%f") + "Z"


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


# ------------------------------------------------------------------------------------------ records

@dataclass
class Review:
    """What the Studio shows before anything is published."""

    name: str
    text: str = ""
    sha256: str = ""
    size: int = 0
    structure: str = ""
    entries: int = 0
    replaces: bool = False
    problems: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems


@dataclass(frozen=True)
class DocInfo:
    name: str
    size: int
    sha256: str
    modified: str
    structure: str
    entries: int
    versions: int
    builtin: bool = False


@dataclass(frozen=True)
class Version:
    id: str
    size: int
    sha256: str
    saved: str


# ------------------------------------------------------------------------------------------- store

class KnowledgeStore:
    def __init__(self, root: str | Path | None = None, builtin: str | Path = BUILTIN,
                 clock: Callable[[], datetime] | None = None):
        self.root = Path(root or os.getenv("VELO_KNOWLEDGE_DIR", "knowledge"))
        self.builtin = Path(builtin)
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    # --- layout
    @property
    def published_dir(self) -> Path:
        return self.root / "published"

    @property
    def history_dir(self) -> Path:
        return self.root / "history"

    @property
    def audit_path(self) -> Path:
        return self.root / "audit.jsonl"

    def _path(self, name: str) -> Path:
        safe, problems, _ = clean_name(name)
        if problems or safe != name:
            raise KnowledgeError(f'"{name}" is not a valid document name.')
        return self.published_dir / safe

    # --- reading
    def files(self) -> list[Path]:
        """The knowledge base the agent answers from: the built-in manual plus every published document."""
        found = [self.builtin] if self.builtin.exists() else []
        if self.published_dir.is_dir():
            found += sorted(p for p in self.published_dir.iterdir() if p.is_file() and not p.name.startswith("."))
        return found

    def version(self) -> str:
        return knowledge_version(self.files())

    def _info(self, path: Path, builtin: bool = False) -> DocInfo:
        data = path.read_bytes()
        structure, count = analyse(data.decode("utf-8", errors="replace"))
        modified = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(timespec="seconds")
        versions = 0 if builtin else len(self.versions(path.name))
        return DocInfo(path.name, len(data), hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest(),
                       modified, structure, count, versions, builtin)

    def builtin_info(self) -> DocInfo | None:
        return self._info(self.builtin, builtin=True) if self.builtin.exists() else None

    def documents(self) -> list[DocInfo]:
        if not self.published_dir.is_dir():
            return []
        return [self._info(p) for p in sorted(self.published_dir.iterdir())
                if p.is_file() and not p.name.startswith(".")]

    def read(self, name: str) -> str:
        path = self._path(name)
        if not path.exists():
            raise KnowledgeError(f'"{name}" is not published.')
        return path.read_text(encoding="utf-8")

    def _other_texts(self, exclude: str | None = None) -> dict[str, str]:
        return {p.name: p.read_text(encoding="utf-8", errors="replace")
                for p in self.files() if p.name != exclude}

    # --- review
    def review(self, raw_name: str, data: bytes) -> Review:
        name, problems, warnings = clean_name(raw_name)
        review = Review(name=name, size=len(data), problems=problems, warnings=warnings)
        review.replaces = (self.published_dir / name).exists()

        if not data:
            review.problems.append("The file is empty.")
            return review
        if len(data) > MAX_FILE_BYTES:
            review.problems.append(f"The file is larger than {MAX_FILE_BYTES // 1024} KB.")
            return review
        if b"\0" in data:
            review.problems.append("This looks like a binary file, not text.")
            return review
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            review.problems.append("The file is not UTF-8. Save it as UTF-8 text (in Word or Notepad: Save As, "
                                   "Encoding: UTF-8) and upload it again.")
            return review

        text = text.replace("\r\n", "\n").replace("\r", "\n")
        review.text = text
        review.sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if not text.strip():
            review.problems.append("The file has no text.")
            return review

        if _BIDI_CONTROL_RE.search(text):
            review.problems.append("The text contains hidden text-direction control characters, which can make "
                                   "text read differently from how it is stored. Remove them.")
        flagged = [i for i, line in enumerate(text.splitlines(), 1) if is_instruction_override(line)]
        for line_no in flagged[:3]:
            review.problems.append(f"Line {line_no} reads like an instruction to the assistant to ignore or reveal "
                                   "its rules. A policy describes rules; it never overrides them. Reword it.")
        if len(flagged) > 3:
            review.problems.append(f"{len(flagged) - 3} more lines like that.")

        if (count := len(_URL_RE.findall(text))):
            review.warnings.append(f"Contains {count} link(s). The agent may repeat them to customers: check each one.")
        if _IMAGE_RE.search(text):
            review.warnings.append("Contains image markup, which can be used to send data to another site.")
        if _HTML_RE.search(text):
            review.warnings.append("Contains HTML tags (script, link, image or form).")
        if _AUTHORITY_RE.search(text):
            review.warnings.append("Claims to override or outrank other rules (for example 'supersedes all earlier "
                                   "rules'). A policy should say what is true, not rank itself above the others.")
        if _PREAPPROVAL_RE.search(text):
            review.warnings.append("Pre-approves requests ('pre-approved', 'approve every ...'). Velo cannot approve "
                                   "anything; a person decides approvals.")
        if _INVISIBLE_RE.search(text):
            review.warnings.append("Contains invisible zero-width characters. Fine in Arabic or Persian text, "
                                   "suspicious anywhere else.")

        review.structure, review.entries = analyse(text)
        if review.structure == "plain":
            review.warnings.append("No headings or '- [Entry]:' items were found, so the text will be cut into "
                                   "fixed-size pieces that can split a rule in half. Add numbered or markdown "
                                   "headings for better answers.")

        others = self._other_texts(exclude=name)
        labels = rule_labels(text)
        for label in sorted(labels):
            owners = [n for n, t in others.items() if label in rule_labels(t)]
            if owners:
                review.warnings.append(f'Defines "{label}", which is also defined in {", ".join(owners)}. If the '
                                       "wording differs, the agent may answer either way. Align them first.")
        titles = entry_titles(text)
        for other_name, other_text in others.items():
            shared = titles & entry_titles(other_text)
            if shared:
                review.warnings.append(f'Entry title(s) also in {other_name}: {", ".join(sorted(shared))}.')

        if not review.replaces and len(list(self.published_dir.glob("*"))) >= MAX_DOCUMENTS:
            review.problems.append(f"The Studio holds at most {MAX_DOCUMENTS} documents.")
        return review

    # --- changing
    def publish_many(self, items: list[tuple[str, bytes]], author: str, note: str = "",
                     acknowledged: bool = False,
                     verify: Callable[[list[Path]], None] | None = None) -> list[Review]:
        """Publish documents together or not at all. `verify` receives the new file list and must raise if the
        knowledge base cannot be built from it; everything is then restored."""
        author, note = self._who(author, note)
        if not items:
            raise KnowledgeError("Nothing to publish.")
        reviews = [self.review(raw_name, data) for raw_name, data in items]
        names = [r.name for r in reviews]
        if len(set(names)) != len(names):
            raise KnowledgeError("Two files in this batch have the same name.")
        blocked = [f"{r.name}: {p}" for r in reviews for p in r.problems]
        if blocked:
            raise KnowledgeError("Not published. " + " ".join(blocked))
        if any(r.warnings for r in reviews) and not acknowledged:
            raise KnowledgeError("Read every warning and tick the box to confirm, then publish again.")

        previous = {r.name: (self.published_dir / r.name).read_bytes() if r.replaces else None for r in reviews}
        archived: list[Path] = []
        try:
            for r in reviews:
                if previous[r.name] is not None:
                    archived.append(self._archive(r.name, previous[r.name]))
                _atomic_write(self.published_dir / r.name, r.text.encode("utf-8"))
            if verify:
                verify(self.files())
        except Exception as exc:
            self._restore_files(previous)
            for path in archived:                       # the undone change leaves no phantom version behind
                path.unlink(missing_ok=True)
            self._audit("rolled_back", names, author, f"{type(exc).__name__}: {exc}"[:MAX_NOTE_LENGTH])
            raise KnowledgeError(f"Publishing failed and every change was undone ({type(exc).__name__}: {exc}).") from exc

        for r in reviews:
            self._audit("update" if previous[r.name] is not None else "create", [r.name], author, note,
                        sha256=r.sha256, size=len(r.text.encode("utf-8")), acknowledged=bool(r.warnings),
                        warnings=r.warnings)
        return reviews

    def delete(self, name: str, author: str, note: str = "",
               verify: Callable[[list[Path]], None] | None = None) -> None:
        author, note = self._who(author, note)
        path = self._path(name)
        if not path.exists():
            raise KnowledgeError(f'"{name}" is not published.')
        data = path.read_bytes()
        archived = self._archive(name, data)
        path.unlink()
        try:
            if verify:
                verify(self.files())
        except Exception as exc:
            _atomic_write(path, data)
            archived.unlink(missing_ok=True)
            self._audit("rolled_back", [name], author, f"{type(exc).__name__}: {exc}"[:MAX_NOTE_LENGTH])
            raise KnowledgeError(f"Deleting failed and was undone ({type(exc).__name__}: {exc}).") from exc
        self._audit("delete", [name], author, note, sha256=hashlib.sha256(data).hexdigest(), size=len(data))

    def versions(self, name: str) -> list[Version]:
        folder = self.history_dir / name
        if not folder.is_dir():
            return []
        found = []
        for path in folder.iterdir():
            if path.is_file() and _VERSION_ID_RE.match(path.stem):
                data = path.read_bytes()
                found.append(Version(path.stem, len(data), hashlib.sha256(data).hexdigest(), path.stem[:16]))
        return sorted(found, key=lambda v: v.id, reverse=True)

    def restore(self, name: str, version_id: str, author: str, note: str = "", acknowledged: bool = False,
                verify: Callable[[list[Path]], None] | None = None) -> Review:
        if not _VERSION_ID_RE.match(version_id):
            raise KnowledgeError("Unknown version.")
        suffix = os.path.splitext(name)[1]
        path = self.history_dir / name / f"{version_id}{suffix}"
        if not path.is_file():
            raise KnowledgeError("That version no longer exists.")
        label = note or f"restored version {version_id}"
        return self.publish_many([(name, path.read_bytes())], author, label, acknowledged, verify)[0]

    # --- audit
    def audit(self, limit: int = 200) -> list[dict]:
        if not self.audit_path.exists():
            return []
        rows = []
        for line in self.audit_path.read_text(encoding="utf-8").splitlines():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return rows[::-1][:limit]

    def _audit(self, action: str, documents: list[str], author: str, note: str, **extra) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        entry = {"time": self._clock().isoformat(timespec="seconds"), "action": action,
                 "documents": documents, "author": author, "note": note, "kb_version": self.version()[:12], **extra}
        with self.audit_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # --- internals
    @staticmethod
    def _who(author: str, note: str) -> tuple[str, str]:
        author, note = author.strip(), note.strip()
        if not 2 <= len(author) <= 60 or re.search(r"[\x00-\x1f]", author):
            raise KnowledgeError("Enter your name (2 to 60 characters). It is recorded in the activity log.")
        if len(note) > MAX_NOTE_LENGTH:
            raise KnowledgeError(f"The note is longer than {MAX_NOTE_LENGTH} characters.")
        return author, note

    def _archive(self, name: str, data: bytes) -> Path:
        suffix = os.path.splitext(name)[1]
        version_id = f"{_stamp(self._clock())}-{hashlib.sha256(data).hexdigest()[:8]}"
        path = self.history_dir / name / f"{version_id}{suffix}"
        _atomic_write(path, data)
        return path

    def _restore_files(self, previous: dict[str, bytes | None]) -> None:
        for name, data in previous.items():
            path = self.published_dir / name
            if data is None:
                path.unlink(missing_ok=True)
            else:
                _atomic_write(path, data)
