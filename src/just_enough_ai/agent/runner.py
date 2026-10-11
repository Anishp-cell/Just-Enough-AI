"""Live inference runner for Nebius Token Factory via OpenAI-compatible SDK."""

import time
import logging
from typing import Generator, Union
from openai import OpenAI
from ..models import RoutingDecision, RunMetadata
from ..router.cost import calculate_cost, calculate_savings_vs_ultra
from ..config import settings
from .mock import run_mock_task

logger = logging.getLogger(__name__)


def run_task(
    task_description: str,
    decision: RoutingDecision,
) -> Generator[Union[str, RunMetadata], None, None]:
    """Execute a task on Nebius Token Factory using the selected model tier.

    Yields:
        str chunks during streaming inference.
        RunMetadata as the final item after the stream ends.

    Falls back to mock mode if MOCK_MODE=True or NEBIUS_API_KEY is not set.
    """
    if settings.mock_mode or not settings.nebius_api_key:
        yield from run_mock_task(task_description, decision)
        return

    client = OpenAI(
        base_url=settings.nebius_base_url,
        api_key=settings.nebius_api_key,
    )

    system_prompt = (
        f"You are an expert agentic coding assistant running on {decision.model_id}. "
        "Provide direct, high-precision code solutions with zero hallucination."
    )

    start_ms = time.monotonic() * 1000
    prompt_tokens = 0
    completion_tokens = 0

    try:
        stream = client.chat.completions.create(
            model=decision.model_id,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": task_description},
            ],
            stream=True,
            stream_options={"include_usage": True},
        )

        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
            if chunk.usage is not None:
                prompt_tokens = chunk.usage.prompt_tokens or 0
                completion_tokens = chunk.usage.completion_tokens or 0

    except Exception as e:
        logger.error(f"Nebius inference error: {e}")
        raise

    latency_ms = (time.monotonic() * 1000) - start_ms
    actual_cost = calculate_cost(decision.selected_tier, prompt_tokens, completion_tokens)
    savings = calculate_savings_vs_ultra(decision.selected_tier, prompt_tokens, completion_tokens)

    metadata = RunMetadata(
        model_id=decision.model_id,
        tier=decision.selected_tier,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
        actual_cost_usd=actual_cost,
        savings_vs_ultra_usd=savings,
        latency_ms=round(latency_ms, 2),
        execution_mode=decision.execution_mode,
    )

    logger.info(
        f"[RUN] model={decision.model_id} tokens={metadata.total_tokens} "
        f"cost=${actual_cost:.5f} saved=${savings:.5f} latency={latency_ms:.0f}ms"
    )

    yield metadata
