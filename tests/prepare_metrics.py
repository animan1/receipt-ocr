"""Score crop and deskew geometry against annotations in the decoded image."""

from dataclasses import dataclass
from math import atan2, degrees

import cv2
import numpy as np
from cv2.typing import MatLike
from numpy.typing import NDArray

Point = tuple[float, float]
Box = tuple[int, int, int, int]


@dataclass(frozen=True)
class Reference:
    outline: list[Point]
    protected: dict[str, tuple[float, float, float, float]]
    text_rows: list[tuple[Point, Point]]


@dataclass(frozen=True)
class Geometry:
    crop: Box
    rotation: float
    outline: list[Point]


@dataclass(frozen=True)
class Preparation:
    png: bytes
    geometry: Geometry | None = None


def polygon_mask(shape: tuple[int, int], outline: list[Point]) -> NDArray[np.uint8]:
    height, width = shape
    mask = np.zeros(shape, dtype=np.uint8)
    if outline:
        pixels = np.rint(np.array(outline) * (width - 1, height - 1)).astype(np.int32)
        cv2.fillPoly(mask, [pixels], 1)
    return mask


def boundary_error(outline: list[Point], shape: tuple[int, int]) -> list[float] | None:
    mask = polygon_mask(shape, outline)
    rows = np.flatnonzero(mask.any(axis=1))
    if rows.size < 10:
        return None
    # End cuts are often torn or incomplete. Fit each long side on the middle 80%.
    trim = rows.size // 10
    rows = rows[trim:-trim]
    left = mask[rows].argmax(axis=1)
    right = shape[1] - 1 - mask[rows, ::-1].argmax(axis=1)
    paper_width = max(1.0, float(np.median(right - left + 1)))
    errors = []
    for edge in (left, right):
        points = np.column_stack((edge, rows)).astype(np.float32)
        vx, vy, x, y = cv2.fitLine(points, cv2.DIST_HUBER, 0, 0.01, 0.01).ravel()
        distances = np.abs((edge - x) * vy - (rows - y) * vx)
        errors.append(round(float(np.percentile(distances, 90)) / paper_width * 100, 2))
    return errors


def score(image: MatLike, reference: Reference | None, geometry: Geometry) -> dict[str, object]:
    height, width = image.shape[:2]
    left, top, right, bottom = geometry.crop
    if not (0 <= left < right <= width and 0 <= top < bottom <= height):
        raise ValueError("Crop must be a nonempty box inside the decoded source.")
    border = max(1, round(0.05 * min(right - left, bottom - top)))
    crop = image[top:bottom, left:right]
    # Evaluate source pixels only. Rotation fill never enters the color score.
    pieces = (
        crop[:border],
        crop[-border:],
        crop[border:-border, :border],
        crop[border:-border, -border:],
    )
    border_pixels = np.concatenate([piece.reshape(-1, 3) for piece in pieces])
    lab = cv2.cvtColor(border_pixels.reshape(-1, 1, 3), cv2.COLOR_BGR2LAB)
    chroma = np.linalg.norm(lab[:, 0, 1:].astype(float) - 128, axis=1)
    scale = min(1.0, 800 / max(width, height))
    measurements: dict[str, object] = {
        "colored_border_pct": round(100 * float(np.mean(chroma > 18)), 2),
        "long_side_p90_error_pct": boundary_error(
            geometry.outline, (max(1, round(height * scale)), max(1, round(width * scale)))
        ),
    }
    if reference is None:
        return measurements
    return {**measurements, **_score_reference((height, width), reference, geometry)}


def _score_reference(
    shape: tuple[int, int], reference: Reference, geometry: Geometry
) -> dict[str, object]:
    height, width = shape
    left, top, right, bottom = geometry.crop
    expected = polygon_mask(shape, reference.outline)
    paper_pixels = int(expected.sum())
    if not paper_pixels:
        raise ValueError("The reference must contain a visible paper outline.")
    kept_paper = int(expected[top:bottom, left:right].sum())
    crop_area = (right - left) * (bottom - top)
    clipped = [
        name
        for name, (x1, y1, x2, y2) in reference.protected.items()
        if x1 * width < left or y1 * height < top or x2 * width > right or y2 * height > bottom
    ]
    residuals = [
        degrees(atan2((end[1] - start[1]) * height, (end[0] - start[0]) * width))
        - geometry.rotation
        for start, end in reference.text_rows
    ]
    return {
        "retained_background_pct": round(100 * (crop_area - kept_paper) / crop_area, 2),
        "paper_lost_pct": round(100 * (paper_pixels - kept_paper) / paper_pixels, 2),
        "protected_regions_clipped": clipped,
        "row_residual_degrees": [round(value, 2) for value in residuals],
        "median_abs_row_residual_degrees": (
            round(float(np.median(np.abs(residuals))), 2) if residuals else None
        ),
    }
