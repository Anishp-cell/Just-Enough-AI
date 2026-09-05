"""Bridge to interact with devmind codebase memory index."""

import subprocess
import shutil
import logging
from ..models import MemoryContext
from ..config import settings

logger = logging.getLogger(__name__)


def query_codebase_memory(query: str, repo_dir: str = ".") -> MemoryContext:
    """Retrieve memory context from devmind.

    Uses devmind CLI via subprocess if available, or gracefully provides a fallback.
    Calculates confidence score based on returned content density and structure.
    """
    if not settings.devmind_enabled:
        return MemoryContext(
            query=query,
            confidence_score=0.0,
            context_chunks=[],
            has_high_confidence=False,
        )

    # Check if devmind executable is on PATH
    devmind_bin = shutil.which(settings.devmind_cli_path)
    if not devmind_bin:
        logger.debug("devmind CLI not found on PATH; returning zero-confidence context.")
        return MemoryContext(
            query=query,
            confidence_score=0.0,
            context_chunks=[],
            has_high_confidence=False,
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
            return MemoryContext(query=query, confidence_score=0.1, context_chunks=[])

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
        logger.warning(f"Error querying devmind: {e}")
        return MemoryContext(query=query, confidence_score=0.0, context_chunks=[])
