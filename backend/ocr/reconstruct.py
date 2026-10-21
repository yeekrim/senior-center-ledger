"""OCR 응답(fields[].inferText + boundingPoly)을 한 줄 텍스트 리스트로 재구성.

OCR 엔진은 단어(토큰) 단위 bbox를 반환하므로, 같은 줄에 속한 토큰끼리 묶고
그 안에서 x좌표 순으로 정렬해 원래 통장 사진의 줄 순서를 복원한다.
복원된 줄은 passbook.lines.parse_line()이 기대하는 원시 OCR 줄 텍스트와
동일한 형태다.

거래 줄은 날짜를 기준점으로 묶는다:
  1) 왼쪽 날짜 칸에서 날짜처럼 생긴 토큰을 찾아 거래마다 기준점을 하나씩 둔다.
  2) 기준점 사이 간격이 크게 벌어진 곳(통장이 접힌 곳)에서 페이지를 나눈다.
     위아래 페이지는 접힘 때문에 기운 방향이 서로 다를 수 있다.
  3) 페이지마다 기울기를 찾는다. 여러 각도로 토큰의 y를 보정해 보고, 토큰들이
     기준점에 가장 가깝게 모이는 각도를 고른다.
  4) 토큰마다 보정한 y가 가장 가까운 기준점의 줄에 넣는다. 어느 기준점과도
     멀면(머리글 · 안내문 · 날짜를 못 읽은 거래) 아래의 이어 붙이기 방식으로 따로 묶는다.

이어 붙이기 방식(날짜 기준점이 2개 미만일 때, 그리고 남은 토큰에 쓴다)은 y로 정렬한 뒤
'직전 토큰과 y가 가까우면 같은 줄'로 잇는다. 줄 간격이 촘촘하고 토큰이 여러 칸에 흩어진
통장에서는 이웃한 줄의 토큰이 사슬처럼 이어져 거래 여러 개가 한 줄로 합쳐진다. 실제 통장
사진 6장으로 재 보니 이 방식은 거래 6줄을 다른 줄과 합쳤고, 날짜 기준으로 바꾸자 0줄이 됐고
정답과 맞은 거래가 71행 중 37행에서 43행으로 늘었다(같은 OCR 결과에 줄 복원만 바꿔서 잼).

허용치는 픽셀 절대값이 아니라 토큰 높이 · 줄 간격에 비례한다. 같은 통장이라도 사진
해상도에 따라 글자 크기가 몇 배씩 달라지므로, 고정값을 쓰면 해상도마다 결과가 달라진다.
"""

import math
import re
from statistics import median

Y_TOLERANCE_RATIO = 0.6  # 이어 붙이기: 같은 줄로 볼 y 낙차 = 토큰 높이 × 이 비율
MIN_Y_TOLERANCE = 4      # 높이를 못 구할 때(꼭짓점 부족 등) 쓰는 하한

# 날짜 기준점. 2개 미만이면 줄 간격을 알 수 없어 이어 붙이기 방식으로 돌아간다.
MIN_ANCHORS = 2
# 날짜 칸 폭: 기준점 후보의 왼쪽 x가 후보들의 중앙값에서 페이지 폭의 이 비율 안에 있어야 한다.
# 내역 칸에 날짜처럼 생긴 숫자가 있어도 기준점으로 쓰지 않으려고.
DATE_COLUMN_RATIO = 0.15
# 같은 줄에서 날짜가 두 번 잡히면(행번호가 붙은 조각 등) 하나로 본다. 토큰 높이 × 이 비율.
DUPLICATE_ANCHOR_RATIO = 0.5
# 기준점 간격이 보통 줄 간격의 이 배수보다 크면 페이지가 바뀐 것으로 본다(접힌 곳).
PAGE_GAP_RATIO = 2.5
# 토큰이 기준점에서 줄 간격의 이 비율보다 멀면 그 거래 줄이 아니다.
ANCHOR_REACH_RATIO = 0.5
# 기준점이 하나뿐인 페이지는 줄 간격을 잴 수 없어 토큰 높이 × 이 비율로 가정한다.
SINGLE_ROW_STEP_RATIO = 1.5
# 기울기를 찾는 범위(도)와 간격. 실제 사진 6장은 모두 ±2도 안이었다.
MAX_SKEW_DEGREES = 5.0
SKEW_STEP_DEGREES = 0.1

# 통장 거래 날짜(YYYYMMDD). 0을 O · D로, 1을 I · l로 읽는 흔한 오독은 숫자로 보고 찾는다.
_DATE = re.compile(r"20\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])")
_DATE_CONFUSABLE = str.maketrans({"O": "0", "o": "0", "D": "0", "I": "1", "l": "1"})


def _vertices(field):
    return field["boundingPoly"]["vertices"]


def _top_y(field):
    return min(v["y"] for v in _vertices(field))


def _left_x(field):
    return min(v["x"] for v in _vertices(field))


def _height(field):
    ys = [v["y"] for v in _vertices(field)]
    return max(ys) - min(ys)


