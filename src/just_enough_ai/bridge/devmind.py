"""Bridge to interact with devmind codebase memory index or local AST symbol fallback."""

import ast
import logging
import re
import shutil
import subprocess
from pathlib import Path
from typing import List, Tuple

from ..config import settings
from ..models import MemoryContext

logger = logging.getLogger(__name__)

# Common English stop-words to exclude from symbol extraction
STOP_WORDS = {
    "a", "an", "the", "in", "on", "at", "to", "for", "from", "of", "with",
    "and", "or", "not", "is", "it", "this", "that", "add", "fix", "update",
    "make", "write", "create", "implement", "refactor", "how", "what", "why",
    "please", "function", "method", "class", "file", "code", "new", "test",
}

IGNORE_DIRS = {
    ".git", ".venv", "venv", "__pycache__", "node_modules", ".pytest_cache",
    ".ruff_cache", "dist", "build", ".idea", ".vscode", "site-packages",
}


def _extract_query_keywords(query: str) -> List[str]:
    """Extract meaningful symbol candidates and identifiers from user prompt."""
    tokens = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", query)
    keywords = [
        t for t in tokens
        if t.lower() not in STOP_WORDS and len(t) >= 3
    ]
    return keywords


def _scan_local_codebase(query: str, repo_dir: str = ".") -> Tuple[float, List[str]]:
    """Scan local repository AST symbols and files when devmind daemon is not running.

    Returns:
        (confidence_score, context_chunks)
    """
    root_path = Path(repo_dir).resolve()
    if not root_path.exists():
        return 0.0, []

    keywords = _extract_query_keywords(query)
    if not keywords:
        return 0.1, []

    keywords_lower = [k.lower() for k in keywords]
    symbol_hits = []
    file_hits = []
    score_accumulator = 0.0

    # Collect python files
    for py_file in root_path.rglob("*.py"):
        if any(part in IGNORE_DIRS for part in py_file.parts):
            continue

        rel_path = str(py_file.relative_to(root_path)).replace("\\", "/")

        # Check path relevance
        path_matched = any(k in rel_path.lower() for k in keywords_lower)
        if path_matched:
            file_hits.append(rel_path)
            score_accumulator += 0.25

        try:
            content = py_file.read_text(encoding="utf-8", errors="ignore")
            tree = ast.parse(content, filename=str(py_file))
            lines = content.splitlines()

            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    fn_name_lower = node.name.lower()
                    fn_tokens = set(fn_name_lower.split("_"))
                    matched = any(
                        (k == fn_name_lower) or (k in fn_tokens) or (len(k) >= 5 and k in fn_name_lower)
                        for k in keywords_lower
                    )
                    if matched:
                        end_line = getattr(node, "end_lineno", node.lineno + 5)
                        snippet_lines = lines[node.lineno - 1 : min(end_line, node.lineno + 12)]
                        snippet = "\n".join(snippet_lines)
                        symbol_hits.append(f"[{rel_path}:{node.lineno}] def {node.name}(...):\n{snippet}")
                        score_accumulator += 0.45

                elif isinstance(node, ast.ClassDef):
                    class_name_lower = node.name.lower()
                    class_tokens = set(re.findall(r"[a-z0-9]+", class_name_lower))
                    matched = any(
                        (k == class_name_lower) or (k in class_tokens) or (len(k) >= 5 and k in class_name_lower)
                        for k in keywords_lower
                    )
                    if matched:
                        end_line = getattr(node, "end_lineno", node.lineno + 5)
                        snippet_lines = lines[node.lineno - 1 : min(end_line, node.lineno + 10)]
                        snippet = "\n".join(snippet_lines)
                        symbol_hits.append(f"[{rel_path}:{node.lineno}] class {node.name}:\n{snippet}")
                        score_accumulator += 0.45

        except Exception as e:
            logger.debug(f"AST parsing skipped for {rel_path}: {e}")
            continue

    # Assemble context chunks (cap at top 4 most relevant)
    chunks = symbol_hits[:4]
    if not chunks and file_hits:
        chunks = [f"[Matched File]: {f}" for f in file_hits[:3]]

    # Confidence score normalization:
    # Strong symbol hit + file hit yields >= 0.70 (Nano eligibility)
    # Partial hits yield 0.35 - 0.60 (Super eligibility)
    # Zero hits yield < 0.20 (Ultra eligibility)
    if symbol_hits:
        confidence = min(0.95, max(0.70, score_accumulator))
    elif file_hits:
        confidence = min(0.65, max(0.40, score_accumulator))
    else:
        confidence = 0.05

    return round(confidence, 2), chunks


def query_codebase_memory(query: str, repo_dir: str = ".") -> MemoryContext:
    """Retrieve memory context from devmind CLI, or fall back to local AST symbol indexing.

    Calculates confidence score based on returned content density and structure.
    """
    if not settings.devmind_enabled:
        confidence, chunks = _scan_local_codebase(query, repo_dir)
        return MemoryContext(
            query=query,
            confidence_score=confidence,
            context_chunks=chunks,
            has_high_confidence=confidence >= 0.7,
        )

    # Check if devmind executable is on PATH
    devmind_bin = shutil.which(settings.devmind_cli_path)
    if not devmind_bin:
        logger.debug("devmind CLI not found on PATH; falling back to local AST indexer.")
        confidence, chunks = _scan_local_codebase(query, repo_dir)
        return MemoryContext(
            query=query,
            confidence_score=confidence,
            context_chunks=chunks,
            has_high_confidence=confidence >= 0.7,
        )

    try:
        # Run: devmind ask "<query>" --dir <repo_dir>
        result = subprocess.run(
            [devmind_bin, "ask", query, "--dir", repo_dir],
            capture_output=True,
            text=True,
            timeout=15,
        )

        output = result.stdout.strip()
        if not output or result.returncode != 0:
            # Fall back to local AST scanner
            confidence, chunks = _scan_local_codebase(query, repo_dir)
            return MemoryContext(
                query=query,
                confidence_score=confidence,
                context_chunks=chunks,
                has_high_confidence=confidence >= 0.7,
            )

        # Compute confidence based on response length and relevance signals
        chunks = [line.strip() for line in output.split("\n") if line.strip()]
        confidence = min(1.0, max(0.2, len(output) / 400.0))

        return MemoryContext(
            query=query,
            confidence_score=round(confidence, 2),
            context_chunks=chunks,
            has_high_confidence=confidence >= 0.7,
        )
    except Exception as e:
        logger.warning(f"Error querying devmind: {e}; falling back to local AST scanner.")
        confidence, chunks = _scan_local_codebase(query, repo_dir)
        return MemoryContext(
            query=query,
            confidence_score=confidence,
            context_chunks=chunks,
            has_high_confidence=confidence >= 0.7,
        )
