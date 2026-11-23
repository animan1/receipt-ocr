# Receipt fixtures

Run `make test` to discover and validate shared and local fixtures in one suite. A fresh checkout runs the shared cases without private data. During development the suite checks fixture integrity and label structure.

- Put shareable cases under `tests/fixtures/inputs/` and `tests/fixtures/outputs/`. A companion fixture checkout uses the same paths. Without a companion checkout, private cases can use those paths under the ignored `.local/` directory.
- Use the same filename stem for a receipt and its JSON label, such as `inputs/synthetic-order.csv` and `outputs/synthetic-order.json`. Both sides are discovered across the two roots, so you can work on a pair across directories locally. Commit both halves of a shared case so it runs from a clean checkout. Duplicate input or output IDs and unpaired fixtures fail collection.
- For manual additions, add the matching files. The optional generated `tests/fixtures/manifest.json` in the fixture checkout supplies checksums and original basenames for imported inputs.

From the library checkout, run `git config --local receipt-ocr.fixturesRepo ../private-receipts-fixtures` to use a sibling fixture repository. Absolute paths work too. Then run `make hooks` to install the pre-push guard for this checkout. The guard blocks library pushes when the configured fixture checkout has staged, unstaged, or untracked changes, or when Git cannot inspect it. Confirm the fixture checkout is clean with `git -C ../private-receipts-fixtures status --short`. A checkout with no configured companion keeps the shared suite and any ignored local fixtures available.
- `receipt_records` holds transcribed receipt records. For recognized CSV exports these are payment groups and item rows. Use `null` when there is no document-level transcription yet.

The private corpus includes every visible file in the supplied receipt archive. After `make setup`, run `make prepare-dev ARCHIVE="/path/to/_Imported" BOOK="/path/to/books.sqlite.gnucash"` to import it. The importer copies the original bytes, uses opaque filenames, and reads the GnuCash database in read-only mode. Pass only the opaque input paths to extraction engines.

The scorer can use `references.archive_filename` as a provisional merchant, receipt date, and total label. It can use `references.ledger_payment` to compare the recorded payment amount and currency. The ledger posting date is included for matching and can differ from the receipt date. Missing references are `null`. Amounts are decimal strings.

The fixture reader needs no account paths, ledger identifiers, or accounting splits. Keep the generated files local until a reviewable subset has been selected and checked for release. Preparing the corpus again regenerates the manifest and automatic labels, so keep reviewed transcriptions separately from these generated labels.

## Pipeline stages

Keep stage-by-stage cases in `pipeline/<case>/`, alongside the paired corpus directories. The [pipeline proposal](../../docs/pipeline.md#example-fixtures) links the images and intermediate outputs for `example-shop`.

Run `make test` to generate preparation diagnostics for every raster fixture in the shared and available private corpora. For a stage-by-stage case, name its original image `receipt.<extension>`. Use `make test PREPARE_FIXTURE=<image fixture ID>` to limit preparation to one image. CSVs and PDFs still participate in the paired fixture checks.

Artifacts go directly in the fixture owner's `tests/fixtures/debug/`, named `<fixture-id>-<stage-number>-<artifact>`. For example, Prepare image writes `example-shop-01-prepared.png`, `example-shop-01-lines.png`, and `example-shop-01-report.json`. Keep the debug directory ignored in both repositories.

## Preparation quality

Run `make setup` and `make evaluate-prepare` to compare scikit-image and OpenCV on the image fixtures in both repositories. Pass `APPROACHES=/path/to/approaches.json` to compare a different set of implementations or parameter values. The [default configuration](../prepare_approaches.json) lists a name, a `module:callable`, and optional keyword arguments for each approach. The first is the baseline.

Each callable accepts the source path and configured keyword arguments and returns PNG bytes. It can also return `Preparation(png, geometry)` to enable scoring. The geometry contains the half-open crop box in decoded source pixels, the applied rotation in degrees counterclockwise, and the paper outline in normalized source coordinates. When the callable supplies only a raster, the report leaves its geometry scores unavailable.

Open `tests/fixtures/debug/all-01-quality.md` in the library checkout for medians, coverage, and paired wins, ties, and losses. The JSON summary is alongside it. Each case gets a `<fixture-id>-01-quality.json` report in its fixture owner's debug directory. For labeled cases the runner also saves one prepared raster per approach.

Keep hand-authored reference labels under `annotations/prepare-image/<fixture-id>.json` in Git. Use normalized coordinates in the decoded input for the visible paper outline, protected text boxes, and left-to-right text row segments. The comparison reads these labels and writes its generated reports under `debug/`. The report measures retained background and omitted paper against the outline, flags clipped protected boxes, and reports remaining border color, deviations along each long side, and residual tilt on the annotated rows. View the measures separately when reviewing tradeoffs.

## Observe quality

Install Tesseract with English language data (`brew install tesseract` on macOS or `sudo apt install tesseract-ocr tesseract-ocr-eng` on Debian/Ubuntu). Run `make setup OBSERVE=1` for RapidOCR and ONNX Runtime. The locked ONNX Runtime has Python 3.12 wheels for Apple Silicon on macOS 14+ and glibc Linux on x86-64 and ARM64. Run `make evaluate-observe` for the available image fixtures or `make evaluate-observe OBSERVE_FIXTURE=example-shop` for one case. Use `OBSERVE_APPROACHES=/path/to/approaches.json` to select callables and keyword arguments. Each callable receives the same prepared PNG bytes and returns a `receipt_ocr.observe.Observation`. The first approach is the comparison baseline.

Open `tests/fixtures/debug/all-02-quality.md` in the library checkout for aggregate scores and paired wins, ties, and losses. Single-fixture runs use the fixture ID in the summary filename. The fixture owner's flat debug directory contains the prepared input, a box overlay and normalized JSON for each approach. Confidence comes from the engine and is useful when inspecting individual spans.

Keep reviewed labels in `annotations/observe/<fixture-id>.json`. Use the original fixture's path relative to its fixture root for `input`. Supply a full visible `transcript` for character error in engine reading order after whitespace normalization. Omit it for partial labels. Annotate `regions` on `<fixture-id>-02-input.png` in normalized top-left coordinates and use `date`, `amount`, or `text` for `kind`. A region is detected when a span covers at least one quarter of its area. Date and amount checks require an exact printed token in the overlapping text. Verify region boxes again when image preparation changes.
