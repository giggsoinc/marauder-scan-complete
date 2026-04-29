# =============================================================
# FILE: tests/unit/test_render_agent_package.py
# VERSION: 1.0.0
# UPDATED: 2026-04-19
# OWNER: Giggso Inc
# PURPOSE: Unit tests for render_agent_package orchestration.
#          All S3/SES calls are mocked — no AWS credentials needed.
# AUDIT LOG:
#   v1.0.0  2026-04-19  Initial — agent delivery system
# =============================================================

import os
import sys
import json
import types
from unittest.mock import MagicMock, patch, call

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))

from render_agent_package import render_agent_package


# ── Fixtures ──────────────────────────────────────────────────

def _make_store(token: str = "test-token-123") -> MagicMock:
    """Return a fully mocked AgentStore."""
    store              = MagicMock()
    store.bucket       = "test-bucket"
    store.region       = "us-east-1"
    store.generate_otp.return_value = "123456"
    store.hash_otp.return_value     = "$2b$12$fakehash"
    store.create_package.return_value = token
    store.get_presigned_urls.return_value = {
        "installer_url":  "https://s3.example.com/installer",
        "meta_url":       "https://s3.example.com/meta",
        "status_put_url": "https://s3.example.com/status",
    }
    store._put = MagicMock(return_value=True)
    return store


def _make_renderer() -> MagicMock:
    """Return a renderer mock that returns a templated string."""
    renderer        = MagicMock()
    renderer.render = MagicMock(return_value="#!/bin/bash\n# rendered script\n")
    return renderer


# ── Tests ──────────────────────────────────────────────────────

def test_successful_package_generation_mac():
    """Happy path: mac package is generated and result contains OTP + URLs."""
    store    = _make_store()
    renderer = _make_renderer()

    result = render_agent_package(
        recipient_name  = "Jane Smith",
        recipient_email = "jane@example.com",
        os_type         = "mac",
        store           = store,
        renderer        = renderer,
        send_email      = False,
    )

    assert result["success"] is True
    assert result["otp"] == "123456"
    assert result["token"] == "test-token-123"
    assert "installer_url" in result
    assert "meta_url" in result


def test_successful_package_generation_windows():
    """Windows platform selects .ps1 template."""
    store    = _make_store()
    renderer = _make_renderer()

    result = render_agent_package(
        recipient_name  = "Bob Jones",
        recipient_email = "bob@example.com",
        os_type         = "windows",
        store           = store,
        renderer        = renderer,
        send_email      = False,
    )

    assert result["success"] is True
    # _put should be called for the re-rendered .ps1
    final_put_calls = [str(c) for c in store._put.call_args_list]
    assert any("ps1" in c for c in final_put_calls)


def test_unsupported_os_type_returns_error():
    """Unknown os_type must fail fast without touching S3."""
    store    = _make_store()
    renderer = _make_renderer()

    result = render_agent_package(
        recipient_name  = "Test",
        recipient_email = "test@example.com",
        os_type         = "freebsd",
        store           = store,
        renderer        = renderer,
        send_email      = False,
    )

    assert result["success"] is False
    assert "freebsd" in result["error"]
    store.create_package.assert_not_called()


def test_s3_upload_failure_returns_error():
    """When create_package returns None, result must indicate failure."""
    store              = _make_store()
    store.create_package.return_value = None
    renderer           = _make_renderer()

    result = render_agent_package(
        recipient_name  = "Test",
        recipient_email = "test@example.com",
        os_type         = "linux",
        store           = store,
        renderer        = renderer,
        send_email      = False,
    )

    assert result["success"] is False
    assert "S3" in result["error"] or "upload" in result["error"].lower()


def test_renderer_called_five_times_for_real_urls():
    """
    Template is rendered five times today:
      1. Pre-render .sh with placeholder context to mint the token.
      2. Render final .sh with real presigned URLs.
      3. Render final .ps1 with the same real URLs.
      4. Render uninstall_agent.sh with token baked in.
      5. Render uninstall_agent.ps1 with token baked in.
    History: assertion was == 2 (pre-ps1), then == 3 (pre-uninstall),
    now == 5 after uninstall scripts were added to render_agent_package.py.
    """
    store    = _make_store(token="abc-def-123")
    renderer = _make_renderer()

    render_agent_package(
        recipient_name  = "Alice",
        recipient_email = "alice@example.com",
        os_type         = "mac",
        store           = store,
        renderer        = renderer,
        send_email      = False,
    )

    assert renderer.render.call_count == 5
    # Call 2 (.sh with real URLs) must carry the real token and META_URL.
    second_ctx = renderer.render.call_args_list[1][0][1]
    assert second_ctx["TOKEN"] == "abc-def-123"
    assert second_ctx["META_URL"] == "https://s3.example.com/meta"
