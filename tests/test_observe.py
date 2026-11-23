import io
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from receipt_ocr.observe import Box, Observation, Span
from receipt_ocr.observe.impl import rapidocr, tesseract
from tests.approaches import load_approaches
from tests.evaluate_observe import ANNOTATION_PATH, evaluate, write_summary
from tests.fixture_cases import FIXTURES
from tests.observe_metrics import Region, score


def sample_png() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (100, 50), "white").save(buffer, format="PNG")
    return buffer.getvalue()


def test_tesseract_normalizes_word_tsv(monkeypatch: pytest.MonkeyPatch) -> None:
    image = sample_png()
    tsv = (
        b"level\tleft\ttop\twidth\theight\tconf\ttext\n"
        b"1\t0\t0\t100\t50\t-1\t\n"
        b"5\t10\t5\t30\t10\t95.5\t10.80\n"
        b'5\t50\t10\t25\t10\t-1\t"TOTAL"\n'
    )

    def run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        assert args == ["tesseract", "stdin", "stdout", "-l", "eng", "--psm", "11", "tsv"]
        assert kwargs["input"] == image
        return subprocess.CompletedProcess(args, 0, tsv)

    monkeypatch.setattr(tesseract, "run", run)
    result = tesseract.observe(image, psm=11)
    assert result == Observation(
        (
            Span("s1", "10.80", Box(0.1, 0.1, 0.4, 0.3), 0.955),
            Span("s2", '"TOTAL"', Box(0.5, 0.2, 0.75, 0.4)),
        )
    )


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (FileNotFoundError(), "Install Tesseract"),
        (
            subprocess.CalledProcessError(1, "tesseract", stderr=b"missing language"),
            "missing language",
        ),
    ],
)
def test_tesseract_reports_setup_errors(
    monkeypatch: pytest.MonkeyPatch, error: Exception, message: str
) -> None:
    def run(*args: object, **kwargs: object) -> None:
        raise error

    monkeypatch.setattr(tesseract, "run", run)
    with pytest.raises(RuntimeError, match=message):
        tesseract.observe(sample_png())


def test_rapidocr_normalizes_polygons_and_keeps_empty_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    image = sample_png()
    polygon = [(60, 10), (100, 8), (102, 23), (61, 25)]
    results = iter(
        [
            SimpleNamespace(boxes=[polygon, polygon], txts=["10.80", " "], scores=[0.9, 0.0]),
            SimpleNamespace(boxes=None, txts=None, scores=None),
        ]
    )

    def run(png: bytes, *, use_cls: bool) -> SimpleNamespace:
        assert png == image and not use_cls
        return next(results)

    def engine(*, params: dict[str, object]) -> object:
        assert params == {"Global.max_side_len": 2100, "Global.text_score": 0.0}
        return run

    monkeypatch.setattr(rapidocr, "import_module", lambda name: SimpleNamespace(RapidOCR=engine))
    rapidocr._engine.cache_clear()
    try:
        assert rapidocr.observe(image, max_side_len=2100) == Observation(
            (Span("s1", "10.80", Box(0.6, 0.16, 1.0, 0.5), 0.9),)
        )
        assert rapidocr.observe(image, max_side_len=2100) == Observation(())
    finally:
        rapidocr._engine.cache_clear()


def test_rapidocr_reports_missing_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing(name: str) -> None:
        raise ModuleNotFoundError(name)

    monkeypatch.setattr(rapidocr, "import_module", missing)
    with pytest.raises(RuntimeError, match="make setup OBSERVE=1"):
        rapidocr.observe(sample_png())


def test_score_separates_missed_regions_from_misread_amounts() -> None:
    regions = [
        Region("date", "date", "10/18/2026", Box(0.2, 0.1, 0.4, 0.2)),
        Region("total", "amount", "10.80", Box(0.8, 0.6, 0.9, 0.7)),
    ]
    observed = Observation((Span("s1", "TOTAL 110.80", Box(0.1, 0.6, 0.9, 0.7)),))
    metrics, details = score(observed, "TOTAL 10.80", regions)
    assert metrics == {
        "empty_output": 0,
        "character_error_pct": 100 / len("TOTAL 10.80"),
        "missed_regions": 1,
        "date_errors": 1,
        "amount_errors": 1,
    }
    assert details["total"] == {"expected": "10.80", "observed": "TOTAL 110.80", "exact": False}
    assert score(Observation(()), "A", regions)[0]["missed_regions"] == 2
    assert "missed_regions" not in score(Observation((Span("s1", "A"),)), "A", regions)[0]
    signed = Observation((Span("s1", "TOTAL -10.80", Box(0.1, 0.6, 0.9, 0.7)),))
    assert score(signed, "", regions)[0]["amount_errors"] == 1


def observe_sample(png: bytes, *, text: str) -> Observation:
    with Image.open(io.BytesIO(png)) as image:
        assert image.format == "PNG"
    return Observation((Span("s1", text, Box(0.6, 0.6, 0.9, 0.7)),))


def test_observe_comparison_shares_prepared_bytes_and_writes_artifacts(tmp_path: Path) -> None:
    source = FIXTURES / "pipeline/example-shop/receipt.png"
    label = tmp_path / ANNOTATION_PATH / "example-shop.json"
    label.parent.mkdir(parents=True)
    label.write_text(json.dumps({"input": str(source), "transcript": "10.80"}), encoding="utf-8")
    config = tmp_path / "approaches.json"
    config.write_text(
        json.dumps(
            [
                {
                    "name": name,
                    "method": "tests.test_observe:observe_sample",
                    "params": {"text": text},
                }
                for name, text in [("baseline", "11.80"), ("challenger", "10.80")]
            ]
        ),
        encoding="utf-8",
    )
    approaches = load_approaches(config)
    observed = evaluate("example-shop", source, tmp_path, approaches)
    debug = tmp_path / "debug"
    summary = write_summary(
        debug, [approach.name for approach in approaches], {"example-shop": observed}
    )
    assert "1 / 0 / 0" in summary.read_text(encoding="utf-8")
    assert observed["challenger"]["character_error_pct"] == 0
    assert (debug / "example-shop-02-input.png").is_file()
    for approach in approaches:
        prefix = f"example-shop-02-{approach.name}"
        assert (debug / f"{prefix}-boxes.png").is_file()
        data = json.loads((debug / f"{prefix}-observed.json").read_text(encoding="utf-8"))
        assert data["spans"][0]["text"] == approach.params["text"]
