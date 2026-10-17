"""Pytest global configuration and fixtures."""

import pytest
from just_enough_ai.config import settings

@pytest.fixture(autouse=True)
def force_mock_mode_for_tests(monkeypatch):
    """Ensure all unit test executions default to mock mode to prevent live API quota usage."""
    monkeypatch.setattr(settings, "mock_mode", True)
