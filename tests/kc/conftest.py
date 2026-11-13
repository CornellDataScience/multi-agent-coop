"""Invariant 8: no network in Knowledge Commons tests.

Every KC test runs with sockets disabled and the real Claude/Ollama/OpenRouter client
functions replaced, so a test that forgets ``chat_fn`` or ``MockBackend``
fails loudly instead of making a real call.
"""
from __future__ import annotations

import socket

import pytest

from src.agents import backends


class NetworkBlocked(RuntimeError):
    """Raised when a KC test tries to reach the network."""


def _blocked(*args, **kwargs):
    raise NetworkBlocked("network access is disabled in KC tests; inject chat_fn or use MockBackend")


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    monkeypatch.setattr(socket, "socket", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)
    monkeypatch.setattr(socket, "getaddrinfo", _blocked)
    monkeypatch.setattr(backends, "_claude_chat", _blocked)
    monkeypatch.setattr(backends, "_ollama_chat", _blocked)
    monkeypatch.setattr(backends, "_openrouter_post", _blocked)
