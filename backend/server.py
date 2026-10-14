"""통장 정리 도우미 API 서버 (FastAPI).

실행:  uvicorn server:app --reload   (backend 폴더 안에서)
그리고 브라우저에서 http://127.0.0.1:8000 을 연다.

지금까지 화면은 export_review.py가 index.html에 직접 써 넣은 JSON으로만 돌아갔다.
이 서버가 붙으면 화면이 서버에서 같은 모양의 JSON을 받아온다:

  GET  /              프론트엔드(frontend/index.html)
  GET  /api/review    데모 검토 데이터(실제 OCR fixture로 만든 것)
  POST /api/review    통장 사진 여러 장을 올리면 OCR→파싱→병합→검토 결과를 돌려준다
  POST /api/settlement  검토를 마친 거래로 정산보고서 칸에 들어갈 값을 계산한다

POST는 사진을 메모리에서만 다룬다. run_ocr_pipeline이 봉투암호화→복호화→OCR을
거치며 평문 이미지를 디스크에 쓰지 않고, 이 서버도 업로드 바이트를 저장하지 않는다.
"""

from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from export_review import build_review
from ocr.pipeline import ENGINES, run_ocr_pipeline
from passbook.lines import parse_lines
from passbook.pages import infer_opening, merge_pages
from passbook.review import review_transactions
from passbook.settlement import settle

FRONTEND = Path(__file__).resolve().parent.parent / "frontend"

app = FastAPI(title="통장 정리 도우미")


@app.get("/")
def index():
    return FileResponse(FRONTEND / "index.html")


@app.get("/api/review")
def demo_review():
    """서버 없이도 열리던 데모 데이터를, 이제 서버에서 같은 모양으로 내려준다."""
    return JSONResponse(build_review())


@app.post("/api/review")
async def review_images(
    files: list[UploadFile] = File(...),
    engine: str = Form("easyocr"),
    opening_balance: int | None = Form(None),
):
    """사진 여러 장 -> 각 장 OCR·파싱 -> 잔액으로 병합 -> 검토 결과.

    사진 순서는 상관없다(passbook.pages가 잔액으로 순서를 정한다).
    opening_balance: 첫 사진 직전의 잔액. 주지 않으면 사진에서 구한다(pages.infer_opening).
    """
    if engine not in ENGINES:
        raise HTTPException(400, f"지원하지 않는 엔진: {engine} (가능: {', '.join(ENGINES)})")
    if not files:
        raise HTTPException(400, "이미지가 없습니다.")

    pages = []
    for upload in files:
        image_bytes = await upload.read()
        lines = run_ocr_pipeline(image_bytes, engine=engine)
        pages.append(parse_lines(lines))

    if opening_balance is None:
        opening_balance = infer_opening(pages)
    merged, merge_report = merge_pages(pages, opening_balance=opening_balance)
    review = review_transactions(merged, opening_balance=opening_balance)
    review["병합"] = merge_report
    review["시작잔액"] = opening_balance
    return JSONResponse(review)


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
