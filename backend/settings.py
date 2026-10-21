"""환경 변수로 바꿀 수 있는 설정을 한 곳에 모은다.

값을 그렇게 정한 이유는 쓰는 곳(reading.py, server.py)의 주석에 있다. 측정 결과에 따라
바뀔 수 있는 값이라 코드를 고치지 않고 바꿀 수 있게 했다.

  LEDGER_READ_SIZES           OCR을 시도할 크기(긴 변 px). 쉼표로 구분, '원본'은 줄이지 않음. 기본 1400,원본
  LEDGER_RETRY_BELOW          잔액이 맞은 이음매 비율이 이보다 낮으면 다음 크기로 다시 읽는다. 기본 0.5
  LEDGER_PAGE_BUDGET_SECONDS  사진 한 장의 목표 시간. 넘으면 경고 로그. 기본 15
  LEDGER_PRELOAD_OCR          0이면 서버를 켤 때 OCR 모델을 미리 불러오지 않는다. 기본 1
  LEDGER_GPU_SIZES            GPU(M1 · CUDA)로 읽을 크기. READ_SIZES와 같은 형식, 비우면 GPU를 쓰지 않음. 기본 원본
"""

import os

ORIGINAL = "원본"


def parse_sizes(raw: str) -> tuple:
    """'1400,원본' -> (1400, None). None은 원본 크기."""
    sizes = []
    for part in (p.strip() for p in raw.split(",")):
        if part == ORIGINAL:
            sizes.append(None)
        elif part.isdigit() and int(part) > 0:
            sizes.append(int(part))
        else:
            raise ValueError(f"LEDGER_READ_SIZES의 '{part}'를 읽을 수 없습니다. 양의 정수나 '{ORIGINAL}'을 쉼표로 구분해 주세요.")
    if not sizes:
        raise ValueError("LEDGER_READ_SIZES가 비어 있습니다.")
    return tuple(sizes)


def _ratio(name: str, default: str) -> float:
    value = float(os.environ.get(name, default))
    if not 0 <= value <= 1:
        raise ValueError(f"{name}는 0과 1 사이여야 합니다: {value}")
    return value


READ_SIZES = parse_sizes(os.environ.get("LEDGER_READ_SIZES", f"1400,{ORIGINAL}"))
RETRY_BELOW = _ratio("LEDGER_RETRY_BELOW", "0.5")
PAGE_BUDGET_SECONDS = float(os.environ.get("LEDGER_PAGE_BUDGET_SECONDS", "15"))
PRELOAD_OCR = os.environ.get("LEDGER_PRELOAD_OCR", "1") != "0"
_gpu_sizes = os.environ.get("LEDGER_GPU_SIZES", ORIGINAL).strip()
GPU_SIZES = parse_sizes(_gpu_sizes) if _gpu_sizes else ()
