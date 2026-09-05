"""Live inference runner for Nebius Token Factory via OpenAI-compatible SDK."""

from typing import Generator
from openai import OpenAI
from ..models import RoutingDecision
from ..config import settings
from .mock import run_mock_task


def run_task(task_description: str, decision: RoutingDecision) -> Generator[str, None, None]:
    """Execute task on Nebius Token Factory using the selected model tier.

    Falls back to mock mode if MOCK_MODE=True or if NEBIUS_API_KEY is not set.
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

    stream = client.chat.completions.create(
        model=decision.model_id,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": task_description},
        ],
        stream=True,
    )

    for chunk in stream:
        content = chunk.choices[0].delta.content or ""
        if content:
            yield content
