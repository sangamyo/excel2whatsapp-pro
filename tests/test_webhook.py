"""Webhook + deployment-config tests. Run with: pytest -q"""
import hashlib
import hmac
import json
import os
import tempfile

# Configure an isolated SQLite DB and dummy credentials before the app is imported.
_tmp = tempfile.mkdtemp()
os.environ.update({
    "DATABASE_URL": f"sqlite:///{_tmp}/test.db",
    "REDIS_URL": "",
    "CELERY_BROKER_URL": "",
    "CELERY_RESULT_BACKEND": "",
    "SECRET_KEY": "test-secret-key-that-is-long-enough-123",
    "ACCESS_TOKEN": "dummy",
    "PHONE_NUMBER_ID": "123",
    "VERIFY_TOKEN": "verify-me",
    "APP_SECRET": "",
})

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.config.settings import settings  # noqa: E402
from app.database import SessionLocal, normalize_database_url  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Campaign, Message, User  # noqa: E402

client = TestClient(app)


def _status_payload(wa_id, status, **extra):
    return {
        "object": "whatsapp_business_account",
        "entry": [{"id": "WABA", "changes": [{"field": "messages", "value": {
            "messaging_product": "whatsapp",
            "statuses": [{"id": wa_id, "status": status, "timestamp": "1760000000",
                          "recipient_id": "15551234567", **extra}],
        }}]}],
    }


@pytest.fixture
def message():
    db = SessionLocal()
    user = User(name="T", email=f"t{os.urandom(4).hex()}@example.com", password="x")
    db.add(user)
    db.flush()
    campaign = Campaign(user_id=user.id, template="Hi", total_messages=1, success_count=1, status="completed")
    db.add(campaign)
    db.flush()
    msg = Message(campaign_id=campaign.id, phone="+15551234567", message="Hi", context={},
                  status="sent", wa_message_id=f"wamid.{os.urandom(6).hex()}")
    db.add(msg)
    db.commit()
    ids = (msg.id, campaign.id, msg.wa_message_id)
    db.close()
    return ids


def _load(message_id, campaign_id):
    db = SessionLocal()
    try:
        return db.get(Message, message_id).status, db.get(Message, message_id).error_reason, db.get(Campaign, campaign_id)
    finally:
        db.close()


def test_verify_handshake():
    ok = client.get("/webhook/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "verify-me", "hub.challenge": "42"})
    assert ok.status_code == 200 and ok.text == "42"
    bad = client.get("/webhook/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "nope", "hub.challenge": "42"})
    assert bad.status_code == 403


def test_status_progression_never_regresses(message):
    message_id, campaign_id, wa_id = message
    assert client.post("/webhook/whatsapp", json=_status_payload(wa_id, "delivered")).json()["updated"] == 1
    assert client.post("/webhook/whatsapp", json=_status_payload(wa_id, "sent")).json()["updated"] == 0
    assert _load(message_id, campaign_id)[0] == "delivered"
    client.post("/webhook/whatsapp", json=_status_payload(wa_id, "read"))
    assert _load(message_id, campaign_id)[0] == "read"


def test_failed_status_moves_counts(message):
    message_id, campaign_id, wa_id = message
    payload = _status_payload(wa_id, "failed", errors=[{"code": 131026, "title": "Message undeliverable"}])
    assert client.post("/webhook/whatsapp", json=payload).json()["updated"] == 1
    status, reason, campaign = _load(message_id, campaign_id)
    assert status == "failed" and "131026" in reason
    assert (campaign.success_count, campaign.failed_count) == (0, 1)


def test_unknown_message_id_is_ignored():
    r = client.post("/webhook/whatsapp", json=_status_payload("wamid.unknown", "delivered"))
    assert r.status_code == 200 and r.json()["updated"] == 0


def test_signature_required_when_app_secret_set(message, monkeypatch):
    _, _, wa_id = message
    monkeypatch.setattr(settings, "APP_SECRET", "s3cret")
    body = json.dumps(_status_payload(wa_id, "delivered")).encode()
    headers = {"Content-Type": "application/json"}

    assert client.post("/webhook/whatsapp", content=body, headers=headers).status_code == 403
    bad = {**headers, "X-Hub-Signature-256": "sha256=" + "0" * 64}
    assert client.post("/webhook/whatsapp", content=body, headers=bad).status_code == 403

    sig = hmac.new(b"s3cret", body, hashlib.sha256).hexdigest()
    good = {**headers, "X-Hub-Signature-256": f"sha256={sig}"}
    r = client.post("/webhook/whatsapp", content=body, headers=good)
    assert r.status_code == 200 and r.json()["updated"] == 1


def test_invalid_json_rejected():
    r = client.post("/webhook/whatsapp", content=b"not json", headers={"Content-Type": "application/json"})
    assert r.status_code == 400


def test_database_url_normalization():
    assert normalize_database_url("postgres://u:p@h:5432/db") == "postgresql://u:p@h:5432/db"
    assert normalize_database_url("postgresql://u:p@h/db") == "postgresql://u:p@h/db"
    assert normalize_database_url("sqlite:///./dev.db") == "sqlite:///./dev.db"


def test_enqueue_without_redis_uses_background_thread(monkeypatch):
    from app.tasks import runner

    calls = []
    monkeypatch.setattr("app.tasks.send_message.process_campaign_sync", lambda cid, via: calls.append(cid))
    assert runner.enqueue_campaign(999) == "background"
    runner.executor.shutdown(wait=True)
    runner.executor = type(runner.executor)(max_workers=2)
    assert calls == [999]
