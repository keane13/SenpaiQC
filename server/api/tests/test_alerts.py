"""Spike alerts: message, inline delivery on scan, and the Pub/Sub push endpoint's guard."""
import base64
import json

import httpx
import pytest

from slices.alerts import service

INV = {"id": "INV-1", "part_number": "IMP-200", "defect_name": "porosity", "shift_key": "2026-09-25/A",
       "rate": 0.0642, "ucl": 0.0542, "center": 0.028}


def test_spike_message_has_numbers_and_link():
    text = service.render(service.spike_alert(INV), "https://senpaiqc.example/")
    assert text.splitlines()[0] == "SenpaiQC alert: porosity spike on IMP-200"
    assert "6.4% defective (limit 5.4%, normal 2.8%)" in text
    assert "INV-1" in text and text.endswith("https://senpaiqc.example/#analytics")


class FakeChannels:
    def __init__(self):
        self.sent = []

    def names(self):
        return ["fake"]

    def deliver(self, text):
        self.sent.append(text)
        return ["fake"]


def test_scan_alerts_once_per_new_investigation(client):
    from .test_flow import _load_process_events, _seed

    c = _seed(client)
    _load_process_events(c)
    fake = FakeChannels()
    c.channels = fake
    opened = client.post("/api/learn/scan", json={"defects": ["porosity"]}).json()
    assert len(opened) == 1 and len(fake.sent) == 1
    assert opened[0]["id"] in fake.sent[0]
    client.post("/api/learn/scan", json={"defects": ["porosity"]})
    assert len(fake.sent) == 1  # still open: no second alert


def test_alert_failure_does_not_break_scan(client):
    from container import get_container

    class Broken(FakeChannels):
        def deliver(self, text):
            raise RuntimeError("telegram HTTP 500")

    c = get_container()
    c.channels = Broken()
    service.notify(c, service.spike_alert(INV))  # logs, does not raise


def test_push_endpoint_needs_pubsub_token(client, monkeypatch):
    body = {"message": {"data": base64.b64encode(json.dumps(service.spike_alert(INV)).encode()).decode()}}
    assert client.post("/api/alerts/push", json=body).status_code == 404  # not configured locally
    from config import get_settings

    monkeypatch.setattr(get_settings(), "alert_push_audience", "https://x/api/alerts/push")
    monkeypatch.setattr(get_settings(), "alert_push_sa", "sa@example.iam.gserviceaccount.com")
    r = client.post("/api/alerts/push", json=body, headers={"Authorization": "Bearer not-a-google-token"})
    assert r.status_code == 401


def test_telegram_error_never_leaks_the_token(monkeypatch):
    from adapters.alert_channels import HttpAlertChannels

    def boom(url, **kw):
        raise httpx.ConnectError(f"cannot reach {url}")

    monkeypatch.setattr(httpx, "post", boom)
    with pytest.raises(RuntimeError) as exc:
        HttpAlertChannels("123:SECRET", "42").deliver("hi")
    assert "SECRET" not in str(exc.value)


def test_pasted_secrets_are_trimmed():
    from adapters.alert_channels import HttpAlertChannels

    ch = HttpAlertChannels(" 123:abc ", "42 ", "")
    assert ch.telegram == ("123:abc", "42") and ch.names() == ["telegram"]
