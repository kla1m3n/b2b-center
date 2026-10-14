def test_health_reports_db(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["db"] is True
    assert body["status"] in ("ok", "starting")
