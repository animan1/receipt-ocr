import json
import shutil
from pathlib import Path

import cv2
import pytest

from receipt_ocr.prepare import Backend, prepare_image
from receipt_ocr.prepare.cli import main
from receipt_ocr.prepare.impl.opencv import Segment, _analyze, _choose_deskew
from tests.fixture_cases import FIXTURES, discover_images
from tests.fixture_repository import private_fixture_root

FIXTURE = FIXTURES / "pipeline" / "example-shop"


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    if "image_source" not in metafunc.fixturenames:
        return
    sources = discover_images(FIXTURES, private_fixture_root())
    fixture_id = metafunc.config.getoption("--prepare-fixture")
    if fixture_id:
        if fixture_id not in sources:
            raise pytest.UsageError(f"Expected an image fixture ID, got {fixture_id!r}")
        sources = {fixture_id: sources[fixture_id]}
    metafunc.parametrize(
        ("fixture_id", "image_source"),
        [pytest.param(case_id, path, id=case_id) for case_id, path in sorted(sources.items())],
    )


def test_cli_prepares_pipeline_fixture_and_writes_diagnostics(
    fixture_id: str, image_source: Path, tmp_path: Path
) -> None:
    original = image_source.resolve()
    root = FIXTURES if original.is_relative_to(FIXTURES) else private_fixture_root()
    main([str(original), "--output-dir", str(tmp_path)])

    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["backend"] == "scikit-image"
    overlay = cv2.imread(str(tmp_path / "lines.png"))
    prepared = cv2.imread(str(tmp_path / "prepared.png"))
    assert overlay is not None and prepared is not None
    assert list(overlay.shape[:2][::-1]) == report["line_overlay_size_px"]
    assert list(prepared.shape[:2][::-1]) == report["prepared_size_px"]
    width, height = report["decoded_size_px"]
    left, top, right, bottom = report["crop_box_px"]
    assert 0 <= left < right <= width
    assert 0 <= top < bottom <= height
    assert prepared.shape[1] >= right - left
    assert prepared.shape[0] >= bottom - top
    if original == FIXTURE / "receipt.png":
        assert left > 0 and top > 0 and right < width and bottom < height
        assert report["reason"] == "deskewed"
        assert report["estimated_skew_degrees"] == pytest.approx(-7, abs=1)
        assert report["applied_rotation_degrees"] == report["estimated_skew_degrees"]
        assert abs(report["residual_skew_degrees"]) < 0.35
        assert sum(segment["supports_estimate"] for segment in report["segments"]) >= 2

    debug_dir = root / "debug"
    debug_dir.mkdir(parents=True, exist_ok=True)
    for name in ("prepared.png", "lines.png", "report.json"):
        shutil.move(tmp_path / name, debug_dir / f"{fixture_id}-01-{name}")


def test_already_level_image_keeps_its_pixels(tmp_path: Path) -> None:
    source = FIXTURE / "prepared.png"
    output = tmp_path / "prepared.png"
    output.write_bytes(prepare_image(source))

    original = cv2.imread(str(source))
    prepared = cv2.imread(str(output))
    assert original is not None and prepared is not None
    assert cv2.norm(original, prepared, cv2.NORM_INF) == 0


def test_flat_image_has_no_skew_estimate_and_diagnostics_are_bounded(tmp_path: Path) -> None:
    source = tmp_path / "blank.png"
    gray = cv2.imread(str(FIXTURE / "prepared.png"))
    assert gray is not None
    gray[:] = 180
    assert cv2.imwrite(str(source), cv2.resize(gray, (2000, 1800)))

    prepare_image(source, debug_dir=tmp_path, backend="opencv")

    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["reason"] == "insufficient_lines"
    assert report["applied_rotation_degrees"] == 0
    assert report["estimated_skew_degrees"] is None
    assert report["segments"] == []
    assert report["decoded_size_px"] == report["prepared_size_px"] == [2000, 1800]
    assert report["line_overlay_size_px"] == [1600, 1440]


def test_conflicting_line_angles_leave_image_alone() -> None:
    segments = [Segment((0, 0), (100, 0), angle) for angle in (-10.0, 0.0, 10.0)]

    deskew = _choose_deskew(segments)

    assert deskew.reason == "inconsistent_lines"
    assert deskew.rotation == 0
    assert deskew.inliers == ()


def test_no_lines_with_opencv_none_result(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cv2, "HoughLinesP", lambda *args, **kwargs: None)
    image = cv2.imread(str(FIXTURE / "prepared.png"))
    assert image is not None
    assert _analyze(image).segments == []


