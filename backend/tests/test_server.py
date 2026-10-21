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


def test_settlement_from_demo_review():
    # 데모 검토 데이터(실사진 OCR, 부식비 통장)를 그대로 정산에 넘긴다.
    items = client.get("/api/review").json()["items"]
    body = {"통장": "부식비", "연도": 2026, "반기": "상반기", "items": items}
    r = client.post("/api/settlement", json=body)
    assert r.status_code == 200
    result = r.json()
    assert [m["월"] for m in result["월별"]] == [1, 2, 3, 4, 5, 6]
    assert result["총괄"]["예산액"] == 849_000 * 2          # OCR이 '3분기'의 숫자를 잃어도 보조금
    assert result["총괄"]["이자"] == 21                     # '결산이 자'로 읽혀도 이자
    assert [p["사용내역"] for p in result["미정"]] == ["취소-주식"]
    # 잔액오독·거래누락을 고치지 않은 데이터이므로 완료가 아니다
    assert result["검산"]["잔액연쇄"] is False
    assert result["완료"] is False


def test_settlement_rejects_unknown_account():
    body = {"통장": "간식비", "연도": 2026, "반기": "상반기", "items": []}
    r = client.post("/api/settlement", json=body)
    assert r.status_code == 400


def test_post_review_infers_opening_balance():
    files = [("files", ("a.jpg", b"x", "image/jpeg"))]
    r = client.post("/api/review", files=files, data={"engine": "mock"})
    assert r.json()["시작잔액"] == 0          # mock fixture는 '신규'부터 찍은 통장


def test_settlement_rejects_item_without_balance():
    body = {"통장": "부식비", "연도": 2026, "반기": "상반기",
            "items": [{"date": "20260320", "입금": 849000}]}
    r = client.post("/api/settlement", json=body)
    assert r.status_code == 422


def test_settlement_rejects_decision_on_non_pending_row():
    items = client.get("/api/review").json()["items"]
    body = {"통장": "부식비", "연도": 2026, "반기": "상반기", "items": items,
            "결정": {"0": "수입"}}        # 0번은 보조금 입금이다
    r = client.post("/api/settlement", json=body)
    assert r.status_code == 400


def _wait_job(job_id, seconds=10):
    import time
    deadline = time.time() + seconds
    while time.time() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["상태"] in ("완료", "실패"):
            return job
        time.sleep(0.05)
    raise AssertionError("작업이 끝나지 않았습니다")


def test_job_reports_progress_and_result():
    files = [("files", ("a.jpg", b"page-a", "image/jpeg")), ("files", ("b.jpg", b"page-b", "image/jpeg"))]
    r = client.post("/api/jobs", files=files, data={"engine": "mock"})
    assert r.status_code == 202
    assert r.json()["전체"] == 2
    job = _wait_job(r.json()["id"])
    assert job["상태"] == "완료" and job["읽음"] == 2
    assert job["결과"]["items"]
    assert len(job["결과"]["사진"]) == 2


def test_job_reuses_same_photo():
    files = [("files", ("a.jpg", b"same-photo", "image/jpeg"))]
    first = _wait_job(client.post("/api/jobs", files=files, data={"engine": "mock"}).json()["id"])
    again = _wait_job(client.post("/api/jobs", files=files, data={"engine": "mock"}).json()["id"])
    assert again["사진"][0]["재사용"] is True
    assert again["결과"]["items"] == first["결과"]["items"]


def test_unknown_job_is_404():
    assert client.get("/api/jobs/nope").status_code == 404


def test_job_rejects_unknown_engine():
    files = [("files", ("a.jpg", b"x", "image/jpeg"))]
    assert client.post("/api/jobs", files=files, data={"engine": "nope"}).status_code == 400


def test_accounts_come_from_one_place():
    from passbook.classify import ACCOUNTS
    body = client.get("/api/accounts").json()
    assert [a["id"] for a in body] == list(ACCOUNTS)
    assert all(a["이름"] for a in body)
