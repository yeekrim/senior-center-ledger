"""OCR 전처리: 사진에서 통장 영역만 잘라낸다.

휴대폰으로 찍은 사진은 통장이 프레임의 일부만 차지하고 배경(이불·책상 등)이
함께 들어간다. 인식에 쓸 해상도가 배경에 낭비되고, 배경 무늬가 글자로 오인될
수도 있다.

배경을 가정하지 않는 것이 이 모듈의 설계 목표다. '통장은 배경보다 밝다'로
기준을 잡으면 어두운 이불 위에서는 되지만 흰 책상 위에서는 무너진다. 그래서
밝기 대신 **글자가 있는 곳이 문서다**를 기준으로 삼는다:

  글자 판정: 작은 커널의 형태학적 그래디언트로 미세한 획을 뽑고, 가로 방향으로
  닫아 '가로로 이어지는 획 덩어리'만 남긴다. 인쇄된 글줄은 이 패턴을 만들지만
  이불 무늬·나무결·장판은 만들지 않는다. 배경 색과 무관하게 성립한다.

후보 영역은 서로 다른 전제로 여러 개 만든 뒤(밝은 문서 / 어두운 문서 / 배경색과
다른 영역 / 글줄이 모인 영역), 공통 잣대로 점수를 매겨 가장 좋은 것을 고른다:

  점수 = (영역이 담아낸 글줄 비율) - (영역이 차지하는 면적 비율 × 벌점)

글줄을 거의 다 담으면서 가장 작은 영역이 이긴다. 어떤 후보도 기준을 못 넘으면
자르지 않고 원본을 돌려준다 — 잘못 잘라 거래 행을 잃는 것보다 안전하다.

원근 변환(기울어진 사진을 정면으로 펴기)은 넣지 않았다. 네 꼭짓점을 잘못 잡으면
거래 행이 통째로 일그러지는데, reconstruct.py가 완만한 기울기는 이미 흡수한다.

이미지는 메모리에서만 다루고 디스크에 쓰지 않는다.
"""

import io

import cv2
import numpy as np
from PIL import Image, ImageOps

DETECT_WIDTH = 1000          # 검출은 축소본에서 (속도)
MIN_COMPONENT_RATIO = 0.01   # 이보다 작은 덩어리는 잡음으로 본다
MIN_AREA_RATIO = 0.12        # 후보 영역 최소 크기
MAX_AREA_RATIO = 0.97        # 이보다 크면 '사실상 안 자른 것'이라 후보로 치지 않는다
MIN_TEXT_CAPTURE = 0.90      # 글줄을 이만큼은 담아야 한다
AREA_PENALTY = 0.35          # 면적에 매기는 벌점
MARGIN_RATIO = 0.02          # 잘라낼 때 사방에 남기는 여유
BORDER_SAMPLE_RATIO = 0.04   # 배경색을 추정할 때 쓰는 테두리 두께
LAB_DISTANCE_MIN = 12        # 배경색과 '다르다'고 볼 최소 색차 (Lab, 8비트 척도)


def shrink(image_bytes: bytes, long_side: int) -> bytes:
    """EXIF 회전을 적용하고 긴 변이 long_side를 넘지 않게 줄인다(메모리 안에서만).

    휴대폰 원본(4032px)을 그대로 OCR하면 CPU에서 사진 한 장에 70초 남짓 걸린다.
    실사진으로 잰 결과 1400px로 줄이면 8초 안팎으로 빨라진다. 다만 사진에 따라 거래를
    놓치기도 해서, 다시 읽을지는 reading.py가 정한다. 회전을 먼저 적용하는 것이 중요하다 — 빠뜨리면
    통장이 옆으로 누운 채 OCR에 들어가 거래를 한 줄도 읽지 못한다.
    """
    pil = ImageOps.exif_transpose(Image.open(io.BytesIO(image_bytes))).convert("RGB")
    if max(pil.size) > long_side:
        pil.thumbnail((long_side, long_side), Image.LANCZOS)
    buf = io.BytesIO()
    pil.save(buf, format="JPEG", quality=92)
    return buf.getvalue()


def _load_bgr(image_bytes: bytes) -> np.ndarray:
    """EXIF 회전을 반영해 디코딩한다."""
    pil = ImageOps.exif_transpose(Image.open(io.BytesIO(image_bytes))).convert("RGB")
    return cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)


def _encode(image: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".png", image)
    if not ok:
        raise RuntimeError("이미지 인코딩 실패")
    return buf.tobytes()


def _text_line_mask(gray: np.ndarray) -> np.ndarray:
    """가로로 이어지는 미세한 획(=인쇄된 글줄)만 남긴 마스크.

    배경의 천 무늬나 나무결은 사방으로 흩어진 굵은 무늬라 가로 닫기 연산에서
    긴 덩어리를 만들지 못한다.
    """
    gradient = cv2.morphologyEx(gray, cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8))
    _, binary = cv2.threshold(gradient, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    closed = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, np.ones((1, 25), np.uint8))

    count, labels, stats, _ = cv2.connectedComponentsWithStats(closed, 8)
    mask = np.zeros_like(closed)
    for i in range(1, count):
        w, h = stats[i][cv2.CC_STAT_WIDTH], stats[i][cv2.CC_STAT_HEIGHT]
        if w >= 25 and w >= h * 2:      # 가로로 긴 덩어리 = 글줄
            mask[labels == i] = 255
    return mask


