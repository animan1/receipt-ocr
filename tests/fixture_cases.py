"""Discover receipt fixtures shared by CI and local development."""

import json
from dataclasses import dataclass
from pathlib import Path

from tests.fixture_repository import FIXTURE_PATH, PROJECT_ROOT, private_fixture_root

FIXTURES = PROJECT_ROOT / FIXTURE_PATH


@dataclass(frozen=True)
class FixtureCase:
    id: str
    input_path: Path
    output_path: Path
    sha256: str | None


def _index_files(roots: tuple[Path, ...], side: str) -> dict[str, Path]:
    files: dict[str, Path] = {}
    for root in roots:
        for path in sorted((root / side).glob("*")):
            if path.name.startswith(".") or not path.is_file():
                continue
            if not path.suffix or (side == "outputs" and path.suffix != ".json"):
                raise ValueError(f"Unexpected fixture file {path}")
            if path.stem in files:
                raise ValueError(
                    f"Duplicate fixture {side} ID {path.stem}: {files[path.stem]}, {path}"
                )
            files[path.stem] = path
    return files


def _index_checksums(
    roots: tuple[Path, ...], inputs: dict[str, Path], outputs: dict[str, Path]
) -> dict[str, str]:
    checksums: dict[str, str] = {}
    for root in roots:
        path = root / "manifest.json"
        if not path.exists():
            continue
        manifest = json.loads(path.read_text(encoding="utf-8"))
        if manifest["version"] != 1:
            raise ValueError(f"Unsupported fixture manifest version in {path}")
        for entry in manifest["fixtures"]:
            fixture_id = entry["id"]
            if (
                fixture_id in checksums
                or inputs.get(fixture_id) != root / entry["input"]
                or outputs.get(fixture_id) != root / entry["output"]
            ):
                raise ValueError(f"Invalid manifest entry for fixture {fixture_id} in {path}")
            checksums[fixture_id] = entry["sha256"]
    return checksums


def discover_cases(shared: Path = FIXTURES, local: Path | None = None) -> list[FixtureCase]:
    roots = (shared, local if local is not None else private_fixture_root())
    inputs = _index_files(roots, "inputs")
    outputs = _index_files(roots, "outputs")
    missing_outputs = sorted(inputs.keys() - outputs.keys())
    missing_inputs = sorted(outputs.keys() - inputs.keys())
    if missing_outputs or missing_inputs:
        raise ValueError(
            f"Unpaired fixtures. Missing outputs: {missing_outputs}. Missing inputs: {missing_inputs}."
        )
    checksums = _index_checksums(roots, inputs, outputs)
    return [
        FixtureCase(fixture_id, inputs[fixture_id], outputs[fixture_id], checksums.get(fixture_id))
        for fixture_id in sorted(inputs)
    ]
