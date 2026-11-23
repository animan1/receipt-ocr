"""Compare OCR approaches on identical prepared receipt rasters."""

import argparse
import io
import json
from dataclasses import asdict
from pathlib import Path
from statistics import median

from PIL import Image, ImageDraw

from receipt_ocr.observe import Box, Observation
from receipt_ocr.prepare import prepare_image
from tests.approaches import Approach, load_approaches
from tests.fixture_cases import FIXTURES, discover_images
from tests.fixture_repository import private_fixture_root
from tests.observe_metrics import METRICS, Region, score

ANNOTATION_PATH = Path("annotations") / "observe"
CaseScores = dict[str, dict[str, float]]


def _write_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _overlay(png: bytes, observation: Observation, output: Path) -> None:
    with Image.open(io.BytesIO(png)) as decoded:
        image = decoded.convert("RGB")
    draw = ImageDraw.Draw(image)
    for span in observation.spans:
        if span.box is None:
            continue
        box = span.box
        left, top = box.left * image.width, box.top * image.height
        draw.rectangle(
            (left, top, box.right * image.width, box.bottom * image.height), outline="cyan", width=2
        )
        draw.text(
            (left, max(0, top - 12)), span.id, fill="cyan", stroke_width=1, stroke_fill="black"
        )
    image.save(output)


def evaluate(fixture_id: str, source: Path, root: Path, approaches: list[Approach]) -> CaseScores:
    reference = root / ANNOTATION_PATH / f"{fixture_id}.json"
    label = json.loads(reference.read_text(encoding="utf-8")) if reference.is_file() else {}
    if label and (root / label["input"]).resolve() != source.resolve():
        raise ValueError(f"Observe annotation points to a different fixture: {reference}")
    regions = [
        Region(row["id"], row["kind"], row["text"], Box(**row["box"]))
        for row in label.get("regions", [])
    ]
    png = prepare_image(source)
    debug = root / "debug"
    debug.mkdir(parents=True, exist_ok=True)
    (debug / f"{fixture_id}-02-input.png").write_bytes(png)
    scores = {}
    for approach in approaches:
        output = approach.run(png, **approach.params)
        if not isinstance(output, Observation):
            raise TypeError(f"{approach.name!r} must return an Observation.")
        metrics, details = score(output, label.get("transcript", ""), regions)
        scores[approach.name] = metrics
        prefix = f"{fixture_id}-02-{approach.name}"
        _overlay(png, output, debug / f"{prefix}-boxes.png")
        _write_json(
            debug / f"{prefix}-observed.json",
            {
                **asdict(output),
                "method": approach.method,
                "params": approach.params,
                "metrics": metrics,
                "regions": details,
            },
        )
    return scores


def write_summary(
    debug: Path, methods: list[str], cases: dict[str, CaseScores], *, scope: str = "all"
) -> Path:
    baseline = methods[0]
    rows = []
    metrics = []
    for key, label in METRICS.items():
        for method in methods:
            scores = [case[method][key] for case in cases.values() if key in case[method]]
            if not scores:
                continue
            deltas = [
                case[method][key] - case[baseline][key]
                for case in cases.values()
                if method != baseline and key in case[method] and key in case[baseline]
            ]
            counts = (
                sum(d < 0 for d in deltas),
                sum(d == 0 for d in deltas),
                sum(d > 0 for d in deltas),
            )
            paired = " / ".join(map(str, counts)) if deltas else "—"
            center = median(scores)
            affected = sum(value > 0 for value in scores)
            metrics.append(
                {
                    "metric": key,
                    "approach": method,
                    "cases_measured": len(scores),
                    "cases_with_errors": affected,
                    "median": center,
                    "paired_cases": len(deltas),
                    "improved": counts[0],
                    "tied": counts[1],
                    "regressed": counts[2],
                }
            )
            rows.append(
                f"| {label} | {method} | {len(scores)} | {affected} | {center:.2f} | {paired} |"
            )

    debug.mkdir(parents=True, exist_ok=True)
    prefix = f"{scope}-02-quality"
    _write_json(
        debug / f"{prefix}.json", {"baseline": baseline, "metrics": metrics, "cases": cases}
    )
    path = debug / f"{prefix}.md"
    path.write_text(
        "\n".join(
            [
                "# Observe quality",
                "",
                f"Compared {len(cases)} image fixtures against `{baseline}`.",
                "Lower is better. Paired counts use cases measured by both approaches.",
                "Only labeled cases contribute transcription and region scores.",
                "",
                "| Metric | Approach | Cases measured | Cases with errors | Median | Improved / tied / regressed |",
                "| --- | --- | ---: | ---: | ---: | ---: |",
                *rows,
                "",
            ]
        ),
        encoding="utf-8",
    )
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--approaches", type=Path, required=True)
    parser.add_argument("--fixture", help="Compare a single fixture ID")
    args = parser.parse_args()
    approaches = load_approaches(args.approaches)
    private = private_fixture_root()
    images = discover_images(FIXTURES, private)
    if args.fixture:
        if args.fixture not in images:
            parser.error(f"Unknown image fixture {args.fixture!r}.")
        images = {args.fixture: images[args.fixture]}
    cases = {}
    for number, (fixture_id, source) in enumerate(sorted(images.items()), start=1):
        root = FIXTURES if source.is_relative_to(FIXTURES) else private
        cases[fixture_id] = evaluate(fixture_id, source, root, approaches)
        if number % 10 == 0 or number == len(images):
            print(f"Compared {number}/{len(images)} fixtures", flush=True)
    print(
        write_summary(
            FIXTURES / "debug",
            [approach.name for approach in approaches],
            cases,
            scope=args.fixture or "all",
        )
    )


if __name__ == "__main__":
    main()
