"""pipeline.py — 크기에 따라 OCR 장치를 고른다.

약속: GPU_SIZES에 든 크기만 GPU로 읽고, 나머지는 CPU로 읽는다.
"""

import io

from PIL import Image

import ocr.pipeline as pipeline


def jpeg(size=(300, 400)):
    buf = io.BytesIO()
    Image.new("RGB", size, "white").save(buf, format="JPEG")
    return buf.getvalue()


def test_GPU_크기만_GPU로_읽는다(monkeypatch):
    used = []
    monkeypatch.setitem(pipeline.ENGINES, "easyocr",
                        lambda image, gpu=False: used.append(gpu) or {"images": [{"fields": []}]})
    monkeypatch.setattr(pipeline, "GPU_SIZES", (None,))

    pipeline.run_ocr_pipeline(jpeg(), long_side=1400)
    pipeline.run_ocr_pipeline(jpeg(), long_side=None)
    assert used == [False, True]


def test_GPU_크기를_비우면_GPU를_쓰지_않는다(monkeypatch):
    used = []
    monkeypatch.setitem(pipeline.ENGINES, "easyocr",
                        lambda image, gpu=False: used.append(gpu) or {"images": [{"fields": []}]})
    monkeypatch.setattr(pipeline, "GPU_SIZES", ())

    pipeline.run_ocr_pipeline(jpeg(), long_side=None)
    assert used == [False]
