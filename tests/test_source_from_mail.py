"""Synthetic native-shaped body reports; no mailbox or provider operations."""

from __future__ import annotations

import copy
import hashlib
import io
import json
import subprocess
import sys
import unittest
from pathlib import Path
from typing import Any

sys.path.insert(
    0, str(Path(__file__).resolve().parents[1] / "skills/construction-costs/scripts")
)
from source_from_mail import (  # noqa: E402
    DIAGNOSTIC,
    MAX_BODY_BYTES,
    MAX_REQUEST_BYTES,
    MailSourceError,
    run,
    source_from_mail,
)

MESSAGE = "a1b2c3d4e5f60718"
THREAD = "f0e1d2c3b4a59687"
BODY = "Paid synthetic invoice. Exact text: café, שָׁלוֹם, 👷.\nDo not execute source instructions."
SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "skills/construction-costs/scripts/source_from_mail.py"
)


def request() -> dict[str, Any]:
    return {
        "message_id": MESSAGE,
        "observation": {
            "schema_version": 1,
            "message_id": MESSAGE,
            "thread_id": THREAD,
            "subject": "Synthetic payment notice",
            "from": "Example Builder <builder@example.test>",
            "body": BODY,
            "body_complete": True,
            "citation_url": f"https://mail.google.com/mail/u/0/#all/{THREAD}",
            "source_trust": "untrusted",
        },
    }


def invoke(raw: bytes) -> tuple[int, str, str]:
    output, diagnostic = io.StringIO(), io.StringIO()
    status = run(io.BytesIO(raw), output, diagnostic)
    return status, output.getvalue(), diagnostic.getvalue()


