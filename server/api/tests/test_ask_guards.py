"""Ask SenpaiQC and request guardrails (offline adapters, no Gemini key)."""
import json

from config import REPO_ROOT
from ports import Answer, ModelUsage


def _seed():
    from container import get_container
    from domain.models import DefectKnowledgeCard

    c = get_container()
    for d in json.loads((REPO_ROOT / "data" / "seed_cards.json").read_text()):
        c.cards.put(DefectKnowledgeCard(**d))
    return c


def test_retrieval_understands_bahasa(client):
    c = _seed()
    from slices.ask.service import build_corpus, retrieve

    top = retrieve(build_corpus(c), "Berapa batas porositas yang boleh diterima?", k=3)
    assert top[0]["id"] == "card:imp-200-porosity-v1"


def test_offline_answer_is_marked_ungrounded(client):
    _seed()
    r = client.post("/api/ask", json={"question": "What is the accept limit for porosity?"}).json()
    assert r["grounded"] is False
    assert r["answer"].startswith("Offline mode")
    assert r["citations"] and r["citations"][0]["page"] == "knowledge"


def test_citations_outside_the_sources_are_dropped(client):
    c = _seed()

    class Liar:
        name = "fake"

        def answer(self, question, sources, history):
            return Answer("Porosity limit is 10 holes.", ["card:does-not-exist"], True, [], ModelUsage(model="fake"))

    c.qa = Liar()
    r = client.post("/api/ask", json={"question": "porosity limit?"}).json()
    assert r["grounded"] is False  # claimed grounded, but cited nothing that was retrieved
    assert r["citations"] == [] and r["dropped_citations"] == ["card:does-not-exist"]


def test_question_limits(client):
    assert client.post("/api/ask", json={"question": "   "}).status_code == 422
    assert client.post("/api/ask", json={"question": "x" * 600}).status_code == 422


def test_ai_rate_limit(client, monkeypatch):
    import config
    import guards

    monkeypatch.setattr(config.get_settings(), "ai_calls_per_minute", 2)
    guards._recent.clear()
    codes = [client.post("/api/ask", json={"question": "porosity?"}).status_code for _ in range(3)]
    assert codes == [200, 200, 429]
    guards._recent.clear()


def test_security_headers_and_token_check(client):
    r = client.get("/api/health")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["referrer-policy"] == "no-referrer"
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]
    assert client.get("/api/teach/cards", headers={"Authorization": "Bearer wrong"}).status_code == 401


def test_cloud_run_refuses_default_token():
    import pytest

    from config import Settings

    with pytest.raises(RuntimeError, match="DEMO_TOKEN"):
        Settings(backend="gcp", auth_mode="demo", demo_token="senpaiqc-demo", gemini_api_key="x").check_deploy_secrets()
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        Settings(backend="gcp", auth_mode="demo", demo_token="kl-a-long-random-token", gemini_api_key="").check_deploy_secrets()
    Settings(backend="gcp", auth_mode="demo", demo_token="kl-a-long-random-token", gemini_api_key="x").check_deploy_secrets()
    Settings(backend="local", demo_token="senpaiqc-demo").check_deploy_secrets()  # local dev stays easy
