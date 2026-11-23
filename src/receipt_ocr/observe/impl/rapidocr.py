"""Read positioned text with RapidOCR's CPU inference engine."""

import io
from collections.abc import Sequence
from functools import lru_cache
from importlib import import_module
from typing import Protocol, cast

from PIL import Image

from receipt_ocr.observe import Box, Observation, Span


class _Result(Protocol):
    boxes: Sequence[Sequence[tuple[float, float]]] | None
    txts: Sequence[str] | None
    scores: Sequence[float] | None


class _Engine(Protocol):
    def __call__(self, image: bytes, *, use_cls: bool) -> _Result: ...


@lru_cache(maxsize=4)
def _engine(max_side_len: int) -> _Engine:
    try:
        rapidocr = import_module("rapidocr")
        import_module("onnxruntime")
    except ModuleNotFoundError as error:
        raise RuntimeError(
            "Run make setup OBSERVE=1 to install RapidOCR and ONNX Runtime."
        ) from error
    return cast(
        _Engine,
        rapidocr.RapidOCR(params={"Global.max_side_len": max_side_len, "Global.text_score": 0.0}),
    )


def observe(image: bytes, *, max_side_len: int = 2000) -> Observation:
    with Image.open(io.BytesIO(image)) as decoded:
        width, height = decoded.size
    result = _engine(max_side_len)(image, use_cls=False)
    boxes, texts, scores = result.boxes, result.txts, result.scores
    if boxes is None or texts is None or scores is None:
        return Observation(())
    spans: list[Span] = []
    for polygon, text, confidence in zip(boxes, texts, scores, strict=True):
        if not text.strip():
            continue
        xs, ys = zip(*polygon, strict=True)
        box = Box.from_pixels(
            float(min(xs)), float(min(ys)), float(max(xs)), float(max(ys)), width, height
        )
        spans.append(Span(f"s{len(spans) + 1}", text, box, float(confidence)))
    return Observation(tuple(spans))