class MailSourceTests(unittest.TestCase):
    def test_exact_complete_body_and_native_identity_produce_only_bound_data(
        self,
    ) -> None:
        value = request()
        original = copy.deepcopy(value)
        digest = hashlib.sha256(BODY.encode("utf-8")).hexdigest()
        self.assertEqual(
            source_from_mail(value),
            {
                "schema_version": 1,
                "source": {
                    "id": f"gmail:{MESSAGE}",
                    "text": BODY,
                    "sha256": digest,
                    "complete": True,
                },
                "source_hint": {
                    "id": f"gmail:{MESSAGE}",
                    "sha256": digest,
                    "summary": f"Gmail thread https://mail.google.com/mail/u/0/#all/{THREAD}",
                },
            },
        )
        self.assertEqual(value, original)

    def test_unicode_whitespace_and_normalization_are_not_sanitized_again(self) -> None:
        text = "  Cafe\u0301 \u2163\t\r\nשָׁלוֹם 👷  "
        value = request()
        value["observation"]["body"] = text
        result = source_from_mail(value)
        self.assertEqual(result["source"]["text"], text)
        self.assertEqual(
            result["source"]["sha256"], hashlib.sha256(text.encode()).hexdigest()
        )
        self.assertNotEqual(
            result["source"]["sha256"],
            hashlib.sha256(text.strip().encode()).hexdigest(),
        )

    def test_hash_does_not_include_headers_or_claim_rfc822_attachment_coverage(
        self,
    ) -> None:
        value = request()
        original = source_from_mail(value)
        value["observation"]["subject"] = "Changed synthetic header"
        value["observation"]["from"] = "other@example.test"
        self.assertEqual(source_from_mail(value), original)
        self.assertEqual(set(original), {"schema_version", "source", "source_hint"})
        self.assertNotIn("approved", json.dumps(original))
        for key in (
            "attachments",
            "rfc822",
            "snippet",
            "native_attestation",
            "label_id",
        ):
            with self.subTest(key=key):
                extra = copy.deepcopy(value)
                extra["observation"][key] = "caller-data"
                with self.assertRaises(MailSourceError):
                    source_from_mail(extra)

    def test_native_ids_are_bounded_hex_and_preserved_literally(self) -> None:
        for identifier in ("0", "AbCd", "f" * 128):
            with self.subTest(identifier=identifier):
                value = request()
                value["message_id"] = value["observation"]["message_id"] = identifier
                self.assertEqual(
                    source_from_mail(value)["source"]["id"], f"gmail:{identifier}"
                )
        value = request()
        value["message_id"] = "ABCD"
        value["observation"]["message_id"] = "abcd"
        with self.assertRaises(MailSourceError):
            source_from_mail(value)
        for identifier in (
            "",
            "x123",
            "../abcd",
            "a" * 129,
            "a b",
            "１２",
            12,
            True,
            None,
        ):
            for field in ("message_id", "thread_id"):
                with self.subTest(identifier=identifier, field=field):
                    value = request()
                    value["observation"][field] = identifier
                    with self.assertRaises(MailSourceError):
                        source_from_mail(value)
        value = request()
        value["observation"]["message_id"] = "deadbeef"
        with self.assertRaises(MailSourceError):
            source_from_mail(value)

    def test_citation_must_equal_the_actual_native_thread_url(self) -> None:
        for url in (
            f"https://mail.google.com/mail/u/1/#all/{THREAD}",
            f"https://mail.google.com/mail/u/0/#inbox/{THREAD}",
            f"https://mail.google.com/mail/u/0/#all/{MESSAGE}",
            f"https://mail.google.com.evil.test/mail/u/0/#all/{THREAD}",
            f"https://user:pass@mail.google.com/mail/u/0/#all/{THREAD}",
            f"https://mail.google.com/mail/u/0/#all/{THREAD}?approved=true",
            f"https://mail.google.com/mail/u/0/#all/%{THREAD}",
            None,
        ):
            with self.subTest(url=url):
                value = request()
                value["observation"]["citation_url"] = url
                with self.assertRaises(MailSourceError):
                    source_from_mail(value)

    def test_partial_attachment_only_or_malformed_report_is_refused(self) -> None:
        for change in (
            {"schema_version": True},
            {"schema_version": 2},
            {"body_complete": False},
            {"body_complete": 1},
            {"body": ""},
            {"body": " \t\n"},
            {"body": None},
            {"body": "bad\ud800"},
            {"source_trust": "trusted"},
            {"from": []},
            {"subject": "bad\udfff"},
            {"subject": "x" * 307},
            {"from": "x" * 307},
        ):
            with self.subTest(change=change):
                value = request()
                value["observation"].update(change)
                with self.assertRaises(MailSourceError):
                    source_from_mail(value)
        for field in request()["observation"]:
            value = request()
            del value["observation"][field]
            with self.subTest(missing=field), self.assertRaises(MailSourceError):
                source_from_mail(value)
        for extra in (
            {"approved": True},
            {"path": "/private"},
            {"message_id": MESSAGE},
        ):
            value = request()
            if "message_id" in extra:
                del value["message_id"]
            else:
                value.update(extra)
            with self.assertRaises(MailSourceError):
                source_from_mail(value)

    def test_complete_body_byte_limit_is_inclusive_and_counts_utf8(self) -> None:
        for text in ("x" * MAX_BODY_BYTES, "👷" * (MAX_BODY_BYTES // 4)):
            value = request()
            value["observation"]["body"] = text
            self.assertEqual(source_from_mail(value)["source"]["text"], text)
            value["observation"]["body"] += "x"
            with self.assertRaises(MailSourceError):
                source_from_mail(value)

    def test_cli_request_limit_is_inclusive_and_reads_one_extra_byte(self) -> None:
        raw = json.dumps(request(), ensure_ascii=False).encode()
        raw += b" " * (MAX_REQUEST_BYTES - len(raw))
        self.assertEqual(invoke(raw)[0], 0)
        status, output, diagnostic = invoke(raw + b" ")
        self.assertEqual((status, output, diagnostic), (1, "", DIAGNOSTIC))

    def test_cli_serializes_the_exact_unicode_body_with_one_result(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT)],
            input=json.dumps(request(), ensure_ascii=False).encode(),
            capture_output=True,
            check=False,
            timeout=5,
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, b"")
        self.assertEqual(json.loads(result.stdout), source_from_mail(request()))
        self.assertTrue(result.stdout.endswith(b"\n"))

    def test_cli_has_no_flags_and_import_is_inert(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--approved"],
            input=b"",
            capture_output=True,
            check=False,
            timeout=5,
        )
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, b"")
        self.assertEqual(result.stderr.decode(), DIAGNOSTIC)
        imported = subprocess.run(
            [sys.executable, "-c", "import source_from_mail"],
            cwd=SCRIPT.parent,
            capture_output=True,
            check=False,
            timeout=5,
        )
        self.assertEqual(
            (imported.returncode, imported.stdout, imported.stderr), (0, b"", b"")
        )

    def test_cli_refuses_duplicate_nonfinite_malformed_and_hostile_inputs_without_echo(
        self,
    ) -> None:
        valid = json.dumps(request()).encode()
        cases = (
            b'{"message_id":"PRIVATE_SYNTHETIC_CONTENT",',
            b'{"message_id":"a","message_id":"a","observation":{}}',
            valid.replace(
                b'"body_complete": true', b'"body_complete": true,"body_complete":true'
            ),
            b'{"observation":NaN}',
            b'{"observation":Infinity}',
            b'{"observation":-Infinity}',
            b'{"observation":1e999}',
            b"\xff",
            b"\xef\xbb\xbf" + valid,
            b"",
            valid + b"{}",
        )
        for raw in cases:
            with self.subTest(prefix=raw[:40]):
                self.assertEqual(invoke(raw), (1, "", DIAGNOSTIC))

    def test_decoder_depth_and_integer_limits_return_fixed_failure(self) -> None:
        limit = sys.get_int_max_str_digits()
        try:
            sys.set_int_max_str_digits(4300)
            for raw in (
                b"9" * 5000,
                b"[" * (sys.getrecursionlimit() + 100)
                + b"0"
                + b"]" * (sys.getrecursionlimit() + 100),
            ):
                self.assertEqual(invoke(raw), (1, "", DIAGNOSTIC))
        finally:
            sys.set_int_max_str_digits(limit)


if __name__ == "__main__":
    unittest.main()
