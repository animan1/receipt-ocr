import hashlib
import json
import sqlite3
from contextlib import closing
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from tests.fixture_cases import FIXTURES, FixtureCase, discover_cases
from tests.fixture_corpus import prepare


def test_imports_csv_labels_and_ledger_reference(tmp_path: Path) -> None:
    archive = tmp_path / "archive"
    archive.mkdir()
    source = archive / "Example Shop 2026-10-18 $10.00.csv"
    source.write_bytes((FIXTURES / "inputs" / "synthetic-order.csv").read_bytes())
    book = tmp_path / "book.sqlite"
    with closing(sqlite3.connect(book)) as conn, conn:
        conn.executescript("""
            CREATE TABLE transactions (guid TEXT, currency_guid TEXT, post_date TEXT);
            CREATE TABLE splits (
                guid TEXT, tx_guid TEXT, value_num INTEGER, value_denom INTEGER, memo TEXT
            );
            CREATE TABLE slots (name TEXT, string_val TEXT);
            CREATE TABLE commodities (guid TEXT, mnemonic TEXT);
            INSERT INTO commodities VALUES ('currency', 'USD');
            INSERT INTO transactions VALUES ('transaction', 'currency', '2026-10-19');
            INSERT INTO splits VALUES ('payment', 'transaction', -1036, 100, '');
        """)
        conn.execute(
            "INSERT INTO slots VALUES ('notes', ?)",
            (f"Receipt match: transaction_guid=transaction; split_guid=payment; receipt={source}",),
        )

    local = tmp_path / "local"
    prepare(archive, book, root=local)
    (case,) = discover_cases(tmp_path / "shared", local)
    expected = json.loads(
        (FIXTURES / "outputs" / "synthetic-order.json").read_text(encoding="utf-8")
    )
    assert case.input_path.name != source.name
    assert case.input_path.read_bytes() == source.read_bytes()
    assert case.sha256 == hashlib.sha256(source.read_bytes()).hexdigest()
    assert json.loads(case.output_path.read_text(encoding="utf-8")) == {
        "receipt_records": expected["receipt_records"],
        "references": {
            "archive_filename": {
                "merchant": "Example Shop",
                "receipt_date": "2026-10-18",
                "total": "10.00",
            },
            "ledger_payment": {
                "amount": "10.36",
                "currency": "USD",
                "posting_date": "2026-10-19",
            },
        },
    }


def test_discover_cases_without_local_directory(tmp_path: Path) -> None:
    shared_input = _fixture_file(tmp_path, "inputs/shared.csv")
    shared_output = _fixture_file(tmp_path, "outputs/shared.json")

    assert discover_cases(tmp_path, tmp_path / "local") == [
        FixtureCase("shared", shared_input, shared_output, None)
    ]


def test_discover_cases_merges_local_pairs_and_cross_directory_pairs(tmp_path: Path) -> None:
    shared_input = _fixture_file(tmp_path, "inputs/shared.csv")
    shared_output = _fixture_file(tmp_path, "outputs/shared.json")
    local_input = _fixture_file(tmp_path, "local/inputs/private.pdf")
    local_output = _fixture_file(tmp_path, "local/outputs/private.json")
    cross_input = _fixture_file(tmp_path, "inputs/cross.png")
    cross_output = _fixture_file(tmp_path, "local/outputs/cross.json")

    assert discover_cases(tmp_path, tmp_path / "local") == [
        FixtureCase("cross", cross_input, cross_output, None),
        FixtureCase("private", local_input, local_output, None),
        FixtureCase("shared", shared_input, shared_output, None),
    ]


def test_discover_cases_rejects_duplicate_ids_on_one_side(tmp_path: Path) -> None:
    _fixture_file(tmp_path, "inputs/shared.csv")
    _fixture_file(tmp_path, "local/inputs/shared.pdf")

    with pytest.raises(ValueError, match="Duplicate fixture inputs ID shared"):
        discover_cases(tmp_path, tmp_path / "local")


def test_discover_cases_reports_unpaired_fixtures(tmp_path: Path) -> None:
    _fixture_file(tmp_path, "inputs/missing-label.csv")
    _fixture_file(tmp_path, "local/outputs/missing-receipt.json")

    with pytest.raises(ValueError, match=r"Missing outputs: .*missing-label.*missing-receipt"):
        discover_cases(tmp_path, tmp_path / "local")


def _fixture_file(root: Path, relative_path: str) -> Path:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()
    return path


CASES = discover_cases()


@pytest.mark.parametrize("case", CASES, ids=[case.id for case in CASES])
def test_receipt_fixture(case: FixtureCase) -> None:
    data = case.input_path.read_bytes()
    assert data
    if case.sha256 is not None:
        assert hashlib.sha256(data).hexdigest() == case.sha256
    output = json.loads(case.output_path.read_text(encoding="utf-8"))
    references = output["references"]
    archive_fields = references.get("archive_filename")
    if archive_fields is not None:
        date.fromisoformat(archive_fields["receipt_date"])
        assert Decimal(archive_fields["total"]).is_finite()
    ledger_payment = references.get("ledger_payment")
    if ledger_payment is not None:
        assert Decimal(ledger_payment["amount"]).is_finite()
    records = output["receipt_records"]
    if records is not None:
        assert isinstance(records, list)
        for record in records:
            if record.get("payment_date") is not None:
                date.fromisoformat(record["payment_date"])
            if record.get("payment_amount") is not None:
                assert Decimal(record["payment_amount"]).is_finite()
            for item in record.get("items", []):
                assert Decimal(item["amount"]).is_finite()
