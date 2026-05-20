"""Structural chunker for RST docs and GitHub issues.

Strategy (defended in D-016):
  RST docs   — split at section headings (title line + underline of equal length).
               Headings are natural semantic boundaries; they preserve section
               context (section_title in metadata) and keep related code/prose
               together without an external NLP model.
  Issues     — body as chunk 0, each comment as its own chunk.
               GitHub issue threads are already naturally segmented: the OP
               states the problem, comments provide diagnosis/fix.

Sliding-window fallback (D-016):
  Any chunk exceeding MAX_TOKENS (220) is re-split with stride 170 (overlap 50).
  220-token cap leaves a 36-token margin inside MiniLM's 256-subword window,
  preventing silent truncation.  Stride 170 (50-token overlap) matches the
  "25% overlap" heuristic: enough cross-boundary context for BM25 term
  matching in Phase 3.3 without tripling chunk counts.  Compared to 200/30
  (same stride=170, smaller window): 220/50 captures 10% more context per
  chunk at the same chunk-count cost.

Issue comment cap (D-016):
  First 300 tokens of each comment are preserved; the rest is truncated.
  Assumption: the first paragraph of a maintainer comment contains the
  substantive answer — diagnosis, workaround, or pointer to a fix.
  Phase 3.4 eval will validate this assumption empirically.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import cast

from transformers import AutoTokenizer, PreTrainedTokenizerBase

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

# MiniLM max_seq_length = 256 subword tokens.  Leave 36-token margin.
MAX_TOKENS = 220
OVERLAP_TOKENS = 50
MAX_COMMENT_TOKENS = 300

_tokenizer: PreTrainedTokenizerBase | None = None

# RST underline characters defined by the Docutils specification.
_RST_UNDERLINE_CHARS = frozenset("=-~^_*+#")


def _get_tokenizer() -> PreTrainedTokenizerBase:
    global _tokenizer
    if _tokenizer is None:
        _tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    return _tokenizer


def count_tokens(text: str) -> int:
    """Return the number of subword tokens for text (no special tokens added)."""
    tok = _get_tokenizer()
    return len(tok.encode(text, add_special_tokens=False))


def truncate_to_tokens(text: str, max_tokens: int) -> str:
    """Return text truncated to at most max_tokens subword tokens."""
    tok = _get_tokenizer()
    ids = tok.encode(text, add_special_tokens=False)
    if len(ids) <= max_tokens:
        return text
    decoded = tok.decode(ids[:max_tokens], skip_special_tokens=True)
    return decoded if isinstance(decoded, str) else " ".join(decoded)


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------


@dataclass
class Chunk:
    source_type: str  # "doc" | "issue"
    source_id: str  # file_id for docs, str(number) for issues
    chunk_index: int
    text: str
    n_tokens: int
    metadata: dict[str, object] = field(default_factory=dict)

    @property
    def chunk_id(self) -> str:
        return f"{self.source_type}:{self.source_id}:{self.chunk_index}"


# ---------------------------------------------------------------------------
# RST heading detection
# ---------------------------------------------------------------------------


def _is_underline_for(title: str, candidate: str) -> bool:
    """True if candidate is an RST section underline for title."""
    if not candidate or not title:
        return False
    chars = set(candidate)
    return (
        len(chars) == 1
        and next(iter(chars)) in _RST_UNDERLINE_CHARS
        and len(candidate) >= len(title)
    )


def _split_rst_sections(text: str) -> list[tuple[str, str]]:
    """Split RST text at section headings.

    Returns a list of (section_title, body) pairs.  Text before the first
    heading is returned with an empty title.  Overline+title+underline
    patterns are handled naturally: only the title+underline pair triggers
    the split; the overline line falls into the previous section body.
    """
    lines = text.splitlines()

    # Collect (line_index_of_title, title_text) pairs.
    heading_positions: list[tuple[int, str]] = []
    for i in range(len(lines) - 1):
        curr = lines[i].rstrip()
        nxt = lines[i + 1].rstrip()
        # Skip blank titles and skip lines that are themselves underlines
        # (overline case: the underline line would also satisfy this check
        # against a subsequent non-underline-looking title, but the title
        # must not consist entirely of underline chars — that would mean
        # the "title" is an overline, not real heading text).
        if curr and nxt and _is_underline_for(curr, nxt):
            # Reject if curr itself looks like a pure underline line (overline).
            curr_chars = set(curr.replace(" ", ""))
            if len(curr_chars) == 1 and next(iter(curr_chars)) in _RST_UNDERLINE_CHARS:
                continue
            heading_positions.append((i, curr))

    if not heading_positions:
        return [("", text)]

    sections: list[tuple[str, str]] = []

    # Preamble: text before the first heading.
    first_pos = heading_positions[0][0]
    if first_pos > 0:
        preamble = "\n".join(lines[:first_pos]).strip()
        if preamble:
            sections.append(("", preamble))

    for k, (pos, title) in enumerate(heading_positions):
        content_start = pos + 2  # skip title line + underline line
        content_end = heading_positions[k + 1][0] if k + 1 < len(heading_positions) else len(lines)
        content = "\n".join(lines[content_start:content_end]).strip()
        sections.append((title, content))

    return [(t, b) for (t, b) in sections if t or b]


# ---------------------------------------------------------------------------
# Sliding-window fallback
# ---------------------------------------------------------------------------


def _sliding_window(text: str, section_title: str) -> list[dict[str, object]]:
    """Split text into overlapping windows of MAX_TOKENS with OVERLAP_TOKENS overlap.

    Stores n_tokens from the decoded text (not raw ID count) so that
    count_tokens(chunk.text) == chunk.n_tokens.  Trims one ID at a time if
    decode/re-encode produces > MAX_TOKENS due to tokenizer round-trip drift.
    """
    tok = _get_tokenizer()
    token_ids: list[int] = tok.encode(text, add_special_tokens=False)
    stride = MAX_TOKENS - OVERLAP_TOKENS
    windows: list[dict[str, object]] = []
    start = 0
    while start < len(token_ids):
        end = start + MAX_TOKENS
        chunk_ids = token_ids[start:end]
        # Trim from the end until the decoded text re-encodes within MAX_TOKENS.
        # In practice this loop runs 0-2 iterations (tokenizer round-trip drift).
        while chunk_ids:
            raw_text = tok.decode(chunk_ids, skip_special_tokens=True)
            chunk_text: str = raw_text if isinstance(raw_text, str) else " ".join(raw_text)
            n = count_tokens(chunk_text)
            if n <= MAX_TOKENS:
                break
            chunk_ids = chunk_ids[:-1]
        else:
            break
        windows.append(
            {
                "text": chunk_text,
                "n_tokens": n,
                "section_title": section_title,
                "window": True,
            }
        )
        if end >= len(token_ids):
            break
        start += stride
    return windows


# ---------------------------------------------------------------------------
# Public chunking functions
# ---------------------------------------------------------------------------


def chunk_doc(doc: dict[str, object]) -> list[Chunk]:
    """Chunk a single RST doc record from data/rag_corpus/docs/.

    One chunk per RST section.  Sections exceeding MAX_TOKENS fall back to
    sliding-window.  Empty sections are skipped.
    """
    raw_text = str(doc["raw_text"])
    file_id = str(doc["file_id"])
    sections = _split_rst_sections(raw_text)

    chunks: list[Chunk] = []
    idx = 0

    for title, body in sections:
        full_text = f"{title}\n{body}".strip() if title else body.strip()
        if not full_text:
            continue

        n = count_tokens(full_text)
        if n <= MAX_TOKENS:
            chunks.append(
                Chunk(
                    source_type="doc",
                    source_id=file_id,
                    chunk_index=idx,
                    text=full_text,
                    n_tokens=n,
                    metadata={"section_title": title},
                )
            )
            idx += 1
        else:
            for w in _sliding_window(full_text, title):
                chunks.append(
                    Chunk(
                        source_type="doc",
                        source_id=file_id,
                        chunk_index=idx,
                        text=str(w["text"]),
                        n_tokens=int(str(w["n_tokens"])),
                        metadata={
                            "section_title": str(w["section_title"]),
                            "window": True,
                        },
                    )
                )
                idx += 1

    return chunks


def chunk_issue(issue: dict[str, object]) -> list[Chunk]:
    """Chunk a single issue record from data/rag_corpus/issues/.

    Chunk 0: title + body (sliding-window if too long).
    Chunk 1+: each comment, truncated to MAX_COMMENT_TOKENS from the start.
    """
    number = str(issue["number"])
    issue_id = str(issue["issue_id"])
    title = str(issue.get("title") or "")
    body = str(issue.get("body") or "").strip()
    comments: list[dict[str, object]] = cast(list[dict[str, object]], issue.get("comments", []))

    chunks: list[Chunk] = []
    idx = 0

    # Body chunk(s)
    body_text = f"{title}\n{body}".strip() if body else title.strip()
    if body_text:
        n = count_tokens(body_text)
        if n <= MAX_TOKENS:
            chunks.append(
                Chunk(
                    source_type="issue",
                    source_id=number,
                    chunk_index=idx,
                    text=body_text,
                    n_tokens=n,
                    metadata={"section_title": "body", "issue_id": issue_id},
                )
            )
            idx += 1
        else:
            for w in _sliding_window(body_text, "body"):
                chunks.append(
                    Chunk(
                        source_type="issue",
                        source_id=number,
                        chunk_index=idx,
                        text=str(w["text"]),
                        n_tokens=int(str(w["n_tokens"])),
                        metadata={
                            "section_title": "body",
                            "issue_id": issue_id,
                            "window": True,
                        },
                    )
                )
                idx += 1

    # Comment chunks: first MAX_COMMENT_TOKENS tokens preserved.
    for comment in comments:
        comment_text = str(comment.get("body") or "").strip()
        if not comment_text:
            continue
        comment_text = truncate_to_tokens(comment_text, MAX_COMMENT_TOKENS)
        n = count_tokens(comment_text)
        chunks.append(
            Chunk(
                source_type="issue",
                source_id=number,
                chunk_index=idx,
                text=comment_text,
                n_tokens=n,
                metadata={
                    "section_title": f"comment_{idx}",
                    "issue_id": issue_id,
                },
            )
        )
        idx += 1

    return chunks


def _strip_rst_noise(text: str) -> str:
    """Remove RST directives, cross-references, and substitutions for cleaner text."""
    # Remove RST role markup: :role:`text` → text
    text = re.sub(r":[a-z_]+:`([^`]*)`", r"\1", text)
    # Remove standalone directives: .. directive:: args
    text = re.sub(r"\.\.\s+\w[^:\n]*::[^\n]*\n", "", text)
    return text
