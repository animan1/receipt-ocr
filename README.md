# Receipt OCR

Python library for preparing receipt images for extraction.

Use Python 3.12 and `uv`. Run `make setup` to install the locked development dependencies, then `make check` to check formatting, lint, types, tests, and coverage. Run `make build` to produce a source distribution and wheel. Bare `make` lists featured commands. Run `make help-verbose` for the full list.

GitHub Actions runs the same checks on Linux and macOS.

The [fixture guide](tests/fixtures/README.md) explains how to add shared cases or use the private local corpus.

The [pipeline proposal](docs/pipeline.md) describes how receipt inputs become normalized records.

Run `make prepare-image INPUT=/path/to/receipt.jpg OUTPUT_DIR=.local/prepare-image/example` to prepare a raster with scikit-image. Add `BACKEND=opencv` to use the OpenCV alternative. The command writes `prepared.png`, `lines.png`, and `report.json`. The overlay outlines the detected paper in cyan. Green edges inside it support the estimated skew and orange edges were excluded from the estimate. The report gives the crop box in decoded pixels and the estimated skew before and after rotation. The crop keeps a margin around the detected paper, and rotation retains the full crop.

Licensed under [Apache 2.0](LICENSE).
