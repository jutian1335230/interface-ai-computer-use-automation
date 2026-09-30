from fastapi.testclient import TestClient

from interface_automation.target_app import app


client = TestClient(app)


def test_member_lookup_success() -> None:
    response = client.post("/legacy/search", data={"member_id": "12345"})
    assert response.status_code == 200
    assert "Member Detail" in response.text
    assert "$1,250.00" in response.text


def test_member_lookup_has_distinct_business_and_runtime_outcomes() -> None:
    not_found = client.post("/legacy/search", data={"member_id": "11111"})
    expired = client.post("/legacy/search", data={"member_id": "99999"})

    assert "No member found" in not_found.text
    assert "Session expired" in expired.text
