#!/usr/bin/env python3
"""Hash complete supplied text for review; this creates no native attestation.

JSON stdin exactly {id,summary,text,complete:true}, no arguments or file access.
The caller retains the actual source/native message reference. Text and its
completeness flag remain supplied evidence, never sender or approval authority.
Output matches source_from_mail's source/source_hint packet. Runtime is stdlib.
"""

from __future__ import annotations

import hashlib
import json
import sys
import unicodedata
from typing import BinaryIO, TextIO

from source_from_mail import MailSource

DIAGNOSTIC = (
    "construction text source refused: supply complete valid text, its stable "
    "source reference and a bounded summary; this packet grants no approval.\n"
)


def _literal(value: object) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > 300
        or any(unicodedata.category(c) in {"Cc", "Cs"} for c in value)
    ):
        raise ValueError("Invalid source reference or summary.")
    return value


def source_from_text(value: object) -> MailSource:
    """Preserve supplied text byte-for-byte; do not infer transport or identity."""
    if not isinstance(value, dict) or set(value) != {
        "id",
        "summary",
        "text",
        "complete",
    }:
        raise ValueError("Invalid source fields.")
    identity, summary = _literal(value["id"]), _literal(value["summary"])
    text = value["text"]
    if (
        value["complete"] is not True
        or not isinstance(text, str)
        or not text.strip()
        or any(unicodedata.category(c) == "Cs" for c in text)
        or len(text.encode("utf-8")) > 2 * 1024 * 1024
    ):
        raise ValueError("Incomplete source text.")
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return {
        "schema_version": 1,
        "source": {"id": identity, "text": text, "sha256": digest, "complete": True},
        "source_hint": {"id": identity, "sha256": digest, "summary": summary},
    }


def _unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate field.")
        result[key] = value
    return result


def _nonfinite(_value: str) -> object:
    raise ValueError("Nonfinite value.")


def run(source: BinaryIO, output: TextIO, diagnostics: TextIO) -> int:
    try:
        raw = source.read(4 * 1024 * 1024 + 1)
        if len(raw) > 4 * 1024 * 1024:
            raise ValueError("Input exceeds byte bound.")
        value = json.loads(
            raw.decode("utf-8"), object_pairs_hook=_unique, parse_constant=_nonfinite
        )
        result = source_from_text(value)
    except (ValueError, UnicodeError, RecursionError):
        diagnostics.write(DIAGNOSTIC)
        return 1
    output.write(json.dumps(result, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 1:
        sys.stderr.write(DIAGNOSTIC)
        raise SystemExit(1)
    raise SystemExit(run(sys.stdin.buffer, sys.stdout, sys.stderr))
