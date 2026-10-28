"""Synthetic observations only; these tests perform no provider operations."""

from __future__ import annotations

import copy
import hashlib
import io
import json
import subprocess
import sys
import unittest
from decimal import localcontext
from pathlib import Path
from typing import Any

sys.path.insert(
    0, str(Path(__file__).resolve().parents[1] / "skills/construction-costs/scripts")
)
# The standalone script import follows the explicit scripts-directory path setup.
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
    def test_explicit_null_journal_requires_host_preview_without_comparison(
        self,
    ) -> None:
        value = request()
        value["journal"] = None
        original = copy.deepcopy(value)
        result = prepare_proposal(value)
        self.assertEqual(
            result,
            {
                "schema_version": 1,
                "disposition": "requires_host_preview",
                "row": [
                    "2026-09-15",
                    "foundation work",
                    "Example Builder",
                    "1234.56",
                    "Wire",
                ],
                "questions": [],
                "matching_rows": [],
                "source_id": value["source"]["id"],
                "source_sha256": value["source"]["sha256"],
                "write_authorized": False,
            },
        )
        self.assertEqual(value, original)

    def test_null_journal_actual_stdin_cli_emits_source_only_candidate(self) -> None:
        value = request()
        value["journal"] = None
        script = (
            Path(__file__).resolve().parents[1]
            / "skills/construction-costs/scripts/payment_proposal.py"
        )
        result = subprocess.run(
            [sys.executable, str(script)],
            input=json.dumps(value),
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, "")
        self.assertEqual(len(result.stdout.splitlines()), 1)
        proposal = json.loads(result.stdout)
        self.assertEqual(proposal["disposition"], "requires_host_preview")
        self.assertEqual(
            proposal["row"],
            ["2026-09-15", "foundation work", "Example Builder", "1234.56", "Wire"],
        )
        self.assertEqual(proposal["matching_rows"], [])
        self.assertIs(proposal["write_authorized"], False)

    def test_source_only_unknown_invoice_pending_and_non_usd_still_need_clarification(
        self,
    ) -> None:
        for field in (
            "document_kind",
            "payment_status",
            "currency",
            *("date", "purpose", "payee", "amount", "payment_method"),
        ):
            with self.subTest(field=field):
                value = request()
                value["journal"] = None
                if field == "document_kind":
                    value["extraction"][field] = "invoice"
                elif field in {"payment_status", "currency"}:
                    value["extraction"][field]["value"] = (
                        "pending" if field == "payment_status" else "EUR"
                    )
                else:
                    value["extraction"][field] = {
                        "value": None,
                        "source_id": None,
                        "quote": None,
                    }
                result = prepare_proposal(value)
                self.assertEqual(result["disposition"], "needs_clarification")
                self.assertIsNone(result["row"])
                self.assertTrue(result["questions"])
                self.assertEqual(result["matching_rows"], [])
                self.assertFalse(result["write_authorized"])

    def test_null_journal_never_waives_complete_source_hash_and_fact_citations(
        self,
    ) -> None:
        for mutation in ("hash", "partial", "quote", "source_id", "missing_fact"):
            with self.subTest(mutation=mutation):
                value = request()
                value["journal"] = None
                if mutation == "hash":
                    value["source"]["sha256"] = "0" * 64
                elif mutation == "partial":
                    value["source"]["complete"] = False
                elif mutation == "quote":
                    value["extraction"]["amount"]["quote"] = "absent evidence"
                elif mutation == "source_id":
                    value["extraction"]["payee"]["source_id"] = "another-mail"
                else:
                    del value["extraction"]["amount"]
                with self.assertRaises(ProposalError):
                    prepare_proposal(value)

    def test_null_journal_unknown_status_and_currency_still_need_clarification(
        self,
    ) -> None:
        for field in ("payment_status", "currency"):
            with self.subTest(field=field):
                value = request()
                value["journal"] = None
                value["extraction"][field] = {
                    "value": None,
                    "source_id": None,
                    "quote": None,
                }
                result = prepare_proposal(value)
                self.assertEqual(result["disposition"], "needs_clarification")
                self.assertIsNone(result["row"])
                self.assertTrue(result["questions"])
                self.assertFalse(result["write_authorized"])

    def test_null_journal_keeps_exact_amount_date_and_method_refusals(self) -> None:
        for field, replacement in (
            ("amount", "0"),
            ("amount", "1.005"),
            ("amount", "NaN"),
            ("date", "2026-09-31"),
            ("payment_method", "maybe bank"),
        ):
            with self.subTest(field=field, replacement=replacement):
                value = request()
                value["journal"] = None
                value["extraction"][field]["value"] = replacement
                with self.assertRaises(ProposalError):
                    prepare_proposal(value)

    def test_missing_or_fabricated_journal_placeholder_is_not_explicit_null(
        self,
    ) -> None:
        for journal in (False, [], {}, {"complete": True}, {"rows": []}):
            with self.subTest(journal=journal):
                value = request()
                value["journal"] = journal
                with self.assertRaises(ProposalError):
                    prepare_proposal(value)
        value = request()
        del value["journal"]
        with self.assertRaises(ProposalError):
            prepare_proposal(value)

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
        for mutation in ("partial", "header", "row", "amount", "date"):
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

    def test_legacy_method_does_not_block_or_bypass_duplicate_comparison(self) -> None:
        value = request()
        value["journal"]["rows"] = [
            [
                "9/15/2026",
                "foundation work",
                "Example Builder",
                "$1,234.56",
                "Legacy transfer entry",
            ]
        ]
        self.assertEqual(prepare_proposal(value)["disposition"], "possible_duplicate")
        value["journal"]["rows"][0][0] = "9/14/2026"
        self.assertEqual(
            prepare_proposal(value)["disposition"], "ready_for_owner_review"
        )
        value["journal"]["rows"][0][4] = ""
        with self.assertRaises(ProposalError):
            prepare_proposal(value)

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

    def test_cli_normalizes_real_decoder_integer_and_recursion_limits(self) -> None:
        original_limit = sys.get_int_max_str_digits()
        try:
            sys.set_int_max_str_digits(4300)
            cases = (
                b"9" * 5000,
                b"[" * (sys.getrecursionlimit() + 100)
                + b"0"
                + b"]" * (sys.getrecursionlimit() + 100),
            )
            for raw in cases:
                with self.subTest(prefix=raw[:20]):
                    output, diagnostics = io.StringIO(), io.StringIO()
                    self.assertEqual(run(io.BytesIO(raw), output, diagnostics), 1)
                    self.assertEqual(output.getvalue(), "")
                    self.assertIn("payment proposal refused:", diagnostics.getvalue())
                    self.assertNotIn("Traceback", diagnostics.getvalue())
        finally:
            sys.set_int_max_str_digits(original_limit)


if __name__ == "__main__":
    unittest.main()
