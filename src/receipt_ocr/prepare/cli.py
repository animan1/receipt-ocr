"""Prepare a receipt raster and optionally save diagnostics."""

import argparse
from collections.abc import Sequence
from pathlib import Path

from receipt_ocr.prepare import DEFAULT_BACKEND, prepare_image


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
