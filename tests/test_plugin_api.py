"""Tests for dashboard/plugin_api.py stats() proxy (no network, no fastapi server)."""
import email.message
import importlib
import io
import json
import urllib.error

import pytest

import os
import importlib.util

_here = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location(
    "dashboard_plugin_api", os.path.join(_here, "..", "dashboard", "plugin_api.py"))
pa = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pa)


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return None


def run_stats(monkeypatch, urlopen):
    monkeypatch.setattr(pa.urllib.request, "urlopen", urlopen)


def test_stats_503_when_service_key_unset(monkeypatch):
    monkeypatch.delenv("AMES_SERVICE_KEY", raising=False)
    with pytest.raises(Exception) as ei:
        import asyncio
        asyncio.run(pa.stats())
    assert getattr(ei.value, "status_code", None) == 503


def test_stats_http_error_code_passthrough(monkeypatch):
    monkeypatch.setenv("AMES_SERVICE_KEY", "k")
    err = urllib.error.HTTPError(
        "url", 404, "Not Found", hdrs=email.message.Message(), fp=io.BytesIO(b"no such owner"))
    def boom(req, timeout=None):
        raise err
    run_stats(monkeypatch, boom)
    with pytest.raises(Exception) as ei:
        import asyncio
        asyncio.run(pa.stats())
    assert getattr(ei.value, "status_code", None) == 404


def test_stats_unreachable_502(monkeypatch):
    monkeypatch.setenv("AMES_SERVICE_KEY", "k")
    def boom(req, timeout=None):
        raise OSError("connection refused")
    run_stats(monkeypatch, boom)
    with pytest.raises(Exception) as ei:
        import asyncio
        asyncio.run(pa.stats())
    assert getattr(ei.value, "status_code", None) == 502
    assert "ames unreachable" in ei.value.detail


def test_stats_ok(monkeypatch):
    monkeypatch.setenv("AMES_SERVICE_KEY", "k")
    body = json.dumps({"owner_id": "o1"}).encode()
    run_stats(monkeypatch, lambda req, timeout=None: FakeResponse(body))
    import asyncio
    assert asyncio.run(pa.stats()) == {"owner_id": "o1"}
