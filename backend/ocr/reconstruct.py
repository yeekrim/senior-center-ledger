"""OCR 응답(fields[].inferText + boundingPoly)을 한 줄 텍스트 리스트로 재구성.

OCR 엔진은 단어(토큰) 단위 bbox를 반환하므로, 같은 줄에 속한 토큰끼리 묶고
그 안에서 x좌표 순으로 정렬해 원래 통장 사진의 줄 순서를 복원한다.
복원된 줄은 passbook.lines.parse_line()이 기대하는 원시 OCR 줄 텍스트와
동일한 형태다.

줄을 나누는 기준 두 가지:
  - 비교 대상은 '줄의 첫 토큰'이 아니라 '직전 토큰'이다. 사진이 조금 기울면
    한 줄 안에서도 y가 서서히 내려가는데, 첫 토큰에 기준을 고정하면 오차가
    누적돼 한 거래가 중간에서 두 줄로 쪼개진다.
  - 허용치는 픽셀 절대값이 아니라 토큰 높이에 비례한다. 같은 통장이라도
    사진 해상도에 따라 글자 크기가 몇 배씩 달라지므로, 고정값을 쓰면
    고해상도 사진에서 한 줄이 잘게 쪼개지고 저해상도에서 여러 줄이 뭉친다.

한계: 한 줄을 가로지르는 y 낙차가 줄 간격보다 커질 만큼 심하게 기운 사진은
y좌표만으로 줄을 가를 수 없다(행끼리 서로 끼어든다). 그 경우는 기울기를
추정해 좌표를 회전시키는 보정이 따로 필요하며, 실사진을 확보한 뒤 다룬다.
"""

Y_TOLERANCE_RATIO = 0.6  # 같은 줄로 볼 y 낙차 = 토큰 높이 × 이 비율
MIN_Y_TOLERANCE = 4      # 높이를 못 구할 때(꼭짓점 부족 등) 쓰는 하한


def _vertices(field):
    return field["boundingPoly"]["vertices"]


def _top_y(field):
    return min(v["y"] for v in _vertices(field))


def _left_x(field):
    return min(v["x"] for v in _vertices(field))


def _height(field):
    ys = [v["y"] for v in _vertices(field)]
    return max(ys) - min(ys)


def _line_tolerance(fields):
    """토큰 높이의 중앙값에서 허용치를 잡는다(일부 토큰이 비정상이어도 흔들리지 않게)."""
    heights = sorted(_height(f) for f in fields)
    median = heights[len(heights) // 2]
    return max(median * Y_TOLERANCE_RATIO, MIN_Y_TOLERANCE)


def fields_to_lines(ocr_response: dict) -> list:
    fields = ocr_response["images"][0]["fields"]
    if not fields:
        return []

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

    lines = []
    for line_fields in grouped:
        line_fields.sort(key=_left_x)
        lines.append(" ".join(f["inferText"] for f in line_fields))
    return lines
