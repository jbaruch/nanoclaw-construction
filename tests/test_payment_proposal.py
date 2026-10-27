"""Synthetic observations only; these tests perform no provider operations."""

from __future__ import annotations

import copy
import hashlib
import io
import json
import sys
import unittest
from decimal import localcontext
from pathlib import Path
from typing import Any

sys.path.insert(
    0, str(Path(__file__).resolve().parents[1] / "skills/construction-costs/scripts")
)
from payment_proposal import ProposalError, prepare_proposal, run  # noqa: E402


def request() -> dict[str, Any]:
    text = (
        "Wire completed on 2026-09-15 to Example Builder for USD 1234.56.\n"
        "Purpose: foundation work."
    )

    def fact(value: str) -> dict[str, str]:
        return {"value": value, "source_id": "synthetic-mail-1", "quote": text}

    return {
        "schema_version": 1,
        "source": {
            "id": "synthetic-mail-1",
            "text": text,
            "sha256": hashlib.sha256(text.encode()).hexdigest(),
            "complete": True,
        },
        "extraction": {
            "document_kind": "payment_confirmation",
            "payment_status": fact("completed"),
            "date": fact("2026-09-15"),
            "purpose": fact("foundation work"),
            "payee": fact("Example Builder"),
            "amount": fact("1234.56"),
            "currency": fact("USD"),
            "payment_method": fact("wire"),
        },
        "journal": {
            "complete": True,
            "headers": ["Date", "Purpose", "Recepient", "Amount", "Payment type"],
            "rows": [],
        },
    }