def test_crop_and_rotation_use_receipt_over_background_lines(tmp_path: Path) -> None:
    paper = cv2.imread(str(FIXTURE / "prepared.png"))
    assert paper is not None
    height, width = paper.shape[:2]
    matrix = cv2.getRotationMatrix2D((width / 2, height / 2), 7, 1)
    matrix[0, 2] += 260
    matrix[1, 2] += 65
    scene = cv2.warpAffine(paper, matrix, (1000, 500), borderValue=(50, 50, 50))
    for y in range(30, 450, 12):
        cv2.line(scene, (20, y), (215, y + 20), (120, 120, 120), 3)
    source = tmp_path / "receipt.png"
    assert cv2.imwrite(str(source), scene)

    prepare_image(source, debug_dir=tmp_path, backend="opencv")

    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["applied_rotation_degrees"] == pytest.approx(-7, abs=1)
    left, top, right, bottom = report["crop_box_px"]
    assert 215 < left < 245 and 700 < right < 760
    assert top < 45 and bottom > 450
    assert all(
        segment["start"][0] > 215 and segment["end"][0] > 215 for segment in report["segments"]
    )


@pytest.mark.parametrize("with_small_patch", [False, True])
def test_uncertain_receipt_boundary_leaves_frame_unchanged(
    tmp_path: Path, with_small_patch: bool
) -> None:
    pixels = cv2.imread(str(FIXTURE / "prepared.png"))
    assert pixels is not None
    pixels[:] = 0
    if with_small_patch:
        pixels[80:110, 80:110] = 255
    source = tmp_path / "dark.png"
    assert cv2.imwrite(str(source), pixels)

    (tmp_path / "prepared.png").write_bytes(
        prepare_image(source, debug_dir=tmp_path, backend="opencv")
    )

    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["reason"] == "no_receipt_region"
    assert report["crop_box_px"] == [0, 0, pixels.shape[1], pixels.shape[0]]
    assert report["applied_rotation_degrees"] == 0
    prepared = cv2.imread(str(tmp_path / "prepared.png"))
    assert prepared is not None and cv2.norm(pixels, prepared, cv2.NORM_INF) == 0


@pytest.mark.parametrize("backend", ["opencv", "scikit-image"])
def test_unreadable_image_reports_an_error(tmp_path: Path, backend: Backend) -> None:
    source = tmp_path / "broken.png"
    source.write_text("invalid raster data", encoding="utf-8")
    with pytest.raises(ValueError, match="Could not read receipt image"):
        prepare_image(source, backend=backend)


def test_encoding_failure_reports_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_encoding(*args: object) -> tuple[bool, None]:
        return False, None

    monkeypatch.setattr(cv2, "imencode", fail_encoding)
    with pytest.raises(ValueError, match="Could not encode"):
        prepare_image(FIXTURE / "prepared.png", backend="opencv")


@pytest.mark.parametrize(
    ("color", "reason"),
    [((80, 80, 80), "insufficient_lines"), ((0, 0, 200), "no_receipt_region")],
)
def test_scikit_image_does_not_rotate_without_paper_evidence(
    tmp_path: Path, color: tuple[int, int, int], reason: str
) -> None:
    pixels = cv2.imread(str(FIXTURE / "prepared.png"))
    assert pixels is not None
    pixels[:] = color
    source = tmp_path / "scene.png"
    assert cv2.imwrite(str(source), pixels)

    prepare_image(source, debug_dir=tmp_path)

    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["reason"] == reason
    assert report["applied_rotation_degrees"] == 0


def test_scikit_image_reports_an_already_level_receipt(tmp_path: Path) -> None:
    prepare_image(FIXTURE / "prepared.png", debug_dir=tmp_path)

    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["reason"] == "already_level"
    assert report["applied_rotation_degrees"] == 0


def test_cli_refuses_to_overwrite_source(tmp_path: Path) -> None:
    source = tmp_path / "prepared.png"
    source.write_bytes((FIXTURE / "receipt.png").read_bytes())
    with pytest.raises(SystemExit) as error:
        main([str(source), "--output-dir", str(tmp_path)])
    assert error.value.code == 2
    assert source.read_bytes() == (FIXTURE / "receipt.png").read_bytes()


def test_debug_writes_preserve_source(tmp_path: Path) -> None:
    source = tmp_path / "lines.png"
    original = (FIXTURE / "receipt.png").read_bytes()
    source.write_bytes(original)
    with pytest.raises(ValueError, match="Choose a debug directory"):
        prepare_image(source, debug_dir=tmp_path)
    assert source.read_bytes() == original
