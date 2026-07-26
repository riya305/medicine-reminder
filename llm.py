"""Shared Anthropic client for the LLM-backed intake and alarm agents."""

from anthropic import Anthropic

_client = None


def get_client():
    global _client
    if _client is None:
        _client = Anthropic()
    return _client