class PaymentProposalTests(unittest.TestCase):
    def test_complete_payment_produces_exact_cents_without_write_authority(
        self,
    ) -> None:
        value = request()
        original = copy.deepcopy(value)
        result = prepare_proposal(value)
        self.assertEqual(result["disposition"], "ready_for_owner_review")
        self.assertEqual(
            result["row"],
            ["2026-09-15", "foundation work", "Example Builder", "1234.56", "Wire"],
        )
        self.assertFalse(result["write_authorized"])
        self.assertEqual(value, original)

    def test_missing_amount_or_payee_is_a_question_not_a_guessed_row(self) -> None:
        for field in ("amount", "payee"):
            with self.subTest(field=field):
                value = request()
                value["extraction"][field] = {
                    "value": None,
                    "source_id": None,
                    "quote": None,
                }
                result = prepare_proposal(value)
                self.assertEqual(result["disposition"], "needs_clarification")
                self.assertIn(f"Clarify {field}.", result["questions"])
                self.assertIsNone(result["row"])

    def test_invoice_and_pending_notice_do_not_establish_payment(self) -> None:
        invoice = request()
        invoice["extraction"]["document_kind"] = "invoice"
        pending = request()
        pending["extraction"]["payment_status"]["value"] = "pending"
        for value in (invoice, pending):
            result = prepare_proposal(value)
            self.assertEqual(result["disposition"], "needs_clarification")
            self.assertIsNone(result["row"])
            self.assertFalse(result["write_authorized"])

    def test_foreign_currency_is_never_implicitly_converted(self) -> None:
        value = request()
        value["extraction"]["currency"]["value"] = "EUR"
        result = prepare_proposal(value)
        self.assertIsNone(result["row"])
        self.assertIn("USD", " ".join(result["questions"]))

    def test_citations_and_complete_source_are_required(self) -> None:
        for mutation in ("hash", "quote", "source_id", "partial", "surrogate"):
            with self.subTest(mutation=mutation):
                value = request()
                if mutation == "hash":
                    value["source"]["sha256"] = "0" * 64
                elif mutation == "quote":
                    value["extraction"]["amount"]["quote"] = "absent evidence"
                elif mutation == "source_id":
                    value["extraction"]["payee"]["source_id"] = "another-mail"
                elif mutation == "partial":
                    value["source"]["complete"] = False
                else:
                    value["source"]["text"] = "bad\ud800"
                with self.assertRaises(ProposalError):
                    prepare_proposal(value)

    def test_complete_valid_journal_is_required_even_when_facts_are_missing(
        self,
    ) -> None:
        for mutation in ("partial", "header", "row", "amount", "method", "date"):
            with self.subTest(mutation=mutation):
                value = request()
                value["journal"]["rows"] = [
                    ["9/14/2026", "earlier work", "Example Builder", "$100.00", "ACH"]
                ]
                if mutation == "partial":
                    value["journal"]["complete"] = False
                elif mutation == "header":
                    value["journal"]["headers"][2] = {}
                elif mutation == "row":
                    value["journal"]["rows"][0] = ["9/14/2026"]
                elif mutation == "amount":
                    value["journal"]["rows"][0][3] = "$1,00.00"
                elif mutation == "method":
                    value["journal"]["rows"][0][4] = "unspecified"
                else:
                    value["journal"]["rows"][0][0] = "9/31/2026"
                value["extraction"]["payee"] = {
                    "value": None,
                    "source_id": None,
                    "quote": None,
                }
                with self.assertRaises(ProposalError):
                    prepare_proposal(value)

    def test_exact_formatted_existing_row_is_already_recorded(self) -> None:
        value = request()
        value["journal"]["rows"] = [
            [],
            [
                "9/15/2026",
                " Foundation   Work ",
                "EXAMPLE BUILDER",
                "$1,234.56",
                "Wire transfer",
            ],
        ]
        result = prepare_proposal(value)
        self.assertEqual(result["disposition"], "already_recorded")
        self.assertEqual(result["matching_rows"], [3])
        self.assertFalse(result["write_authorized"])

    def test_changed_purpose_is_possible_duplicate_not_new_payment(self) -> None:
        value = request()
        value["journal"]["rows"] = [
            ["9/15/2026", "Draw one", "Example Builder", "USD 1,234.56", "Wire"]
        ]
        result = prepare_proposal(value)
        self.assertEqual(result["disposition"], "possible_duplicate")
        self.assertEqual(result["matching_rows"], [2])
        self.assertTrue(result["questions"])
        self.assertFalse(result["write_authorized"])

    def test_changed_method_cannot_hide_a_possible_duplicate(self) -> None:
        value = request()
        value["journal"]["rows"] = [
            ["9/15/2026", "foundation work", "Example Builder", "$1,234.56", "ACH"]
        ]
        self.assertEqual(prepare_proposal(value)["disposition"], "possible_duplicate")

    def test_distinct_payment_date_does_not_merge_by_payee_or_amount(self) -> None:
        value = request()
        value["journal"]["rows"] = [
            ["9/14/2026", "foundation work", "Example Builder", "$1,234.56", "Wire"]
        ]
        self.assertEqual(
            prepare_proposal(value)["disposition"], "ready_for_owner_review"
        )

    def test_invalid_amount_date_or_method_is_refused_without_rounding(self) -> None:
        for field, replacement in (
            ("amount", "0"),
            ("amount", "-12.50"),
            ("amount", "1.005"),
            ("amount", "NaN"),
            ("amount", "1e3"),
            ("date", "2026-09-31"),
            ("date", "09/15/2026"),
            ("payment_method", "maybe bank"),
        ):
            with self.subTest(field=field, replacement=replacement):
                value = request()
                value["extraction"][field]["value"] = replacement
                with self.assertRaises(ProposalError):
                    prepare_proposal(value)

    def test_decimal_context_cannot_round_an_extracted_amount(self) -> None:
        with localcontext() as context:
            context.prec = 3
            row = prepare_proposal(request())["row"]
            self.assertIsNotNone(row)
            assert row is not None
            self.assertEqual(row[3], "1234.56")

    def test_unknown_and_approval_fields_cannot_supply_authority(self) -> None:
        for field, replacement in (("approved", True), ("schema_version", True)):
            value = request()
            value[field] = replacement
            with self.assertRaises(ProposalError):
                prepare_proposal(value)

    def test_cli_emits_one_proposal_without_diagnostics(self) -> None:
        output, diagnostics = io.StringIO(), io.StringIO()
        self.assertEqual(
            run(io.BytesIO(json.dumps(request()).encode()), output, diagnostics), 0
        )
        self.assertEqual(
            json.loads(output.getvalue())["disposition"], "ready_for_owner_review"
        )
        self.assertFalse(json.loads(output.getvalue())["write_authorized"])
        self.assertEqual(diagnostics.getvalue(), "")

    def test_cli_refuses_invalid_inputs_without_echoing_source(self) -> None:
        for raw in (
            b'{"source":"private-synthetic-content",',
            b'{"source":1,"source":2}',
            b'{"schema_version":NaN}',
            b"\xff",
            b"x" * (4 * 1024 * 1024 + 1),
        ):
            with self.subTest(prefix=raw[:20]):
                output, diagnostics = io.StringIO(), io.StringIO()
                self.assertEqual(run(io.BytesIO(raw), output, diagnostics), 1)
                self.assertEqual(output.getvalue(), "")
                self.assertNotIn("private-synthetic-content", diagnostics.getvalue())
                self.assertTrue(
                    diagnostics.getvalue().startswith("payment proposal refused:")
                )


if __name__ == "__main__":
    unittest.main()
