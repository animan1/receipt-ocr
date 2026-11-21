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
