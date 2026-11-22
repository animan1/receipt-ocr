"""Prepare a receipt raster and optionally save diagnostics."""

import argparse
from collections.abc import Sequence
from pathlib import Path
from typing import Literal

from receipt_ocr._skimage_prepare import prepare_with_skimage

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
        from receipt_ocr._opencv_prepare import prepare_image as prepare_with_opencv

        return prepare_with_opencv(source, debug_dir=debug_dir)
    return prepare_with_skimage(source, debug_dir=debug_dir, chroma_cap=chroma_cap)


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Receipt image")
    parser.add_argument(
        "--output-dir", type=Path, required=True, help="Save PNG and diagnostics here"
    )
    parser.add_argument("--backend", choices=("scikit-image", "opencv"), default=DEFAULT_BACKEND)
    args = parser.parse_args(argv)
    output_dir: Path = args.output_dir
    source: Path = args.source
    output = output_dir / "prepared.png"
    if source.resolve() == output.resolve():
        parser.error("Choose an output directory that will preserve the source image.")
    png = prepare_image(source, debug_dir=output_dir, backend=args.backend)
    output.write_bytes(png)
