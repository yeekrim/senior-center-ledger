"""통장 정리 도우미 API 서버 (FastAPI).

실행:  uvicorn server:app --reload   (backend 폴더 안에서)
그리고 브라우저에서 http://127.0.0.1:8000 을 연다.

지금까지 화면은 export_review.py가 index.html에 직접 써 넣은 JSON으로만 돌아갔다.
이 서버가 붙으면 화면이 서버에서 같은 모양의 JSON을 받아온다:

  GET  /              프론트엔드(frontend/index.html)
  GET  /api/review    데모 검토 데이터(실제 OCR fixture로 만든 것)
  POST /api/review    통장 사진 여러 장을 올리면 OCR→파싱→병합→검토 결과를 돌려준다

POST는 사진을 메모리에서만 다룬다. run_ocr_pipeline이 봉투암호화→복호화→OCR을
거치며 평문 이미지를 디스크에 쓰지 않고, 이 서버도 업로드 바이트를 저장하지 않는다.
"""

from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from export_review import build_review
from ocr.pipeline import ENGINES, run_ocr_pipeline
from passbook.lines import parse_lines
from passbook.pages import merge_pages
from passbook.review import review_transactions

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
):
    """사진 여러 장 -> 각 장 OCR·파싱 -> 잔액으로 병합 -> 검토 결과.

    사진 순서는 상관없다(passbook.pages가 잔액으로 순서를 정한다).
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

    merged, merge_report = merge_pages(pages, opening_balance=0)
    review = review_transactions(merged, opening_balance=0)
    review["계좌"] = {"은행": "신협", "상품": "보통예탁금", "시작잔액": 0}
    review["병합"] = merge_report
    return JSONResponse(review)
