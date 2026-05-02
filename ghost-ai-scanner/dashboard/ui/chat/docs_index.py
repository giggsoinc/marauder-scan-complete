# =============================================================
# FILE: dashboard/ui/chat/docs_index.py
# VERSION: 1.0.0
# UPDATED: 2026-05-02
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: BM25-backed retrieval over PatronAI's HTML + Markdown
#          docs. Loaded once at first call (lazy), kept in memory for
#          process lifetime. Powers `get_help(query=...)` so the chat
#          can answer "how do I install the Linux agent / uninstall on
#          Mac / what is the rollup architecture" from real docs
#          rather than hallucinating.
#
#          Pure stdlib + rank_bm25 (one tiny dep, no native libs).
#          No embeddings, no vector DB, no external services.
# DEPENDS: rank_bm25 (>=0.2.2), html.parser (stdlib)
# =============================================================

from __future__ import annotations

import logging
import os
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Optional

log = logging.getLogger("patronai.chat.docs_index")

# Roots where docs live. First match wins per relative path. Archive
# included so historic guides (e.g. Mac agent uninstall) stay reachable.
_DOC_ROOTS = [
    Path(__file__).resolve().parents[4] / "ghost-ai-scanner" / "docs",
    Path(__file__).resolve().parents[4] / "docs",
]
_ALLOWED_EXT = {".md", ".html", ".htm"}
_MAX_CHUNK_CHARS = 1500   # ~300-400 tokens per chunk
_MAX_CHUNKS_PER_DOC = 50  # safety cap on pathological docs
_MIN_CHUNK_CHARS = 80     # drop chunks shorter than this (header noise, etc.)
_TOPK_DEFAULT = 3
_BM25_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_+\-./]*")


# ── HTML → text ──────────────────────────────────────────────────


class _HTMLStripper(HTMLParser):
    """Minimal HTML→text converter. Drops <script>, <style>; preserves
    paragraph boundaries; collapses whitespace."""

    # Tags whose CONTENT we drop. Must NOT include void elements
    # (<meta>, <link>, <br>) because handle_starttag fires for them but
    # handle_endtag does not — that would leak skip_depth and silently
    # blackhole the whole body. Void elements have no content anyway, so
    # they don't need to be in this list.
    _DROP_TAGS = {"script", "style", "noscript"}
    _BLOCK_TAGS = {"p", "div", "section", "article", "header", "footer",
                   "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6",
                   "br", "pre", "blockquote", "table"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in self._DROP_TAGS:
            self.skip_depth += 1
        if tag in self._BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self._DROP_TAGS and self.skip_depth > 0:
            self.skip_depth -= 1
        if tag in self._BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data):
        if self.skip_depth == 0:
            self.parts.append(data)

    def text(self) -> str:
        out = "".join(self.parts)
        out = re.sub(r"[ \t]+", " ", out)
        out = re.sub(r"\n{3,}", "\n\n", out)
        return out.strip()


def _html_to_text(html: str) -> str:
    parser = _HTMLStripper()
    try:
        parser.feed(html)
        return parser.text()
    except Exception as exc:
        log.warning("HTML parse failed: %s", exc)
        return ""


# ── Chunking ─────────────────────────────────────────────────────


def _chunks(text: str) -> list[str]:
    """Split on blank lines, glue small adjacent paragraphs up to the
    char cap, drop micro-chunks. Preserves rough section structure so
    BM25 hits return self-contained passages."""
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    buf = ""
    for p in paragraphs:
        candidate = (buf + "\n\n" + p) if buf else p
        if len(candidate) <= _MAX_CHUNK_CHARS:
            buf = candidate
        else:
            if buf:
                chunks.append(buf)
            buf = p[:_MAX_CHUNK_CHARS]
        if len(chunks) >= _MAX_CHUNKS_PER_DOC:
            break
    if buf:
        chunks.append(buf)
    return [c for c in chunks if len(c) >= _MIN_CHUNK_CHARS]


