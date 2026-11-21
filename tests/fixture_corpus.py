"""Prepare the private receipt corpus independently of any OCR engine."""

import argparse
import csv
import hashlib
import json
import re
import sqlite3
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import TypedDict

from tests.fixture_repository import private_fixture_root

ARCHIVE_NAME = re.compile(
    r"(?P<merchant>.+?)\s+(?P<receipt_date>\d{4}-\d{2}-\d{2})\s+"
    r"\$(?P<total>-?\d+(?:\.\d{2})?)(?:\s+.*)?"
)
MATCH_MEMO = re.compile(
    r"Receipt match:\s*transaction_guid=([^;]+);\s*split_guid=([^;]+);\s*receipt=(.+)$"
)
ORDER_COLUMNS = {
    "Order ID",
    "Order Status",
    "Payment Reference ID",
    "Payment Date",
    "Payment Amount",
    "Currency",
    "Title",
    "Item Net Total",
}


class LedgerPayment(TypedDict):
    amount: str
    currency: str
    posting_date: str | None


class Item(TypedDict):
    description: str
    amount: str


class CsvPayment(TypedDict):
    order_id: str
    payment_reference: str
    payment_date: str
    payment_amount: str
    currency: str | None
    items: list[Item]


def write_json(path: Path, value: object) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def book_payments(book: Path) -> dict[str, LedgerPayment]:
    """Reduce explicit transaction links to scorer-only payment references."""
    with closing(sqlite3.connect(book.resolve().as_uri() + "?mode=ro", uri=True)) as conn:
        memos = conn.execute("""
            SELECT memo FROM splits WHERE instr(memo, 'Receipt match:') > 0
            UNION
            SELECT string_val FROM slots
            WHERE name = 'notes' AND instr(string_val, 'Receipt match:') > 0
        """).fetchall()
        links: dict[str, set[tuple[str, str]]] = defaultdict(set)
        for (memo,) in memos:
            match = MATCH_MEMO.search(memo.strip())
            if match:
                links[Path(match[3]).name].add((match[1], match[2]))

        payments: dict[str, LedgerPayment] = {}
        for name, pairs in links.items():
            if len(pairs) != 1:
                continue
            transaction, split = next(iter(pairs))
            row = conn.execute(
                """
                SELECT s.value_num, s.value_denom, c.mnemonic, t.post_date
                FROM splits s JOIN transactions t ON t.guid = s.tx_guid
                JOIN commodities c ON c.guid = t.currency_guid
                WHERE t.guid = ? AND s.guid = ?
            """,
                (transaction, split),
            ).fetchone()
            if row:
                numerator, denominator, currency, posted_at = row
                payments[name] = {
                    "amount": format(abs(Decimal(numerator) / denominator), "f"),
                    "currency": currency,
                    "posting_date": posted_at[:10] if posted_at else None,
                }
    return payments


def csv_reference(path: Path) -> list[CsvPayment] | None:
    """Transcribe payment groups and source item amounts from known export columns."""
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not ORDER_COLUMNS.issubset(reader.fieldnames or ()):
            return None
        groups: dict[tuple[str, str, str, Decimal, str | None], list[Item]] = defaultdict(list)
        for row in reader:
            if row["Order Status"].strip().casefold() == "cancelled":
                continue
            fields = [
                row[key].strip()
                for key in (
                    "Order ID",
                    "Payment Reference ID",
                    "Payment Date",
                    "Payment Amount",
                )
            ]
            if any(field.lower() in {"", "n/a", "nan", "not available"} for field in fields):
                continue
            order, reference, payment_date, amount = fields
            total = Decimal(amount)
            if total:
                currency = row["Currency"].strip().upper() or None
                groups[order, reference, payment_date, total, currency].append(
                    {
                        "description": row["Title"].strip(),
                        "amount": format(Decimal(row["Item Net Total"]), "f"),
                    }
                )

    return [
        {
            "order_id": order,
            "payment_reference": reference,
            "payment_date": datetime.strptime(payment_date, "%m/%d/%Y").date().isoformat(),
            "payment_amount": format(total, "f"),
            "currency": currency,
            "items": items,
        }
        for (order, reference, payment_date, total, currency), items in groups.items()
    ]


def prepare_fixture(root: Path, source: Path, payment: LedgerPayment | None) -> dict[str, str]:
    fixture_id = hashlib.sha256(source.name.encode()).hexdigest()[:16]
    input_path = root / "inputs" / (fixture_id + source.suffix.lower())
    output_path = root / "outputs" / (fixture_id + ".json")
    data = source.read_bytes()
    if not data or len(data) != source.stat().st_size:
        raise ValueError(f"incomplete input for fixture {fixture_id}")
    temporary = input_path.with_suffix(".tmp")
    temporary.write_bytes(data)
    temporary.replace(input_path)

    archive_fields = None
    match = ARCHIVE_NAME.fullmatch(source.stem)
    if match:
        archive_fields = match.groupdict()
        date.fromisoformat(archive_fields["receipt_date"])
    records = csv_reference(input_path) if input_path.suffix == ".csv" else None
    write_json(
        output_path,
        {
            "receipt_records": records,
            "references": {"archive_filename": archive_fields, "ledger_payment": payment},
        },
    )
    return {
        "id": fixture_id,
        "input": input_path.relative_to(root).as_posix(),
        "output": output_path.relative_to(root).as_posix(),
        "source_filename": source.name,
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def prepare(archive: Path, book: Path, *, root: Path | None = None) -> None:
    if not archive.is_dir() or not book.is_file():
        raise ValueError("pass the archive directory and the local book file")
    sources = sorted(
        path for path in archive.iterdir() if path.is_file() and not path.name.startswith(".")
    )
    if not sources:
        raise ValueError("archive has no visible input files")
    if root is None:
        root = private_fixture_root(require_existing=False)
    payments = book_payments(book)
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    for directory in (root / "inputs", root / "outputs"):
        directory.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=8) as workers:
        jobs = [
            workers.submit(prepare_fixture, root, source, payments.get(source.name))
            for source in sources
        ]
        fixtures = [job.result() for job in jobs]
    write_json(root / "manifest.json", {"version": 1, "fixtures": fixtures})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--book", type=Path, required=True)
    args = parser.parse_args()
    prepare(args.archive, args.book)


if __name__ == "__main__":
    main()
