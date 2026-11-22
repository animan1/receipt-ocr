"""Prepare a receipt raster and optionally save diagnostics."""

from pathlib import Path
from typing import Literal

from receipt_ocr.prepare.impl.skimage import prepare_with_skimage

Backend = Literal["scikit-image", "opencv"]
DEFAULT_BACKEND: Backend = "scikit-image"


def prepare_image(
    source: Path,
    *,
    debug_dir: Path | None = None,
    backend: Backend = DEFAULT_BACKEND,
    chroma_cap: float = 22,
) -> bytes:
    """Return a prepared raster as PNG bytes."""
    if debug_dir is not None and source.resolve() in {
        (debug_dir / "lines.png").resolve(),
        (debug_dir / "report.json").resolve(),
    }:
        raise ValueError("Choose a debug directory that will preserve the source image.")
    if backend == "opencv":
        from receipt_ocr.prepare.impl.opencv import prepare_image as prepare_with_opencv

        return prepare_with_opencv(source, debug_dir=debug_dir)
    return prepare_with_skimage(source, debug_dir=debug_dir, chroma_cap=chroma_cap)