# ── Tokenisation ─────────────────────────────────────────────────


def _tokenise(text: str) -> list[str]:
    """Lowercase, alphanumeric + a few punctuation chars (so 'github.copilot'
    stays one token). Stop-word list deliberately small — product docs are
    short, every word can carry signal."""
    return [t.lower() for t in _BM25_TOKEN_RE.findall(text)]


# ── Index ────────────────────────────────────────────────────────


class DocsIndex:
    """In-memory BM25 over HTML+MD docs. One instance per process.
    Idempotent rebuild via load(); lazy on first query."""

    def __init__(self) -> None:
        self.chunks: list[dict] = []   # [{path, title, text, tokens}]
        self.bm25 = None               # rank_bm25.BM25Okapi
        self._loaded = False

    # ── Loading ─────────────────────────────────────────────────

    def _walk(self) -> list[Path]:
        out: list[Path] = []
        seen: set[str] = set()
        for root in _DOC_ROOTS:
            if not root.exists():
                continue
            for p in root.rglob("*"):
                if not p.is_file() or p.suffix.lower() not in _ALLOWED_EXT:
                    continue
                # Dedup across root variants (worktree + main checkout).
                rel = str(p.relative_to(root))
                if rel in seen:
                    continue
                seen.add(rel)
                out.append(p)
        return out

    def _read_one(self, path: Path) -> Optional[str]:
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            log.warning("docs_index: failed to read %s: %s", path, exc)
            return None
        if path.suffix.lower() in (".html", ".htm"):
            return _html_to_text(raw)
        return raw

    def _title_for(self, path: Path, text: str) -> str:
        """First markdown heading or HTML <title>-equivalent first line."""
        for line in text.splitlines():
            line = line.strip(" #").strip()
            if line:
                return line[:120]
        return path.name

    def load(self) -> int:
        """(Re)build the index. Returns chunk count."""
        try:
            from rank_bm25 import BM25Okapi
        except ImportError:
            log.error("docs_index: rank_bm25 not installed — RAG disabled")
            self._loaded = False
            return 0

        self.chunks = []
        for path in self._walk():
            text = self._read_one(path)
            if not text:
                continue
            title = self._title_for(path, text)
            for chunk in _chunks(text):
                self.chunks.append({
                    "path": str(path.name),
                    "title": title,
                    "text": chunk,
                    "tokens": _tokenise(chunk),
                })
        if not self.chunks:
            log.warning("docs_index: no docs indexed")
            self.bm25 = None
            self._loaded = True
            return 0
        self.bm25 = BM25Okapi([c["tokens"] for c in self.chunks])
        self._loaded = True
        log.info("docs_index: %d chunks across %d files",
                 len(self.chunks),
                 len({c["path"] for c in self.chunks}))
        return len(self.chunks)

    # ── Query ───────────────────────────────────────────────────

    def query(self, q: str, top_k: int = _TOPK_DEFAULT) -> list[dict]:
        """Return top_k chunks for the query, sorted by BM25 score."""
        if not self._loaded:
            self.load()
        if not self.bm25 or not q.strip():
            return []
        tokens = _tokenise(q)
        if not tokens:
            return []
        scores = self.bm25.get_scores(tokens)
        ranked = sorted(enumerate(scores), key=lambda kv: kv[1], reverse=True)
        out: list[dict] = []
        for idx, score in ranked[:max(1, int(top_k))]:
            if score <= 0:
                continue
            c = self.chunks[idx]
            out.append({
                "score": round(float(score), 3),
                "source": c["path"],
                "title": c["title"],
                "text": c["text"],
            })
        return out


# ── Module-level singleton ──────────────────────────────────────


_INDEX: Optional[DocsIndex] = None


def get_index() -> DocsIndex:
    global _INDEX
    if _INDEX is None:
        _INDEX = DocsIndex()
        _INDEX.load()
    return _INDEX


def reset_index() -> None:
    """Test/CLI hook — drop the singleton so next call rebuilds."""
    global _INDEX
    _INDEX = None
