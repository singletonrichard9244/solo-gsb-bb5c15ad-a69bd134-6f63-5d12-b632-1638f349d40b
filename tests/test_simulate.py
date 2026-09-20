"""POST /simulate 行为与校验测试。"""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

PAYLOAD = {
    "buckets": [
        {"id": "api", "capacity": 100, "refill_rate": 10},
        {"id": "user", "capacity": 50, "refill_rate": 5},
    ],
    "requests": [
        {"timestamp": 0, "amount": 10, "buckets": ["api", "user"]},
        {"timestamp": 1, "amount": 95, "buckets": ["api"]},
        {"timestamp": 2, "amount": 30, "buckets": ["api", "user"]},
        {"timestamp": 3, "amount": 20, "buckets": ["user"]},
    ],
}


def test_atomic_simulation_flow():
    resp = client.post("/simulate", json=PAYLOAD)
    assert resp.status_code == 200
    results = resp.json()["results"]
    assert len(results) == 4

    # t=0：满桶扣 10
    r0 = results[0]
    assert r0["allowed"] is True and r0["limiting_bucket"] is None
    assert r0["buckets"]["api"] == {"before": 100, "after": 90}
    assert r0["buckets"]["user"] == {"before": 50, "after": 40}

    # t=1：api 连续补充 1s 后封顶 100，扣 95
    r1 = results[1]
    assert r1["allowed"] is True
    assert r1["buckets"]["api"] == {"before": 100, "after": 5}

    # t=2：api 补充至 15 不足 30 -> 拒绝，链上所有桶保持不变
    # （user 自 t=0 起连续补充 2s：40 + 2*5 = 50，同样不被扣减）
    r2 = results[2]
    assert r2["allowed"] is False and r2["limiting_bucket"] == "api"
    assert r2["buckets"]["api"] == {"before": 15, "after": 15}
    assert r2["buckets"]["user"] == {"before": 50, "after": 50}

    # t=3：被拒绝的请求未扣减 user，补充 1s 后封顶 50，放行
    r3 = results[3]
    assert r3["allowed"] is True
    assert r3["buckets"]["user"] == {"before": 50, "after": 30}


def test_empty_requests():
    resp = client.post("/simulate", json={"buckets": [], "requests": []})
    assert resp.status_code == 200
    assert resp.json() == {"results": []}


def test_reject_duplicate_bucket_definitions():
    body = {
        "buckets": [
            {"id": "a", "capacity": 10, "refill_rate": 1},
            {"id": "a", "capacity": 20, "refill_rate": 2},
        ],
        "requests": [],
    }
    resp = client.post("/simulate", json=body)
    assert resp.status_code == 422
    assert "重复" in resp.text


def test_reject_duplicate_bucket_in_chain():
    body = {
        "buckets": [{"id": "a", "capacity": 10, "refill_rate": 1}],
        "requests": [{"timestamp": 0, "amount": 1, "buckets": ["a", "a"]}],
    }
    resp = client.post("/simulate", json=body)
    assert resp.status_code == 422


def test_reject_invalid_rates_and_amounts():
    for bad_bucket in [
        {"id": "a", "capacity": 10, "refill_rate": 0},
        {"id": "a", "capacity": 10, "refill_rate": -1},
        {"id": "a", "capacity": 0, "refill_rate": 1},
    ]:
        resp = client.post("/simulate", json={"buckets": [bad_bucket], "requests": []})
        assert resp.status_code == 422
    body = {
        "buckets": [{"id": "a", "capacity": 10, "refill_rate": 1}],
        "requests": [{"timestamp": 0, "amount": 0, "buckets": ["a"]}],
    }
    assert client.post("/simulate", json=body).status_code == 422


def test_reject_unknown_reference():
    body = {
        "buckets": [{"id": "a", "capacity": 10, "refill_rate": 1}],
        "requests": [{"timestamp": 0, "amount": 1, "buckets": ["ghost"]}],
    }
    resp = client.post("/simulate", json=body)
    assert resp.status_code == 422
    assert "ghost" in resp.text


def test_reject_out_of_order_timestamps():
    body = {
        "buckets": [{"id": "a", "capacity": 10, "refill_rate": 1}],
        "requests": [
            {"timestamp": 2, "amount": 1, "buckets": ["a"]},
            {"timestamp": 1, "amount": 1, "buckets": ["a"]},
        ],
    }
    assert client.post("/simulate", json=body).status_code == 422
