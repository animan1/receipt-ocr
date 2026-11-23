import io
import subprocess

import pytest
from PIL import Image

from receipt_ocr.observe import Box, Observation, Span
from receipt_ocr.observe.impl import tesseract


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
