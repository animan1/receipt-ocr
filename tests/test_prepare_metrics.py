import json
import shutil
from pathlib import Path

import numpy as np

from tests.approaches import load_approaches
from tests.evaluate_prepare import ANNOTATION_PATH, evaluate
from tests.fixture_cases import FIXTURES
from tests.prepare_metrics import Geometry, Preparation, Reference, boundary_error, score
from tests.prepare_summary import write_summary


def test_crop_scores_distinguish_background_from_lost_content() -> None:
    scene = np.full((100, 100, 3), (30, 100, 180), dtype=np.uint8)
    scene[20:80, 20:80] = 245
    outline = [(0.20, 0.20), (0.80, 0.20), (0.80, 0.80), (0.20, 0.80)]
    reference = Reference(outline, {"total": (0.55, 0.70, 0.75, 0.78)}, [])

    wide = score(scene, reference, Geometry((0, 0, 100, 100), 0, outline))
    tight = score(scene, reference, Geometry((20, 20, 80, 70), 0, outline))

    assert wide["retained_background_pct"] == 64
    assert wide["paper_lost_pct"] == 0
    assert wide["colored_border_pct"] == 100
    assert tight["retained_background_pct"] == 0
    assert tight["paper_lost_pct"] == 16.67
    assert tight["protected_regions_clipped"] == ["total"]
    assert boundary_error(outline, (100, 100)) == [0, 0]


def prepare_at_angle(source: Path, *, rotation: float) -> Preparation:
    return Preparation(source.read_bytes(), Geometry((0, 0, 540, 486), rotation, []))


def prepare_image_only(source: Path) -> bytes:
    return source.read_bytes()


def test_comparison_runs_multiple_configured_methods_with_parameters(tmp_path: Path) -> None:
    label = tmp_path / ANNOTATION_PATH / "example-shop.json"
    label.parent.mkdir(parents=True)
    shutil.copyfile(FIXTURES / ANNOTATION_PATH / label.name, label)
    relative_source = json.loads(label.read_text(encoding="utf-8"))["input"]
    source = tmp_path / relative_source
    source.parent.mkdir(parents=True)
    shutil.copyfile(FIXTURES / relative_source, source)
    config = tmp_path / "approaches.json"
    config.write_text(
        json.dumps(
            [
                {
                    "name": "opencv",
                    "method": "tests.backend_prepare:prepare_for_scoring",
                    "params": {"backend": "opencv"},
                },
                {
                    "name": "zero",
                    "method": "tests.test_prepare_metrics:prepare_at_angle",
                    "params": {"rotation": 0},
                },
                {
                    "name": "rotate",
                    "method": "tests.test_prepare_metrics:prepare_at_angle",
                    "params": {"rotation": -7},
                },
                {"name": "image-only", "method": "tests.test_prepare_metrics:prepare_image_only"},
            ]
        ),
        encoding="utf-8",
    )

    approaches = load_approaches(config)
    labeled, has_label = evaluate("example-shop", source, tmp_path, approaches)
    unlabeled, no_label = evaluate("without-label", source, tmp_path, approaches)
    assert has_label and not no_label

    debug = tmp_path / "debug"
    report = json.loads((debug / "example-shop-01-quality.json").read_text(encoding="utf-8"))
    assert report["baseline"] == "opencv"
    assert list(report["results"]) == ["opencv", "zero", "rotate", "image-only"]
    assert report["results"]["image-only"]["scores"] is None
    zero = report["results"]["zero"]["scores"]["median_abs_row_residual_degrees"]
    rotated = report["results"]["rotate"]["scores"]["median_abs_row_residual_degrees"]
    assert rotated < 0.2 < zero
    for method in report["results"]:
        assert (debug / f"example-shop-01-{method}-prepared.png").is_file()
        assert not (debug / f"without-label-01-{method}-prepared.png").exists()

    write_summary(debug, [approach.name for approach in approaches], [labeled, unlabeled], 1)
    summary = json.loads((debug / "all-01-quality.json").read_text(encoding="utf-8"))
    assert summary["image_cases"] == 2
    assert summary["annotated_cases"] == 1
    by_metric = {(row["metric"], row["approach"]): row for row in summary["metrics"]}
    assert by_metric["colored_border_pct", "zero"]["paired_cases"] == 2
    assert by_metric["retained_background_pct", "zero"]["paired_cases"] == 1
    assert by_metric["retained_background_pct", "zero"]["regressed"] == 1
    assert by_metric["paper_lost_pct", "zero"]["tied"] == 1
    assert by_metric["colored_border_pct", "image-only"]["cases_measured"] == 0
