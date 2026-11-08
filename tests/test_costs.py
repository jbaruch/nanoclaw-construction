"""costs.py against a fake Sheets API: read, duplicate refusal, append + readback."""

from __future__ import annotations

import importlib.util
import io
import json
import re
import tempfile
import unittest
import urllib.parse
from pathlib import Path
from typing import Any
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/construction-costs/scripts/costs.py"


def load() -> Any:
    spec = importlib.util.spec_from_file_location("costs_under_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def formatted(cell: str) -> str:
    """What Sheets shows after parsing an entered cell (USER_ENTERED)."""
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", cell):
        y, m, d = (int(x) for x in cell.split("-"))
        return f"{m}/{d}/{y}"
    if re.fullmatch(r"\$?[\d,]+(\.\d+)?", cell):
        return f"${float(cell.replace('$', '').replace(',', '')):,.2f}"
    return cell


class FakeSheet:
    """Sheet1!A:E with the Sheets v4 values/append response shapes."""

    def __init__(self, values, reformat=False):
        self.values = values
        self.reformat = reformat
        self.calls = []

    def urlopen(self, request, timeout):
        self.calls.append((request.get_method(), request.full_url))
        url = request.full_url
        if request.get_method() == "POST":
            row = json.loads(request.data)["values"][0]
            self.values.append([formatted(c) for c in row] if self.reformat else row)
            n = len(self.values)
            body = {"updates": {"updatedRange": f"Sheet1!A{n}:E{n}"}}
        elif "Sheet1%21A%3AE" in url:
            body = {"range": "Sheet1!A1:E9", "values": self.values}
        else:
            written = re.search(r"Sheet1!A(\d+):E\d+$", urllib.parse.unquote(url))
            assert written is not None, url
            body = {"values": [self.values[int(written.group(1)) - 1]]}
        return io.BytesIO(json.dumps(body).encode())


ROW = ["2026-11-02", "Framing deposit", "Acme Builders", "$12,500.00", "Wire"]


class CostsTests(unittest.TestCase):
    def setUp(self):
        self.costs = load()
        self.dir = tempfile.TemporaryDirectory()
        config = Path(self.dir.name) / "construction-costs.json"
        config.write_text('{"sheet_id": "sheet-1"}')
        self.costs.CONFIG = config

    def tearDown(self):
        self.dir.cleanup()

    def run_cli(self, argv, stdin: str = "", *, sheet: FakeSheet):
        out = io.StringIO()
        with (
            mock.patch.object(self.costs.urllib.request, "urlopen", sheet.urlopen),
            mock.patch("sys.stdin", io.StringIO(stdin)),
            mock.patch("sys.stdout", out),
        ):
            code = self.costs.main(argv)
        result: Any = json.loads(out.getvalue()) if out.getvalue() else None
        return code, result

    def test_rows_lists_the_sheet(self):
        sheet = FakeSheet([["Date", "Purpose", "Payee", "Amount", "Method"], ROW])
        code, out = self.run_cli(["rows"], sheet=sheet)
        self.assertEqual((code, out["rows"][1]), (0, ROW))

    def test_append_writes_and_reads_the_row_back(self):
        sheet = FakeSheet([["Date", "Purpose", "Payee", "Amount", "Method"]])
        code, out = self.run_cli(["append"], json.dumps({"row": ROW}), sheet=sheet)
        self.assertEqual(code, 0)
        self.assertEqual(out, {"appended": "Sheet1!A2:E2", "row": ROW})
        self.assertEqual([m for m, _ in sheet.calls], ["GET", "POST", "GET"])
        self.assertIn("valueInputOption=USER_ENTERED", sheet.calls[1][1])

    def test_an_identical_row_is_refused_without_writing(self):
        sheet = FakeSheet([["Date", "Purpose", "Payee", "Amount", "Method"], ROW])
        code, out = self.run_cli(["append"], json.dumps({"row": ROW}), sheet=sheet)
        self.assertEqual((code, out), (3, {"duplicate": 2}))
        self.assertEqual([m for m, _ in sheet.calls], ["GET"])

    def test_reformatted_cells_still_read_back_and_match_as_duplicates(self):
        sheet = FakeSheet(
            [["Date", "Purpose", "Recepient", "Amount", "Payment type"]], reformat=True
        )
        entered = ["2026-11-02", "Framing deposit", "Acme Builders", "12500", "wire"]
        code, out = self.run_cli(["append"], json.dumps({"row": entered}), sheet=sheet)
        self.assertEqual((code, out["appended"]), (0, "Sheet1!A2:E2"))
        self.assertEqual(
            sheet.values[1],
            ["11/2/2026", "Framing deposit", "Acme Builders", "$12,500.00", "wire"],
        )
        again = [
            "11/02/2026",
            "framing deposit",
            "Acme  Builders",
            "$12,500.00",
            "Wire",
        ]
        code, out = self.run_cli(["append"], json.dumps({"row": again}), sheet=sheet)
        self.assertEqual((code, out), (3, {"duplicate": 2}))

    def test_a_short_row_is_bad_input(self):
        sheet = FakeSheet([])
        code, out = self.run_cli(["append"], json.dumps({"row": ROW[:4]}), sheet=sheet)
        self.assertEqual((code, out, sheet.calls), (2, None, []))

    def test_a_missing_config_is_a_failure(self):
        self.costs.CONFIG = Path(self.dir.name) / "absent.json"
        code, out = self.run_cli(["rows"], sheet=FakeSheet([]))
        self.assertEqual((code, out), (1, None))


if __name__ == "__main__":
    unittest.main()
