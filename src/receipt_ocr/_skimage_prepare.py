"""Crop and deskew paper using brightness and chroma."""

import io
import json
from dataclasses import dataclass
from importlib import import_module
from math import atan2, ceil, degrees, floor
from pathlib import Path
from statistics import median

import numpy as np
from numpy.typing import NDArray
from PIL import Image, ImageDraw, ImageOps

Raster = NDArray[np.uint8]
Point = tuple[int, int]


@dataclass(frozen=True)
class Analysis:
    thumbnail: Raster
    crop: tuple[int, int, int, int]
    outline: list[tuple[float, float]]
    lines: list[tuple[Point, Point, float]]
    angle: float | None = None
    rotation: float = 0.0


def _analyze(image: Raster, chroma_cap: float) -> Analysis:
    color = import_module("skimage.color")
    feature = import_module("skimage.feature")
    filters = import_module("skimage.filters")
    measure = import_module("skimage.measure")
    morphology = import_module("skimage.morphology")
    transform = import_module("skimage.transform")

    height, width = image.shape[:2]
    scale = min(1.0, 1200 / max(width, height))
    rows, columns = max(2, round(height * scale)), max(2, round(width * scale))
    rgb = transform.resize(image, (rows, columns), anti_aliasing=True)
    thumbnail = np.rint(rgb * 255).astype(np.uint8)
    gray = color.rgb2gray(rgb)
    chroma = np.linalg.norm(color.rgb2lab(rgb)[..., 1:], axis=-1)
    chroma_limit = float(np.clip(filters.threshold_otsu(chroma), 12, chroma_cap))
    brightness = min(float(filters.threshold_otsu(gray)), float(np.quantile(gray, 0.9)) * 0.8)
    foreground = (gray >= brightness) & (chroma <= chroma_limit)
    closed = morphology.closing(foreground, morphology.footprint_rectangle((9, 9)))
    region = max(
        measure.regionprops(measure.label(closed)), key=lambda item: item.area, default=None
    )
    if region is None or region.area < 0.05 * foreground.size:
        return Analysis(thumbnail, (0, 0, width, height), [], [])

    top, left, bottom, right = region.bbox
    paper = np.zeros(foreground.shape, dtype=bool)
    paper[top:bottom, left:right] = region.image_filled
    contour = max(measure.find_contours(np.pad(paper, 1), 0.5), key=len) - 1
    outline = [
        (float(np.clip(x, 0, columns - 1)), float(np.clip(y, 0, rows - 1))) for y, x in contour
    ]
    edges = feature.canny(gray, mask=morphology.erosion(paper), sigma=1)
    candidates = transform.probabilistic_hough_line(
        edges,
        threshold=20,
        line_length=max(16, (right - left) // 9),
        line_gap=max(4, (right - left) // 35),
        rng=0,
    )
    lines: list[tuple[Point, Point, float]] = []
    for start, end in candidates:
        x1, y1 = start
        x2, y2 = end
        angle = (degrees(atan2(y2 - y1, x2 - x1)) + 90) % 180 - 90
        if abs(angle) <= 15:
            lines.append(((int(x1), int(y1)), (int(x2), int(y2)), angle))

    pad = ceil(0.04 * min(right - left, bottom - top))
    crop = (
        max(0, floor((left - pad) * width / columns)),
        max(0, floor((top - pad) * height / rows)),
        min(width, ceil((right + pad) * width / columns)),
        min(height, ceil((bottom + pad) * height / rows)),
    )
    if len(lines) >= 2:
        center = median(line[2] for line in lines)
        agreeing = [line[2] for line in lines if abs(line[2] - center) <= 1.5]
        if len(agreeing) * 2 > len(lines):
            angle = median(agreeing)
            return Analysis(
                thumbnail, crop, outline, lines, angle, angle if abs(center) >= 0.35 else 0
            )
    return Analysis(thumbnail, crop, outline, lines)


def _write_debug(
    directory: Path, image: Raster, prepared: Raster, analysis: Analysis, chroma_cap: float
) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    overlay = Image.fromarray(analysis.thumbnail)
    draw = ImageDraw.Draw(overlay)
    if analysis.outline:
        draw.line(analysis.outline, fill="#1ec8f0", width=2)
    segments = []
    for start, end, angle in analysis.lines:
        supports = analysis.angle is not None and abs(angle - analysis.angle) <= 1.5
        draw.line((start, end), fill="#3cb423" if supports else "#ff8c00", width=2)
        segments.append({"start": start, "end": end, "angle": angle, "supports_estimate": supports})
    overlay.save(directory / "lines.png")
    residual = _analyze(prepared, chroma_cap).angle if analysis.rotation else analysis.angle
    if analysis.rotation:
        reason = "deskewed"
    elif analysis.angle is not None:
        reason = "already_level"
    elif analysis.outline:
        reason = "insufficient_lines" if len(analysis.lines) < 2 else "inconsistent_lines"
    else:
        reason = "no_receipt_region"
    report = {
        "backend": "scikit-image",
        "decoded_size_px": image.shape[:2][::-1],
        "prepared_size_px": prepared.shape[:2][::-1],
        "line_overlay_size_px": overlay.size,
        "crop_box_px": analysis.crop,
        "paper_outline_px": analysis.outline,
        "estimated_skew_degrees": analysis.angle,
        "applied_rotation_degrees": analysis.rotation,
        "residual_skew_degrees": residual,
        "reason": reason,
        "segments": segments,
    }
    (directory / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


def prepare_with_skimage(source: Path, *, debug_dir: Path | None, chroma_cap: float) -> bytes:
    try:
        with Image.open(source) as original:
            image = np.asarray(ImageOps.exif_transpose(original).convert("RGB"))
    except OSError as error:
        raise ValueError(f"Could not read receipt image: {source}") from error
    analysis = _analyze(image, chroma_cap)
    left, top, right, bottom = analysis.crop
    prepared = image[top:bottom, left:right]
    if analysis.rotation:
        transform = import_module("skimage.transform")
        prepared = np.rint(
            transform.rotate(
                prepared, analysis.rotation, resize=True, cval=255, preserve_range=True
            )
        ).astype(np.uint8)
    if debug_dir is not None:
        _write_debug(debug_dir, image, prepared, analysis, chroma_cap)
    output = io.BytesIO()
    Image.fromarray(prepared).save(output, format="PNG")
    return output.getvalue()
