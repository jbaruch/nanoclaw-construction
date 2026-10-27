"""Validate model-extracted payment facts and compare a complete journal read.

This pure component performs no network or filesystem writes and grants no
approval. A model must read the complete sanitized source and extract the facts;
quote containment is provenance checking, not a semantic payment classifier.
The host writer and native intake are separate, mandatory delivery gates.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import unicodedata
from datetime import date, datetime
from decimal import Decimal
from typing import BinaryIO, TextIO, TypedDict


class ProposalError(ValueError):
    """The supplied observation cannot support a payment proposal."""


class Proposal(TypedDict):
    schema_version: int
    disposition: str
    row: list[str] | None
    questions: list[str]
    matching_rows: list[int]
    source_id: str
    source_sha256: str
    write_authorized: bool


FIELDS = ("date", "purpose", "payee", "amount", "currency", "payment_method")
METHODS = {
    "ach": "ACH",
    "ach transfer": "ACH",
    "wire": "Wire",
    "wire transfer": "Wire",
    "bank wire": "Wire",
    "check": "Check",
    "cheque": "Check",
    "cash": "Cash",
    "card": "Card",
    "credit card": "Card",
    "debit card": "Card",
}


def _object(value: object, keys: set[str], context: str) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != keys:
        raise ProposalError(f"Restore the exact {context} schema.")
    return value


def _text(value: object, context: str, limit: int = 2000) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > limit
        or any(unicodedata.category(c) in {"Cc", "Cs"} for c in value)
    ):
        raise ProposalError(f"Supply a bounded, nonempty {context}.")
    return value


def _key(value: str) -> str:
    return " ".join(unicodedata.normalize("NFC", value).split()).casefold()


def _amount(value: str, *, formatted: bool = False) -> str:
    raw = value.strip()
    if formatted:
        raw = re.sub(r"^(?:USD\s*|\$\s*)", "", raw)
        pattern = r"(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d{1,2})?"
    else:
        pattern = r"\d+(?:\.\d{1,2})?"
    if not re.fullmatch(pattern, raw) or len(raw) > 24:
        raise ProposalError("Clarify the positive USD amount to exact cents.")
    number = Decimal(raw.replace(",", ""))
    if number <= 0:
        raise ProposalError("Clarify the positive USD payment amount.")
    return format(number, ".2f")


def _date(value: str, *, formatted: bool = False) -> str:
    try:
        if formatted:
            if not re.fullmatch(r"\d{1,2}/\d{1,2}/\d{4}", value):
                raise ValueError("unsupported displayed journal date")
            return datetime.strptime(value, "%m/%d/%Y").date().isoformat()
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ValueError("payment date must be ISO")
        return date.fromisoformat(value).isoformat()
    except ValueError as error:
        raise ProposalError("Clarify the actual payment date.") from error


def _method(value: str) -> str:
    method = METHODS.get(_key(value))
    if method is None:
        raise ProposalError("Clarify the payment method; do not infer it.")
    return method


def _fact(value: object, source_id: str, source_text: str) -> str | None:
    record = _object(value, {"value", "source_id", "quote"}, "extracted fact")
    if record["value"] is None:
        if record["source_id"] is not None or record["quote"] is not None:
            raise ProposalError("An unknown fact must have no invented citation.")
        return None
    result = _text(record["value"], "fact")
    quote = record["quote"]
    if (
        record["source_id"] != source_id
        or not isinstance(quote, str)
        or not quote.strip()
        or len(quote) > 4000
        or quote not in source_text
    ):
        raise ProposalError("Bind every fact to a quote in the complete source.")
    return result


def _journal_rows(value: object) -> list[tuple[int, list[str]]]:
    journal = _object(value, {"complete", "headers", "rows"}, "journal observation")
    headers = journal["headers"]
    if (
        journal["complete"] is not True
        or not isinstance(headers, list)
        or len(headers) != 5
        or not all(isinstance(header, str) for header in headers)
        or headers[:2] != ["Date", "Purpose"]
        or headers[2] not in {"Recepient", "Recipient", "Payee"}
        or headers[3:] != ["Amount", "Payment type"]
    ):
        raise ProposalError("Read the complete five-column payment journal first.")
    rows = journal["rows"]
    if not isinstance(rows, list) or len(rows) > 10000:
        raise ProposalError("Read a bounded, complete journal without truncation.")
    result: list[tuple[int, list[str]]] = []
    for number, row in enumerate(rows, start=2):
        if not isinstance(row, list) or len(row) > 5:
            raise ProposalError("Resolve malformed journal rows before proposing.")
        cells = row + [""] * (5 - len(row))
        if all(cell == "" for cell in cells):
            continue
        texts = [_text(cell, "displayed journal cell") for cell in cells]
        result.append(
            (
                number,
                [
                    _date(texts[0], formatted=True),
                    _key(texts[1]),
                    _key(texts[2]),
                    _amount(texts[3], formatted=True),
                    _method(texts[4]),
                ],
            )
        )
    return result


def prepare_proposal(value: object) -> Proposal:
    """Return a review candidate or clarification, never write permission."""
    request = _object(
        value, {"schema_version", "source", "extraction", "journal"}, "request"
    )
    if type(request["schema_version"]) is not int or request["schema_version"] != 1:
        raise ProposalError("Use payment proposal schema version 1.")
    source = _object(
        request["source"], {"id", "text", "sha256", "complete"}, "source observation"
    )
    source_id = _text(source["id"], "native source identifier", 300)
    text = source["text"]
    if (
        source["complete"] is not True
        or not isinstance(text, str)
        or not text.strip()
        or any(unicodedata.category(c) == "Cs" for c in text)
        or len(text.encode("utf-8")) > 2 * 1024 * 1024
        or source["sha256"] != hashlib.sha256(text.encode("utf-8")).hexdigest()
    ):
        raise ProposalError("Restore the complete sanitized source and its hash.")
    observed_rows = _journal_rows(request["journal"])
    extraction = _object(
        request["extraction"],
        {*FIELDS, "document_kind", "payment_status"},
        "model extraction",
    )
    if extraction["document_kind"] not in ("invoice", "payment_confirmation"):
        raise ProposalError("Classify the full document before extracting a payment.")
    status = _fact(extraction["payment_status"], source_id, text)
    fields = {name: _fact(extraction[name], source_id, text) for name in FIELDS}
    questions = [
        f"Clarify {name.replace('_', ' ')}." for name in FIELDS if fields[name] is None
    ]
    if extraction["document_kind"] == "invoice" or status != "completed":
        questions.append("Confirm this was paid, including the actual payment date.")
    if fields["currency"] is not None and fields["currency"] != "USD":
        questions.append(
            "Confirm a USD journal amount; do not convert currency implicitly."
        )
    result: Proposal = {
        "schema_version": 1,
        "disposition": "needs_clarification",
        "row": None,
        "questions": questions,
        "matching_rows": [],
        "source_id": source_id,
        "source_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "write_authorized": False,
    }
    if questions:
        return result
    values: list[str] = []
    for name in FIELDS:
        fact = fields[name]
        if fact is None:
            raise ProposalError("Resolve every payment field before owner review.")
        values.append(fact)
    payment_date, purpose, payee, amount, _, method = values
    row = [_date(payment_date), purpose, payee, _amount(amount), _method(method)]
    key = [row[0], _key(row[1]), _key(row[2]), row[3], row[4]]
    exact = [number for number, prior in observed_rows if prior == key]
    possible = [
        number
        for number, prior in observed_rows
        if [prior[0], prior[2], prior[3]] == [key[0], key[2], key[3]]
    ]
    result["row"] = row
    result["matching_rows"] = exact or possible
    result["disposition"] = (
        "already_recorded"
        if exact
        else "possible_duplicate"
        if possible
        else "ready_for_owner_review"
    )
    if possible and not exact:
        result["questions"] = [
            "Is this a separate payment from the matching journal row?"
        ]
    return result


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ProposalError("Remove ambiguous duplicate JSON keys.")
        result[key] = value
    return result


def _reject_constant(_value: str) -> object:
    raise ProposalError("Use standard JSON values without nonfinite numbers.")


def run(source: BinaryIO, output: TextIO, diagnostics: TextIO) -> int:
    """Read one request, max 4 MiB; emit one proposal or a content-free error."""
    try:
        raw = source.read(4 * 1024 * 1024 + 1)
        if len(raw) > 4 * 1024 * 1024:
            raise ProposalError("Supply a complete request within the 4 MiB limit.")
        try:
            value = json.loads(
                raw.decode("utf-8"),
                object_pairs_hook=_unique_object,
                parse_constant=_reject_constant,
            )
        except ProposalError:
            raise
        except (ValueError, RecursionError) as error:
            raise ProposalError("Supply bounded, valid UTF-8 JSON.") from error
        result = prepare_proposal(value)
    except (ProposalError, UnicodeError, json.JSONDecodeError) as error:
        message = (
            str(error)
            if isinstance(error, ProposalError)
            else "Supply valid UTF-8 JSON."
        )
        diagnostics.write(f"payment proposal refused: {message}\n")
        return 1
    output.write(json.dumps(result, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(run(sys.stdin.buffer, sys.stdout, sys.stderr))
