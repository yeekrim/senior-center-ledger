"""사진 읽기를 백그라운드 작업으로 돌리고, 화면이 진행 상황을 물어볼 수 있게 한다.

OCR은 사진 한 장에 수 초~수십 초가 걸린다. 한 번의 요청 안에서 다 끝내면 화면은 그동안
아무것도 알 수 없다. 그래서 업로드는 작업 번호만
바로 돌려주고, 사진은 뒤에서 한 장씩 읽으면서 '몇 장 읽었는지'를 갱신한다.

이 앱은 한 기기에서 한 사람이 쓰므로 큐 서버 없이 프로세스 안의 작업 스레드 하나로 충분하다.
작업자를 하나로 두는 이유는 OCR 모델을 여러 스레드가 동시에 쓰지 않게 하기 위해서다.

  - 사진은 메모리에서만 다루고, 다 읽으면 바로 참조를 버린다(디스크에 쓰지 않는다).
  - 같은 사진을 다시 올리면(같은 바이트) 앞서 읽은 결과를 그대로 쓴다. 다시 시도해도
    결과가 달라지지 않고(멱등), 기다리지도 않는다. 결과는 최근 CACHE_SIZE장만 기억한다.
  - 끝난 작업은 JOB_TTL_SECONDS가 지나면 지운다.
"""

import hashlib
import logging
import threading
import time
import uuid
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor

from reading import read_page

WAITING, READING, DONE, FAILED = "대기", "읽는중", "완료", "실패"
CACHE_SIZE = 32
JOB_TTL_SECONDS = 60 * 60

log = logging.getLogger("ledger")
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ocr")
_lock = threading.Lock()
_jobs: dict[str, dict] = {}
_pages: OrderedDict[str, dict] = OrderedDict()   # 사진 해시 -> read_page 결과


def _page_key(image_bytes: bytes, engine: str) -> str:
    return hashlib.sha256(engine.encode() + b"\0" + image_bytes).hexdigest()


def _cached_read(image_bytes: bytes, engine: str, name: str) -> dict:
    key = _page_key(image_bytes, engine)
    with _lock:
        if key in _pages:
            _pages.move_to_end(key)
            return {**_pages[key], "재사용": True}
    page = read_page(image_bytes, engine=engine, name=name)
    with _lock:
        _pages[key] = page
        while len(_pages) > CACHE_SIZE:
            _pages.popitem(last=False)
    return {**page, "재사용": False}


def _update(job_id: str, **fields):
    with _lock:
        _jobs[job_id].update(fields)


def _run(job_id: str, images: list, engine: str, finish):
    _update(job_id, 상태=READING)
    pages, infos = [], []
    try:
        for i, image_bytes in enumerate(images):
            page = _cached_read(image_bytes, engine, name=f"{i + 1}/{len(images)}")
            images[i] = None                                   # 읽은 사진은 바로 놓아준다
            pages.append(page["rows"])
            infos.append({k: v for k, v in page.items() if k != "rows"})
            _update(job_id, 읽음=i + 1, 사진=list(infos))
        _update(job_id, 상태=DONE, 결과={**finish(pages), "사진": infos}, 끝난시각=time.time())
    except Exception as e:                                     # 작업 스레드에서 조용히 사라지지 않게
        log.exception("작업 %s 실패", job_id)
        _update(job_id, 상태=FAILED, 오류=str(e) or type(e).__name__, 끝난시각=time.time())


def _forget_old():
    now = time.time()
    with _lock:
        for job_id in [j for j, job in _jobs.items()
                       if job.get("끝난시각") and now - job["끝난시각"] > JOB_TTL_SECONDS]:
            del _jobs[job_id]


def submit(images: list, engine: str, finish) -> str:
    """사진 바이트 목록을 작업으로 맡긴다. finish(페이지별 rows 목록) -> 검토 결과 dict."""
    _forget_old()
    job_id = uuid.uuid4().hex
    with _lock:
        _jobs[job_id] = {"id": job_id, "상태": WAITING, "전체": len(images), "읽음": 0,
                         "사진": [], "결과": None, "오류": None, "끝난시각": None}
    _executor.submit(_run, job_id, list(images), engine, finish)
    return job_id


def status(job_id: str):
    """작업 상태의 복사본. 없으면 None."""
    with _lock:
        job = _jobs.get(job_id)
        return None if job is None else {k: v for k, v in job.items() if k != "끝난시각"}
