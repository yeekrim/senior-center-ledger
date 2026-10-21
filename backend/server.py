"""통장 정리 도우미 API 서버 (FastAPI).

실행:  uvicorn server:app --reload   (backend 폴더 안에서)
그리고 브라우저에서 http://127.0.0.1:8000 을 연다.

지금까지 화면은 export_review.py가 index.html에 직접 써 넣은 JSON으로만 돌아갔다.
이 서버가 붙으면 화면이 서버에서 같은 모양의 JSON을 받아온다:

  GET  /              프론트엔드(frontend/index.html)
  GET  /api/accounts  통장 종류(운영비 · 부식비 · 냉난방비)와 보고서에 적는 이름
  GET  /api/review    데모 검토 데이터(실제 OCR fixture로 만든 것)
  POST /api/review    통장 사진 여러 장을 올리면 OCR→파싱→병합→검토 결과를 돌려준다
  POST /api/jobs      위와 같은 일을 백그라운드 작업으로 맡기고 작업 번호를 바로 받는다
  GET  /api/jobs/{id} 작업 진행 상황(몇 장 읽었는지)과 끝나면 검토 결과
  POST /api/settlement  검토를 마친 거래로 정산보고서 칸에 들어갈 값을 계산한다

POST는 사진을 메모리에서만 다룬다. run_ocr_pipeline이 사진을 디스크에 쓰지 않고,
이 서버도 업로드 바이트를 저장하지 않는다.
"""

import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from export_review import build_review
from ocr.easyocr_client import warm_up
import jobs
from ocr.pipeline import ENGINES
from reading import read_page
from settings import GPU_SIZES, PRELOAD_OCR
from passbook.pages import infer_opening, merge_pages
from passbook.review import review_transactions
from passbook.classify import ACCOUNTS
from passbook.settlement import settle

FRONTEND = Path(__file__).resolve().parent.parent / "frontend"

log = logging.getLogger("ledger")
if not log.handlers:                       # uvicorn은 앱 로거를 설정하지 않으므로 직접 붙인다
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(asctime)s [ledger] %(message)s"))
    log.addHandler(_handler)
    log.setLevel(logging.INFO)


@asynccontextmanager
async def lifespan(_app):
    """서버를 켤 때 OCR 모델을 미리 불러 둔다. LEDGER_PRELOAD_OCR=0이면 건너뛴다(settings.py)."""
    if PRELOAD_OCR:
        started = time.perf_counter()
        loaded = warm_up(gpu=bool(GPU_SIZES))
        log.info("OCR 모델 미리 불러오기: %s (%.1f초)",
                 "완료" if loaded else "easyocr 없음, 건너뜀", time.perf_counter() - started)
    yield


app = FastAPI(title="통장 정리 도우미", lifespan=lifespan)


@app.get("/")
def index():
    return FileResponse(FRONTEND / "index.html")


@app.get("/api/accounts")
def accounts():
    """통장 종류와 보고서에 적는 이름. 화면은 이 목록으로 통장 고르기 버튼을 그린다."""
    return [{"id": key, "이름": info["이름"]} for key, info in ACCOUNTS.items()]


@app.get("/api/review")
def demo_review():
    """서버 없이도 열리던 데모 데이터를, 이제 서버에서 같은 모양으로 내려준다."""
    return JSONResponse(build_review())


def _check_engine(engine: str):
    if engine not in ENGINES:
        raise HTTPException(400, f"지원하지 않는 엔진: {engine} (가능: {', '.join(ENGINES)})")


def _review_from_pages(pages, opening_balance=None) -> dict:
    """페이지별 rows -> 잔액으로 병합 -> 검토 결과. 사진 순서는 상관없다(passbook.pages)."""
    if opening_balance is None:
        opening_balance = infer_opening(pages)
    merged, merge_report = merge_pages(pages, opening_balance=opening_balance)
    review = review_transactions(merged, opening_balance=opening_balance)
    review["병합"] = merge_report
    review["시작잔액"] = opening_balance
    return review


@app.post("/api/review")
async def review_images(
    files: list[UploadFile] = File(...),
    engine: str = Form("easyocr"),
    opening_balance: int | None = Form(None),
):
    """사진 여러 장을 한 요청 안에서 다 읽고 검토 결과를 돌려준다.

    화면은 진행 상황을 보여주려고 /api/jobs를 쓴다. 이 엔드포인트는 스크립트 · 테스트용으로 남긴다.
    opening_balance: 첫 사진 직전의 잔액. 주지 않으면 사진에서 구한다(pages.infer_opening).
    """
    _check_engine(engine)
    if not files:
        raise HTTPException(400, "이미지가 없습니다.")

    pages, infos = [], []
    for i, upload in enumerate(files):
        page = read_page(await upload.read(), engine=engine, name=f"{i + 1}/{len(files)}")
        pages.append(page["rows"])
        infos.append({k: v for k, v in page.items() if k != "rows"})
    return JSONResponse({**_review_from_pages(pages, opening_balance), "사진": infos})


@app.post("/api/jobs", status_code=202)
async def create_job(
    files: list[UploadFile] = File(...),
    engine: str = Form("easyocr"),
    opening_balance: int | None = Form(None),
):
    """사진을 맡기고 작업 번호를 바로 받는다. 진행 상황은 GET /api/jobs/{id}로 묻는다."""
    _check_engine(engine)
    if not files:
        raise HTTPException(400, "이미지가 없습니다.")
    images = [await upload.read() for upload in files]
    job_id = jobs.submit(images, engine, lambda pages: _review_from_pages(pages, opening_balance))
    return {"id": job_id, "전체": len(images)}


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str):
    """상태(대기 · 읽는중 · 완료 · 실패), 읽은 장수, 완료되면 검토 결과."""
    job = jobs.status(job_id)
    if job is None:
        raise HTTPException(404, "없는 작업입니다. 사진을 다시 올려 주세요.")
    return JSONResponse(job)


class SettlementItem(BaseModel):
    """검토 화면의 item 한 줄. 그 밖의 필드(상태, 제안 등)는 무시한다."""
    date: str
    잔액: int
    입금: int = 0
    지출: int = 0
    적요: str = ""
    사용내역: str = ""


class SettlementRequest(BaseModel):
    """검토 화면의 items를 그대로 받는다. 필수 필드가 빠지면 422로 거절된다."""
    통장: str
    연도: int
    반기: str
    items: list[SettlementItem]
    결정: dict[int, str] = {}
    시작잔액: int | None = None


@app.post("/api/settlement")
def settlement(req: SettlementRequest):
    """통장 하나의 반기 정산값. 미정 입금은 '결정'에 인덱스별로 '수입' 또는 '차감'을 준다."""
    rows = [{"date": item.date, "적요": item.적요, "사용내역": item.사용내역,
             "맡기신금액": item.입금 or None, "찾으신금액": item.지출 or None,
             "잔액": item.잔액}
            for item in req.items]
    try:
        result = settle(rows, req.통장, req.연도, req.반기,
                        opening_balance=req.시작잔액, decisions=req.결정)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return JSONResponse(result)
