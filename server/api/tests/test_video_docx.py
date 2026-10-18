"""Large-video upload flow and the 8D .docx export (offline adapters, local backend)."""
import io


def test_upload_url_local_is_direct_and_validates(client):
    r = client.post("/api/teach/upload-url", json={"filename": "expert.mp4", "content_type": "video/mp4", "size": 120 * 2**20})
    assert r.json()["mode"] == "direct" and r.json()["max_mb"] == 500
    assert client.post("/api/teach/upload-url", json={"filename": "x.exe", "content_type": "application/x-msdownload", "size": 10}).status_code == 422
    too_big = client.post("/api/teach/upload-url", json={"filename": "long.mp4", "content_type": "video/mp4", "size": 900 * 2**20})
    assert too_big.status_code == 422 and "500 MB" in too_big.json()["detail"]


def test_from_upload_drafts_cards_and_rejects_foreign_paths(client):
    from container import get_container

    c = get_container()
    uri = c.blobs.save("teach/uploads/20261018/abc-expert.mp4", b"\x00" * 2048, "video/mp4")
    r = client.post("/api/teach/videos/from-upload", json={"uri": uri, "content_type": "video/mp4", "part_number": "IMP-200"})
    assert r.status_code == 200 and r.json()["cards"][0]["status"] == "draft"
    for bad in ("local://line/2026-10-18/D-1.jpg", "local://teach/uploads/../../senpaiqc.db", "local://teach/uploads/missing.mp4"):
        assert client.post("/api/teach/videos/from-upload", json={"uri": bad, "content_type": "video/mp4", "part_number": "IMP-200"}).status_code == 422


def test_8d_docx_export(client):
    from docx import Document

    from container import get_container

    c = get_container()
    c.docs.put("investigations", "INV-T", {"id": "INV-T", "defect_name": "porosity", "part_number": "IMP-200", "shift_key": "2026-09-25/A",
                                           "rate": 0.064, "ucl": 0.054, "center": 0.028, "status": "analysed",
                                           "hypotheses": [{"rank": 1, "statement": "porosity driven by MD-04 + LOT-2409C", "blamed": {"mould_id": "MD-04"},
                                                           "evidence": ["31.6% on n=1561"], "confidence": "high"}]})
    c.docs.put("reports", "8D-INV-T", {"id": "8D-INV-T", "investigation_id": "INV-T", "status": "draft", "generated_by": "test",
                                       "sections": {"D4_root_cause": "Mould MD-04 with lot LOT-2409C."}})
    r = client.get("/api/learn/reports/8D-INV-T/docx")
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/vnd.openxmlformats")
    text = "\n".join(p.text for p in Document(io.BytesIO(r.content)).paragraphs)
    assert "D4 · Root cause" in text and "Mould MD-04 with lot LOT-2409C." in text and "(to be completed)" in text
    assert client.get("/api/learn/reports/nope/docx").status_code == 404
