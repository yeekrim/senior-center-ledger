"""server.py — FastAPI 엔드포인트 회귀 테스트.

fastapi/httpx가 없는 환경에서는 통째로 건너뛴다(핵심 파이프라인 테스트는
그대로 돌아간다). 설치되어 있으면 세 엔드포인트의 계약을 확인한다.
"""

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

import server  # noqa: E402

client = TestClient(server.app)


def test_index_serves_html():
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]


def test_demo_review_shape():
    r = client.get("/api/review")
    assert r.status_code == 200
    body = r.json()
    assert body["summary"]["전체"] == len(body["items"])
    assert body["계좌"]["은행"] == "신협"


def test_post_merges_and_reviews():
    # mock 엔진은 이미지 내용을 무시하고 fixture를 돌려준다 -> 파이프라인 전 구간 확인
    files = [("files", ("a.jpg", b"x", "image/jpeg"))]
    r = client.post("/api/review", files=files, data={"engine": "mock"})
    assert r.status_code == 200
    body = r.json()
    assert body["items"]                       # 거래가 인식됐다
    assert body["summary"]["전체"] == len(body["items"])
    assert "병합" in body and "order" in body["병합"]


def test_post_rejects_unknown_engine():
    files = [("files", ("a.jpg", b"x", "image/jpeg"))]
    r = client.post("/api/review", files=files, data={"engine": "nope"})
    assert r.status_code == 400