def _union_bbox(mask: np.ndarray, frame_area: int):
    """마스크의 큰 덩어리들을 모두 감싸는 바운딩 박스.

    통장은 가운데 접힌 부분의 그림자 때문에 위/아래 페이지가 서로 다른 덩어리로
    검출된다. 가장 큰 덩어리 하나만 쓰면 한 페이지가 잘려나가므로 합쳐서 잡는다.
    """
    count, _, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    boxes = [stats[i] for i in range(1, count)
             if stats[i][cv2.CC_STAT_AREA] >= frame_area * MIN_COMPONENT_RATIO]
    if not boxes:
        return None
    return (min(b[cv2.CC_STAT_LEFT] for b in boxes),
            min(b[cv2.CC_STAT_TOP] for b in boxes),
            max(b[cv2.CC_STAT_LEFT] + b[cv2.CC_STAT_WIDTH] for b in boxes),
            max(b[cv2.CC_STAT_TOP] + b[cv2.CC_STAT_HEIGHT] for b in boxes))


def _background_difference(bgr: np.ndarray) -> np.ndarray:
    """사진 테두리를 배경 표본으로 삼아, 배경색과 다른 픽셀을 남긴다.

    배경이 어둡든 밝든 '테두리는 배경'이라는 가정만 쓰므로 색에 중립적이다.

    색차를 0~255로 정규화하면 안 된다. 검정 글자가 배경과 극단적으로 달라서
    최대값을 독점하고, 정작 구분해야 할 '종이 대 배경'의 차이가 0 근처로
    눌린다. 절대 색차에 고정 문턱을 쓰고, 종이 안쪽의 배경색과 비슷한 여백은
    닫기 연산으로 메워 문서를 하나의 덩어리로 만든다.
    """
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB).astype(np.float32)
    h, w = lab.shape[:2]
    t = max(1, int(min(h, w) * BORDER_SAMPLE_RATIO))
    border = np.concatenate([
        lab[:t].reshape(-1, 3), lab[-t:].reshape(-1, 3),
        lab[:, :t].reshape(-1, 3), lab[:, -t:].reshape(-1, 3),
    ])
    distance = np.linalg.norm(lab - np.median(border, axis=0), axis=2)
    mask = (distance >= LAB_DISTANCE_MIN).astype(np.uint8) * 255
    return cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((41, 41), np.uint8))


def _candidate_masks(bgr: np.ndarray, gray: np.ndarray, text: np.ndarray):
    """서로 다른 전제로 만든 후보 마스크들. 하나가 실패해도 다른 것이 받쳐준다."""
    blurred = cv2.GaussianBlur(gray, (9, 9), 0)
    _, bright = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    open_kernel = np.ones((31, 31), np.uint8)
    return [
        cv2.morphologyEx(bright, cv2.MORPH_OPEN, open_kernel),                  # 문서가 밝을 때
        cv2.morphologyEx(255 - bright, cv2.MORPH_OPEN, open_kernel),            # 문서가 어두울 때
        cv2.morphologyEx(_background_difference(bgr), cv2.MORPH_OPEN, open_kernel),
        cv2.dilate(text, np.ones((45, 45), np.uint8)),                          # 글줄이 모인 영역
    ]


def _score(bbox, text: np.ndarray, frame_area: int):
    """글줄을 많이 담을수록 좋고, 넓게 잡을수록 손해."""
    x0, y0, x1, y1 = bbox
    area = (x1 - x0) * (y1 - y0)
    if not (frame_area * MIN_AREA_RATIO <= area <= frame_area * MAX_AREA_RATIO):
        return None

    total = int(text.sum())
    if total == 0:
        return None
    capture = int(text[y0:y1, x0:x1].sum()) / total
    if capture < MIN_TEXT_CAPTURE:
        return None
    return capture - AREA_PENALTY * (area / frame_area)


def _document_bbox(bgr: np.ndarray, gray: np.ndarray):
    frame_area = gray.shape[0] * gray.shape[1]
    text = _text_line_mask(gray)

    best, best_score = None, None
    for mask in _candidate_masks(bgr, gray, text):
        bbox = _union_bbox(mask, frame_area)
        if bbox is None:
            continue
        score = _score(bbox, text, frame_area)
        if score is not None and (best_score is None or score > best_score):
            best, best_score = bbox, score
    return best


def crop_document(image_bytes: bytes) -> bytes:
    """통장 영역만 잘라낸 이미지를 PNG 바이트로 반환한다.

    통장을 찾지 못하면 EXIF 회전만 반영한 원본을 돌려준다.
    """
    image = _load_bgr(image_bytes)
    height, width = image.shape[:2]
    scale = DETECT_WIDTH / width
    small = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)

    bbox = _document_bbox(small, cv2.cvtColor(small, cv2.COLOR_BGR2GRAY))
    if bbox is None:
        return _encode(image)

    x0, y0, x1, y1 = (int(v / scale) for v in bbox)
    mx = int((x1 - x0) * MARGIN_RATIO)
    my = int((y1 - y0) * MARGIN_RATIO)
    x0, y0 = max(0, x0 - mx), max(0, y0 - my)
    x1, y1 = min(width, x1 + mx), min(height, y1 + my)

    return _encode(image[y0:y1, x0:x1])
