#!/usr/bin/env python3
"""Bind a complete admin fetch-mail-body schema1 report to its requested native ID.

JSON stdin exactly {message_id, observation}; no arguments, files or network.
The source hash covers only the exact already-sanitized body string's UTF-8
bytes. Metadata and source hints remain untrusted data, never owner approval,
native attestation, label membership or attachment/RFC822 coverage.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from typing import BinaryIO, TextIO, TypedDict

MAX_BODY_BYTES = 512 * 1024
MAX_REQUEST_BYTES = 600 * 1024
NATIVE_ID = re.compile(r"[a-fA-F0-9]{1,128}\Z")
DIAGNOSTIC = (
    "construction mail source refused: fetch the exact native message through "
    "the installed sanitizing fetch-mail-body helper and supply its complete "
    "schema1 body report; incomplete or attachment-only evidence needs another "
    "complete source. Source hints grant no approval.\n"
)
REPORT_FIELDS = {
    "schema_version",
    "message_id",
    "thread_id",
    "subject",
    "from",
    "body",
    "body_complete",
    "citation_url",
    "source_trust",
}


class MailSourceError(ValueError):
    """The observation cannot bind a complete sanitized message body."""


class Source(TypedDict):
    id: str
    text: str
    sha256: str
    complete: bool


class SourceHint(TypedDict):
    id: str
    sha256: str
    summary: str


class MailSource(TypedDict):
    schema_version: int
    source: Source
    source_hint: SourceHint


def _object(value: object, fields: set[str]) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != fields:
        raise MailSourceError("Unsupported report fields.")
    return value


def _identifier(value: object) -> str:
    if not isinstance(value, str) or not NATIVE_ID.fullmatch(value):
        raise MailSourceError("Unsupported native message or thread identifier.")
    return value


def _unicode(value: object) -> str:
    if not isinstance(value, str) or any(0xD800 <= ord(c) <= 0xDFFF for c in value):
        raise MailSourceError("Invalid Unicode report string.")
    return value


def source_from_mail(value: object) -> MailSource:
    """Validate identity/completeness and preserve the producer's body bytes."""
    request = _object(value, {"message_id", "observation"})
    expected = _identifier(request["message_id"])
    report = _object(request["observation"], REPORT_FIELDS)
    if (
        type(report["schema_version"]) is not int
        or report["schema_version"] != 1
        or _identifier(report["message_id"]) != expected
        or report["body_complete"] is not True
        or report["source_trust"] != "untrusted"
    ):
        raise MailSourceError("Unsupported identity, schema or complete-body proof.")
    thread = _identifier(report["thread_id"])
    citation = f"https://mail.google.com/mail/u/0/#all/{thread}"
    if report["citation_url"] != citation:
        raise MailSourceError("Native thread and canonical citation differ.")
    # The shipped sanitizer limits headers to 300 scalars plus its six-character
    # truncation marker. Headers are validated but never hashed as body evidence.
    for field in ("subject", "from"):
        if len(_unicode(report[field])) > 306:
            raise MailSourceError("Unsupported sanitized header bounds.")
    body = _unicode(report["body"])
    if not body.strip():
        raise MailSourceError("Empty or attachment-only evidence is incomplete.")
    body_bytes = body.encode("utf-8")
    if len(body_bytes) > MAX_BODY_BYTES:
        raise MailSourceError("Complete body exceeds the supported byte bound.")
    digest = hashlib.sha256(body_bytes).hexdigest()
    identity = f"gmail:{expected}"
    return {
        "schema_version": 1,
        "source": {"id": identity, "text": body, "sha256": digest, "complete": True},
        "source_hint": {
            "id": identity,
            "sha256": digest,
            "summary": f"Gmail thread {citation}",
        },
    }


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise MailSourceError("Duplicate JSON field.")
        result[key] = value
    return result


def _reject_constant(_value: str) -> object:
    raise MailSourceError("Nonfinite JSON number.")


def run(source: BinaryIO, output: TextIO, diagnostics: TextIO) -> int:
    """Read bounded UTF-8 JSON; emit one source object or content-free failure."""
    try:
        raw = source.read(MAX_REQUEST_BYTES + 1)
        if len(raw) > MAX_REQUEST_BYTES:
            raise MailSourceError("Request exceeds the supported byte bound.")
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
        result = source_from_mail(value)
    except (ValueError, UnicodeError, RecursionError):
        # Decoder digit/recursion/UTF-8 messages can contain source bytes.
        diagnostics.write(DIAGNOSTIC)
        return 1
    output.write(json.dumps(result, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 1:
        sys.stderr.write(DIAGNOSTIC)
        raise SystemExit(1)
    raise SystemExit(run(sys.stdin.buffer, sys.stdout, sys.stderr))
