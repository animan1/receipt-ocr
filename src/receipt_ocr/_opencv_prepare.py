"""Prepare a receipt raster for reading and optionally save deskew diagnostics."""

import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from math import atan2, ceil, cos, degrees, floor, radians, sin
from pathlib import Path
from statistics import median

import cv2
from cv2.typing import MatLike

ANALYSIS_LIMIT = 1600
MAX_SKEW = 15.0
ANGLE_TOLERANCE = 1.5
MIN_CORRECTION = 0.35


@dataclass(frozen=True)
class Segment:
    start: tuple[int, int]
    end: tuple[int, int]
    angle: float


@dataclass(frozen=True)
class Deskew:
    angle: float | None
    rotation: float
    reason: str
    inliers: tuple[Segment, ...] = ()


@dataclass(frozen=True)
class Analysis:
    image: MatLike
    paper: MatLike | None
    segments: list[Segment]
    deskew: Deskew


def _dimensions(image: MatLike) -> tuple[int, int]:
    return int(image.shape[1]), int(image.shape[0])


def _analysis_image(image: MatLike) -> MatLike:
    width, height = _dimensions(image)
    if max(width, height) <= ANALYSIS_LIMIT:
        return image
    scale = ANALYSIS_LIMIT / max(width, height)
    return cv2.resize(
        image,
        (max(1, round(width * scale)), max(1, round(height * scale))),
        interpolation=cv2.INTER_AREA,
    )


def _paper_contour(gray: MatLike) -> MatLike | None:
    _, bright = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 15))
    closed = cv2.morphologyEx(bright, cv2.MORPH_CLOSE, kernel)
    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    paper = max(contours, key=cv2.contourArea)
    area = cv2.contourArea(paper)
    width, height = _dimensions(gray)
    _, _, paper_width, paper_height = cv2.boundingRect(paper)
    if area < width * height * 0.05 or area < paper_width * paper_height * 0.55:
        return None
    return paper


