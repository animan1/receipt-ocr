"""Adapt the library's preparation backends and diagnostics for scoring."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from receipt_ocr.prepare import Backend, prepare_image
from tests.prepare_metrics import Geometry, Preparation


def prepare_for_scoring(source: Path, *, backend: Backend, chroma_cap: float = 22) -> Preparation:
    with TemporaryDirectory() as directory:
        scratch = Path(directory)
        png = prepare_image(source, debug_dir=scratch, backend=backend, chroma_cap=chroma_cap)
        report = json.loads((scratch / "report.json").read_text(encoding="utf-8"))
    width, height = report["line_overlay_size_px"]
    geometry = Geometry(
        tuple(report["crop_box_px"]),
        report["applied_rotation_degrees"],
        [(x / max(1, width - 1), y / max(1, height - 1)) for x, y in report["paper_outline_px"]],
    )
    return Preparation(png, geometry)
