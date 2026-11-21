# Receipt extraction pipeline

Accept one document and return zero or more normalized receipt records, with source evidence and review issues. A file can contain multiple receipts or payment groups.

## Stages and entry points

| Stage | Responsibility | Output |
| --- | --- | --- |
| Prepare image | Render if needed, orient, deskew, correct perspective, and clean up pixels. | A sanitized image |
| Observe | Read embedded text or recognize text from a prepared image. Read the whole page or locate and read regions such as headers, item tables, and totals. | Text and optional geometry, reading order, and recognition confidence |
| Structure | Recover rows, cells, tables, and labeled regions from observations, or read them directly from a structured input. | Structured evidence with source locations |
| Interpret | Group evidence into receipts and propose fields, items, and adjustments. Use layout cues or explicit schema mappings where available. | Candidate receipt records with evidence links |
| Resolve | Normalize values, reconcile amounts, and resolve competing candidates. Return partial records with review issues when evidence is missing or conflicting. | A document result with normalized records and issues |

Routing chooses the first useful stage per file, page, or region. Image preparation ends with a sanitized raster. Text recognition begins in **Observe**. A mixed PDF can send scanned pages through image preparation and supply embedded text directly for other pages. A CSV normally enters at **Structure** with named cells and row references. A recognized CSV schema can emit candidates directly at **Interpret**, including one record per payment group.

Implementations can cover one stage or several. A table reader can emit structured evidence directly. A whole-document parser can provide observations, structured evidence, or candidate receipt records in one call. For image inputs, these capabilities operate on the prepared image. Adapt each output to the earliest downstream boundary that can consume it. Routing can try another implementation when evidence is unusable. Every candidate goes through **Resolve**.

## Example fixtures

These synthetic fixtures follow one tilted receipt through the stage boundaries.

| Stage | Example input | Example output |
| --- | --- | --- |
| Prepare image | [Tilted receipt](../tests/fixtures/pipeline/example-shop/receipt.png) | [Sanitized raster](../tests/fixtures/pipeline/example-shop/prepared.png) |
| Observe | [Sanitized raster](../tests/fixtures/pipeline/example-shop/prepared.png) | [Positioned text spans](../tests/fixtures/pipeline/example-shop/observed.json) |
| Structure | [Positioned text spans](../tests/fixtures/pipeline/example-shop/observed.json) | [Header, item table, and summary rows](../tests/fixtures/pipeline/example-shop/structured.json) |
| Interpret | [Structured evidence](../tests/fixtures/pipeline/example-shop/structured.json) | [Receipt candidate with evidence links](../tests/fixtures/pipeline/example-shop/candidate.json) |
| Resolve | [Receipt candidate](../tests/fixtures/pipeline/example-shop/candidate.json) | [Normalized receipt with review status](../tests/fixtures/pipeline/example-shop/result.json) |

## Shared contracts

- **Evidence** retains the original text or cell value and the most precise source location available. Use page and bounding box for positioned content, row and column for structured input, and page or document for coarser evidence. Normalize boxes to a top-left origin and coordinates from 0 to 1 in the image or page being read. Geometry and confidence are optional.
- **Candidates** associate field values and item rows with their supporting evidence. Preserve alternatives when their differences matter. Keep format handling, layout rules, and schema mappings in the components that understand them.
- **Results** use a normalized merchant name, typed dates, and exact decimal amounts with currency when known. Keep items, discounts, taxes, fees, printed totals, and payments distinct. Preserve signs and repeated items. Distinguish observed values from derived values and leave unresolved fields unset.
- **Issues** identify the affected field, item, or source unit and give a stable reason. A result can be complete, need review, or fail at the file level. Reconciliation can rule out inconsistent candidates. A balanced sum alone cannot establish a missing item.

The caller handles ledger matching, account assignment, and posting. Those workflows can use the receipt result and its evidence independently of how extraction was implemented.

## Evaluating implementations

Run implementations on the same fixture bytes and score their normalized results. Keep reference labels, including ledger-derived labels, available to the evaluator. Report improvements and regressions by fixture and field against the accepted baseline. Record deliberate output changes in the suite’s baseline for review, using the companion checkout for private cases.
