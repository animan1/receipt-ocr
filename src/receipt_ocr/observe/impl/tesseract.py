"""Read word evidence from Tesseract TSV."""

import csv
import io
from subprocess import CalledProcessError, run

from PIL import Image

from receipt_ocr.observe import Box, Observation, Span


def observe(image: bytes, *, psm: int = 6, language: str = "eng") -> Observation:
    with Image.open(io.BytesIO(image)) as decoded:
        width, height = decoded.size
    try:
        result = run(
            ["tesseract", "stdin", "stdout", "-l", language, "--psm", str(psm), "tsv"],
            input=image,
            capture_output=True,
            check=True,
            timeout=60,
        )
    except FileNotFoundError as error:
        raise RuntimeError(
            "Install Tesseract and its language data to run this approach."
        ) from error
    except CalledProcessError as error:
        raise RuntimeError(error.stderr.decode("utf-8", errors="replace").strip()) from error

    spans: list[Span] = []
    for row in csv.DictReader(
        io.StringIO(result.stdout.decode("utf-8")), delimiter="\t", quoting=csv.QUOTE_NONE
    ):
        if row["level"] != "5" or not row["text"].strip():
            continue
        left, top, word_width, word_height = (
            int(row[key]) for key in ("left", "top", "width", "height")
        )
        confidence = float(row["conf"])
        spans.append(
            Span(
                f"s{len(spans) + 1}",
                row["text"],
                Box.from_pixels(left, top, left + word_width, top + word_height, width, height),
                confidence / 100 if confidence >= 0 else None,
            )
        )
    return Observation(tuple(spans))