def _center(field):
    xs = [v["x"] for v in _vertices(field)]
    ys = [v["y"] for v in _vertices(field)]
    return (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2


def _line_tolerance(fields):
    """토큰 높이의 중앙값에서 허용치를 잡는다(일부 토큰이 비정상이어도 흔들리지 않게)."""
    heights = sorted(_height(f) for f in fields)
    median_height = heights[len(heights) // 2]
    return max(median_height * Y_TOLERANCE_RATIO, MIN_Y_TOLERANCE)


def _chain_groups(fields):
    """이어 붙이기 방식. 비교 대상은 '줄의 첫 토큰'이 아니라 '직전 토큰'이다.

    사진이 조금 기울면 한 줄 안에서도 y가 서서히 내려가는데, 첫 토큰에 기준을 고정하면
    오차가 누적돼 한 거래가 중간에서 두 줄로 쪼개진다.
    """
    fields = sorted(fields, key=_top_y)
    tolerance = _line_tolerance(fields)

    grouped = []
    current_line = [fields[0]]
    for field in fields[1:]:
        if abs(_top_y(field) - _top_y(current_line[-1])) <= tolerance:
            current_line.append(field)
        else:
            grouped.append(current_line)
            current_line = [field]
    grouped.append(current_line)
    return grouped


def _join(line_fields):
    return " ".join(f["inferText"] for f in sorted(line_fields, key=_left_x))


def _looks_like_date(field) -> bool:
    digits = re.sub(r"[^\dOoDIl]", "", field["inferText"]).translate(_DATE_CONFUSABLE)
    return bool(_DATE.search(digits))


def _find_anchors(fields):
    """날짜 칸에 있는 날짜 토큰을 위에서부터 거래마다 하나씩 고른다."""
    candidates = [f for f in fields if _looks_like_date(f)]
    if not candidates:
        return []
    width = max(_left_x(f) for f in fields) - min(_left_x(f) for f in fields)
    column = median(_left_x(f) for f in candidates)
    candidates = [f for f in candidates if abs(_left_x(f) - column) <= width * DATE_COLUMN_RATIO]

    duplicate = median(_height(f) for f in fields) * DUPLICATE_ANCHOR_RATIO
    anchors = []
    for field in sorted(candidates, key=lambda f: _center(f)[1]):
        if anchors and _center(field)[1] - _center(anchors[-1])[1] < duplicate:
            continue
        anchors.append(field)
    return anchors


def _split_pages(anchors):
    """기준점 간격이 보통 줄 간격보다 크게 벌어진 곳에서 나눈다."""
    if len(anchors) < 3:
        return [anchors]
    gaps = [_center(b)[1] - _center(a)[1] for a, b in zip(anchors, anchors[1:])]
    usual = median(gaps)
    pages, current = [], [anchors[0]]
    for anchor, gap in zip(anchors[1:], gaps):
        if gap > usual * PAGE_GAP_RATIO:
            pages.append(current)
            current = []
        current.append(anchor)
    pages.append(current)
    return pages


def _nearest(fields, anchors, slope, reach):
    """기울기 slope로 y를 보정했을 때, 토큰마다 (가장 가까운 기준점 또는 None, 거리)."""
    anchor_ys = []
    for a in anchors:
        x, y = _center(a)
        anchor_ys.append((y - x * slope, a))
    result = []
    for field in fields:
        x, y = _center(field)
        corrected = y - x * slope
        distance, anchor = min(((abs(corrected - ay), a) for ay, a in anchor_ys), key=lambda t: t[0])
        result.append((anchor if distance <= reach else None, min(distance, reach)))
    return result


def _best_slope(fields, anchors, reach):
    """토큰들이 기준점에 가장 가깝게 모이는 기울기. 멀리 떨어진 토큰은 reach로 잘라 영향을 줄인다."""
    steps = round(MAX_SKEW_DEGREES / SKEW_STEP_DEGREES)
    best = None
    for i in range(-steps, steps + 1):
        slope = math.tan(math.radians(i * SKEW_STEP_DEGREES))
        cost = sum(d for _, d in _nearest(fields, anchors, slope, reach))
        if best is None or cost < best[0]:
            best = (cost, slope)
    return best[1]


def _anchor_lines(fields, anchors):
    """기준점마다 한 줄. 반환: [(줄의 y, 토큰 목록)]과 어느 줄에도 들지 않은 토큰."""
    rows = {id(a): [] for a in anchors}
    leftovers = []
    pages = _split_pages(anchors)
    row_height = median(_height(f) for f in fields)

    for i, page in enumerate(pages):
        # 페이지 경계는 이웃한 두 페이지의 끝 기준점 사이 한가운데로 잡는다.
        top = (_center(pages[i - 1][-1])[1] + _center(page[0])[1]) / 2 if i else -math.inf
        bottom = (_center(page[-1])[1] + _center(pages[i + 1][0])[1]) / 2 if i + 1 < len(pages) else math.inf
        mine = [f for f in fields if top <= _center(f)[1] < bottom]
        if len(page) > 1:
            step = median(_center(b)[1] - _center(a)[1] for a, b in zip(page, page[1:]))
        else:
            step = row_height * SINGLE_ROW_STEP_RATIO
        reach = step * ANCHOR_REACH_RATIO

        slope = _best_slope(mine, page, reach)
        for field, (anchor, _) in zip(mine, _nearest(mine, page, slope, reach)):
            (rows[id(anchor)] if anchor is not None else leftovers).append(field)

    return [(_center(a)[1], rows[id(a)]) for a in anchors], leftovers


def fields_to_lines(ocr_response: dict) -> list:
    fields = ocr_response["images"][0]["fields"]
    if not fields:
        return []

    anchors = _find_anchors(fields)
    if len(anchors) < MIN_ANCHORS:
        return [_join(group) for group in _chain_groups(fields)]

    lines, leftovers = _anchor_lines(fields, anchors)
    if leftovers:
        # 남은 토큰은 이어 붙이기로 묶고, 묶음의 y 자리에 끼워 넣어 위아래 순서를 지킨다.
        lines += [(median(_center(f)[1] for f in group), group) for group in _chain_groups(leftovers)]
    lines.sort(key=lambda line: line[0])
    return [_join(group) for _, group in lines]
