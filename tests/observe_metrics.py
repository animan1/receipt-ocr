"""Score observed text and geometry against human-authored reference labels."""

import re
from dataclasses import dataclass

from receipt_ocr.observe import Box, Observation

METRICS = {
    "empty_output": "Empty observation",
    "character_error_pct": "Character error (%)",
    "missed_regions": "Missed labeled regions",
    "date_errors": "Printed date errors",
    "amount_errors": "Printed amount errors",
}


@dataclass(frozen=True)
class Region:
    id: str
    kind: str
    text: str
    box: Box


def normalized(text: str) -> str:
    return " ".join(text.split())


def edit_distance(expected: str, actual: str) -> int:
    row = list(range(len(actual) + 1))
    for i, expected_char in enumerate(expected, start=1):
        previous, row[0] = row[0], i
        for j, actual_char in enumerate(actual, start=1):
            previous, row[j] = (
                row[j],
                min(row[j] + 1, row[j - 1] + 1, previous + (actual_char != expected_char)),
            )
    return row[-1]


def intersects(box: Box, region: Box) -> bool:
    width = max(0.0, min(box.right, region.right) - max(box.left, region.left))
    height = max(0.0, min(box.bottom, region.bottom) - max(box.top, region.top))
    return width * height >= 0.25 * (region.right - region.left) * (region.bottom - region.top)


def score(
    observation: Observation, transcript: str, regions: list[Region]
) -> tuple[dict[str, float], dict[str, dict[str, bool | str]]]:
    actual = normalized(" ".join(span.text for span in observation.spans))
    metrics: dict[str, float] = {"empty_output": float(not actual)}
    expected = normalized(transcript)
    if expected:
        metrics["character_error_pct"] = 100 * edit_distance(expected, actual) / len(expected)

    details: dict[str, dict[str, bool | str]] = {}
    geometry = [span for span in observation.spans if span.box is not None]
    if regions and (geometry or not actual):
        metrics["missed_regions"] = 0
        for region in regions:
            text = normalized(
                " ".join(
                    span.text
                    for span in geometry
                    if span.box is not None and intersects(span.box, region.box)
                )
            )
            token = re.escape(normalized(region.text))
            exact = re.search(rf"(?<![\w.,/$+−(-]){token}(?![\w.,/)])", text)
            details[region.id] = {"expected": region.text, "observed": text, "exact": bool(exact)}
            metrics["missed_regions"] += int(not text)
            if region.kind in {"date", "amount"}:
                key = f"{region.kind}_errors"
                metrics[key] = metrics.get(key, 0) + int(not exact)
    return metrics, details