def _detect_segments(gray: MatLike, paper: MatLike) -> list[Segment]:
    _, _, width, _ = cv2.boundingRect(paper)
    edges = cv2.Canny(gray, 60, 160)
    mask = gray.copy()
    mask[:] = 0
    cv2.drawContours(mask, [paper], -1, 255, cv2.FILLED)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    interior = cv2.erode(mask, kernel)
    lines = cv2.HoughLinesP(
        cv2.bitwise_and(edges, interior),
        rho=1,
        theta=radians(0.5),
        threshold=25,
        minLineLength=max(16, width // 9),
        maxLineGap=max(4, width // 35),
    )
    if lines is None:
        return []
    segments = []
    for detected in lines.reshape(-1, 4):
        x1, y1, x2, y2 = map(int, detected)
        angle = (degrees(atan2(y2 - y1, x2 - x1)) + 90) % 180 - 90
        if abs(angle) <= MAX_SKEW:
            segments.append(Segment((x1, y1), (x2, y2), angle))
    return segments


def _choose_deskew(segments: Sequence[Segment]) -> Deskew:
    if len(segments) < 2:
        return Deskew(None, 0, "insufficient_lines")
    center = median(segment.angle for segment in segments)
    inliers = tuple(
        segment for segment in segments if abs(segment.angle - center) <= ANGLE_TOLERANCE
    )
    if len(inliers) * 2 <= len(segments):
        return Deskew(None, 0, "inconsistent_lines")
    angle = median(segment.angle for segment in inliers)
    if abs(angle) < MIN_CORRECTION:
        return Deskew(angle, 0, "already_level", inliers)
    return Deskew(angle, angle, "deskewed", inliers)


def _analyze(image: MatLike) -> Analysis:
    scaled = _analysis_image(image)
    gray = cv2.cvtColor(scaled, cv2.COLOR_BGR2GRAY)
    paper = _paper_contour(gray)
    if paper is None:
        return Analysis(scaled, None, [], Deskew(None, 0, "no_receipt_region"))
    segments = _detect_segments(gray, paper)
    return Analysis(scaled, paper, segments, _choose_deskew(segments))


def _crop_box(image: MatLike, analysis: Analysis) -> tuple[int, int, int, int]:
    width, height = _dimensions(image)
    if analysis.paper is None:
        return 0, 0, width, height
    analyzed_width, analyzed_height = _dimensions(analysis.image)
    x, y, paper_width, paper_height = cv2.boundingRect(analysis.paper)
    padding = ceil(0.04 * min(paper_width, paper_height))
    scale_x, scale_y = width / analyzed_width, height / analyzed_height
    return (
        max(0, floor((x - padding) * scale_x)),
        max(0, floor((y - padding) * scale_y)),
        min(width, ceil((x + paper_width + padding) * scale_x)),
        min(height, ceil((y + paper_height + padding) * scale_y)),
    )


def _rotate(image: MatLike, angle: float) -> MatLike:
    if not angle:
        return image
    width, height = _dimensions(image)
    cx, cy = width / 2, height / 2
    rotation = radians(angle)
    out_width = ceil(width * abs(cos(rotation)) + height * abs(sin(rotation)))
    out_height = ceil(width * abs(sin(rotation)) + height * abs(cos(rotation)))
    matrix = cv2.getRotationMatrix2D((cx, cy), angle, 1)
    matrix[0, 2] += out_width / 2 - cx
    matrix[1, 2] += out_height / 2 - cy
    return cv2.warpAffine(image, matrix, (out_width, out_height), borderValue=(255, 255, 255))


def _png(image: MatLike) -> bytes:
    ok, png = cv2.imencode(".png", image)
    if not ok:
        raise ValueError("Could not encode the prepared image as PNG.")
    return png.tobytes()


def _write_debug(
    directory: Path,
    original: MatLike,
    analysis: Analysis,
    prepared: MatLike,
    crop_box: tuple[int, int, int, int],
) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    overlay = analysis.image.copy()
    if analysis.paper is not None:
        cv2.drawContours(overlay, [analysis.paper], -1, (240, 200, 30), 2)
    deskew = analysis.deskew
    inliers = set(deskew.inliers)
    residual = _analyze(prepared).deskew if deskew.rotation else deskew
    for segment in analysis.segments:
        color = (35, 180, 60) if segment in inliers else (0, 140, 255)
        cv2.line(overlay, segment.start, segment.end, color, 2, cv2.LINE_AA)
    report = {
        "backend": "opencv",
        "opencv_version": cv2.__version__,
        "decoded_size_px": _dimensions(original),
        "prepared_size_px": _dimensions(prepared),
        "crop_box_px": crop_box,
        "line_overlay_size_px": _dimensions(overlay),
        "paper_outline_px": (
            analysis.paper.reshape(-1, 2).tolist() if analysis.paper is not None else []
        ),
        "estimated_skew_degrees": deskew.angle,
        "applied_rotation_degrees": deskew.rotation,
        "residual_skew_degrees": residual.angle,
        "reason": deskew.reason,
        "segments": [
            {**asdict(segment), "supports_estimate": segment in inliers}
            for segment in analysis.segments
        ],
    }
    (directory / "lines.png").write_bytes(_png(overlay))
    (directory / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


def prepare_image(source: Path, *, debug_dir: Path | None = None) -> bytes:
    """Return a prepared PNG. Line detection uses a scaled copy of the source image."""
    image = cv2.imread(str(source), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"Could not read receipt image: {source}")
    analysis = _analyze(image)
    crop_box = _crop_box(image, analysis)
    left, top, right, bottom = crop_box
    prepared = _rotate(image[top:bottom, left:right], analysis.deskew.rotation)
    if debug_dir is not None:
        _write_debug(debug_dir, image, analysis, prepared, crop_box)
    return _png(prepared)
