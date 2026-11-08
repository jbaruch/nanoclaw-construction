#!/usr/bin/env python3
"""Read and append rows in the «Construction costs» Google Sheet.

The sheet ID comes from /workspace/group/construction-costs.json
({"sheet_id": "..."}; override the path with CONSTRUCTION_COSTS_CONFIG).
OneCLI's gateway adds the Google credential on the wire through HTTPS_PROXY,
so this script sends none.

Commands, one JSON object on stdout:
  rows              {"rows": [[date, purpose, payee, amount, method], ...]}
                    every row of Sheet1!A:E.
  append            stdin {"row": [date, purpose, payee, amount, method]}.
                    Refuses a row equal to an existing one with
                    {"duplicate": <sheet row number>} and exit 3. Otherwise
                    appends it, reads the written range back and prints
                    {"appended": "<range>", "row": [...]}.
Sheets parses entered cells and returns them formatted (2026-11-02 reads back
as 11/2/2026, 12500 as $12,500.00), so rows compare as dates, amounts and
case-insensitive text, never as raw strings.
Exit 1 on a config or Google failure, 2 on bad input.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

CONFIG = Path(
    os.environ.get(
        "CONSTRUCTION_COSTS_CONFIG", "/workspace/group/construction-costs.json"
    )
)
API = "https://sheets.googleapis.com/v4/spreadsheets/"
RANGE = "Sheet1!A:E"
FIELDS = 5


DATE_FORMATS = ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y")


def normal(cell: str) -> object:
    """A cell as Sheets means it: a date, an amount, or folded text."""
    text = " ".join(cell.split())
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    try:
        return Decimal(text.replace("$", "").replace(",", ""))
    except InvalidOperation:
        return text.casefold()


def same(left: list[str], right: list[str]) -> bool:
    return [normal(c) for c in left] == [normal(c) for c in right]


class BadInput(ValueError):
    """Exit 2."""


def sheet_id() -> str:
    value = json.loads(CONFIG.read_text(encoding="utf-8")).get("sheet_id")
    if not isinstance(value, str) or not value:
        raise ValueError(f"{CONFIG} has no sheet_id")
    return value


def call(method: str, path: str, body: dict | None = None) -> dict:
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(
        API + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response)


def rows(sid: str) -> list[list[str]]:
    path = f"{sid}/values/{urllib.parse.quote(RANGE)}"
    return call("GET", path).get("values", [])


def append(sid: str, row: list[str]) -> dict:
    for number, existing in enumerate(rows(sid), start=1):
        if same(existing, row):
            return {"duplicate": number}
    query = urllib.parse.urlencode(
        {"valueInputOption": "USER_ENTERED", "insertDataOption": "INSERT_ROWS"}
    )
    path = f"{sid}/values/{urllib.parse.quote(RANGE)}:append?{query}"
    written = call("POST", path, {"values": [row]})["updates"]["updatedRange"]
    readback = call("GET", f"{sid}/values/{urllib.parse.quote(written)}").get(
        "values", []
    )
    if len(readback) != 1 or not same(readback[0], row):
        raise ValueError(f"wrote {written} but read back {readback!r}; check the sheet")
    return {"appended": written, "row": row}


def parse_row(raw: str) -> list[str]:
    try:
        row = json.loads(raw).get("row")
    except (ValueError, AttributeError):
        raise BadInput('stdin must be {"row": [5 strings]}') from None
    if (
        not isinstance(row, list)
        or len(row) != FIELDS
        or not all(isinstance(c, str) and c.strip() for c in row)
    ):
        raise BadInput(
            "row must be 5 non-empty strings: date, purpose, payee, amount, method"
        )
    return [cell.strip() for cell in row]


def main(argv: list[str]) -> int:
    if argv not in (["rows"], ["append"]):
        sys.stderr.write('usage: costs.py rows | costs.py append < {"row": [...]}\n')
        return 2
    try:
        row = parse_row(sys.stdin.read()) if argv == ["append"] else None
        sid = sheet_id()
        result = {"rows": rows(sid)} if row is None else append(sid, row)
    except BadInput as error:
        sys.stderr.write(f"costs: {error}\n")
        return 2
    except (OSError, ValueError, KeyError, urllib.error.URLError) as error:
        sys.stderr.write(
            f"costs: {type(error).__name__}: {error}; check {CONFIG} and the OneCLI Sheets connection\n"
        )
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 3 if "duplicate" in result else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
