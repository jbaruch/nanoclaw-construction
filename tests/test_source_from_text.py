"""Supplied text is hashed exactly; it never becomes native or owner authority."""

from __future__ import annotations

import hashlib
import io
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(
    0, str(Path(__file__).resolve().parents[1] / "skills/construction-costs/scripts")
)
# These standalone-script imports follow the explicit scripts-directory setup.
from source_from_text import run, source_from_text  # noqa: E402


class SourceTextTests(unittest.TestCase):
    def test_retains_exact_unicode_whitespace_and_only_hashes_text(self) -> None:
        text = "  Actual supplied synthetic source\nOwner clarification: paid USD 12.34 👷\r\n"
        packet = source_from_text(
            {
                "id": "synthetic-source:501",
                "summary": "Synthetic owner clarification",
                "text": text,
                "complete": True,
            }
        )
        self.assertEqual(packet["source"]["text"], text)
        self.assertEqual(
            packet["source"]["sha256"], hashlib.sha256(text.encode("utf-8")).hexdigest()
        )
        self.assertEqual(packet["source_hint"]["id"], "synthetic-source:501")
        self.assertEqual(set(packet), {"schema_version", "source", "source_hint"})

    def test_refuses_partial_or_malformed_evidence(self) -> None:
        for changed in (
            {"complete": False},
            {"complete": 1},
            {"id": ""},
            {"summary": "x\ny"},
            {"text": ""},
            {"text": "\ud800"},
            {"approved": True},
            {"text": "x" * (2 * 1024 * 1024 + 1)},
        ):
            with self.subTest(changed=list(changed)):
                value = {
                    "id": "synthetic-source",
                    "summary": "Synthetic text",
                    "text": "Actual source",
                    "complete": True,
                    **changed,
                }
                with self.assertRaises(ValueError):
                    source_from_text(value)

    def test_cli_emits_packet_without_transport_or_approval_claim(self) -> None:
        output, errors = io.StringIO(), io.StringIO()
        raw = json.dumps(
            {
                "id": "synthetic-source",
                "summary": "Synthetic text",
                "text": "Actual source",
                "complete": True,
            }
        ).encode()
        self.assertEqual(run(io.BytesIO(raw), output, errors), 0)
        self.assertEqual(errors.getvalue(), "")
        self.assertEqual(
            json.loads(output.getvalue())["source"]["text"], "Actual source"
        )

    def test_decoder_failures_are_content_free(self) -> None:
        for raw in (
            b'{"id":"PRIVATE","id":"PRIVATE"}',
            b"NaN",
            b"[" * 5000,
            b"9" * 5000,
            b"\xff",
            b"x" * (4 * 1024 * 1024 + 1),
        ):
            with self.subTest(prefix=raw[:1]):
                output, errors = io.StringIO(), io.StringIO()
                self.assertEqual(run(io.BytesIO(raw), output, errors), 1)
                self.assertEqual(output.getvalue(), "")
                self.assertNotIn("PRIVATE", errors.getvalue())
                self.assertNotIn("Traceback", errors.getvalue())
