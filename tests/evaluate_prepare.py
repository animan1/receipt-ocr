"""Compare configured image preparation approaches across the receipt corpus."""

import argparse
import json
from dataclasses import asdict
from pathlib import Path

import cv2

from tests.approaches import Approach, load_approaches
from tests.fixture_cases import FIXTURES, discover_images
from tests.fixture_repository import private_fixture_root
from tests.prepare_metrics import Preparation, Reference, score
from tests.prepare_summary import CaseScores, write_summary

ANNOTATION_PATH = Path("annotations") / "prepare-image"


def evaluate(
    fixture_id: str, source: Path, root: Path, approaches: list[Approach]
) -> tuple[CaseScores, bool]:
    label = root / ANNOTATION_PATH / f"{fixture_id}.json"
    reference = None
    provenance = None
    if label.is_file():
        label_data = json.loads(label.read_text(encoding="utf-8"))
        if (root / label_data["input"]).resolve() != source.resolve():
            raise ValueError(f"Quality label points to a different fixture: {label}")
        reference = Reference(
            label_data["outline"], label_data["protected"], label_data["text_rows"]
        )
        provenance = label_data.get("provenance")
    image = cv2.imread(str(source), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"Could not read fixture image: {source}")

    debug = root / "debug"
    debug.mkdir(parents=True, exist_ok=True)
    results = {}
    case_scores: CaseScores = {}
    for approach in approaches:
        output = approach.run(source, **approach.params)
        if not isinstance(output, (bytes, Preparation)):
            raise TypeError(f"{approach.name!r} must return PNG bytes or a Preparation.")
        prepared = Preparation(output) if isinstance(output, bytes) else output
        geometry = prepared.geometry
        values = score(image, reference, geometry) if geometry is not None else None
        case_scores[approach.name] = values
        if reference is not None:
            image_path = debug / f"{fixture_id}-01-{approach.name}-prepared.png"
            image_path.write_bytes(prepared.png)
        results[approach.name] = {
            "method": approach.method,
            "params": approach.params,
            "geometry": asdict(geometry) if geometry is not None else None,
            "scores": values,
        }

    report = debug / f"{fixture_id}-01-quality.json"
    report.write_text(
        json.dumps(
            {
                "fixture_id": fixture_id,
                "reference": provenance,
                "baseline": approaches[0].name,
                "results": results,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return case_scores, reference is not None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--approaches", type=Path, required=True)
    args = parser.parse_args()
    approaches = load_approaches(args.approaches)
    private = private_fixture_root()
    images = discover_images(FIXTURES, private)
    cases = []
    annotated = 0
    for number, (fixture_id, source) in enumerate(sorted(images.items()), start=1):
        root = FIXTURES if source.is_relative_to(FIXTURES) else private
        scores, labeled = evaluate(fixture_id, source, root, approaches)
        cases.append(scores)
        annotated += labeled
        if number % 10 == 0 or number == len(images):
            print(f"Compared {number}/{len(images)} fixtures", flush=True)
    report = write_summary(
        FIXTURES / "debug", [approach.name for approach in approaches], cases, annotated
    )
    print(report)


if __name__ == "__main__":
    main()
