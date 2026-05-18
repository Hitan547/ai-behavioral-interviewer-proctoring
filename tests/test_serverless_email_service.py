import os
import sys
from pathlib import Path

import pytest

SERVERLESS_BACKEND = Path(__file__).resolve().parents[1] / "serverless" / "backend"
sys.path.insert(0, str(SERVERLESS_BACKEND))
os.environ["ENVIRONMENT"] = "test"

from services.email_service import _get_invite_webhook_url


def test_invite_webhook_placeholder_is_treated_as_missing(monkeypatch):
    monkeypatch.setenv("N8N_INVITE_WEBHOOK", "PLACEHOLDER_NOT_SET")
    monkeypatch.delenv("N8N_INVITE_WEBHOOK_PARAMETER_NAME", raising=False)

    assert _get_invite_webhook_url() == ""


def test_invite_webhook_requires_full_url(monkeypatch):
    monkeypatch.setenv("N8N_INVITE_WEBHOOK", "not-a-url")
    monkeypatch.delenv("N8N_INVITE_WEBHOOK_PARAMETER_NAME", raising=False)

    with pytest.raises(RuntimeError, match="full https:// webhook URL"):
        _get_invite_webhook_url()


def test_invite_webhook_accepts_https_url(monkeypatch):
    monkeypatch.setenv("N8N_INVITE_WEBHOOK", "https://example.test/webhook/invite")
    monkeypatch.delenv("N8N_INVITE_WEBHOOK_PARAMETER_NAME", raising=False)

    assert _get_invite_webhook_url() == "https://example.test/webhook/invite"
