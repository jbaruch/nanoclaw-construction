# Payment proposal component

This component is an inactive foundation for
[nanoclaw#1039](https://github.com/jbaruch/nanoclaw/issues/1039). It has no
SKILL entrypoint, plugin manifest, cadence, network access, approval consumer,
or spreadsheet writer. Do not register or publish it as a delivered overlay.

`scripts/payment_proposal.py` reads one schema-1 JSON request from stdin, at
most 4 MiB, and emits one schema-1 proposal. Invalid input returns nonzero
with empty stdout and a diagnostic that contains no source content. The
request and report are transient observations; this component owns no state.

The request has `source`, `extraction`, and `journal` objects. `source` carries
the actual source `id`, complete sanitized `text`, its UTF-8 `sha256`, and
`complete: true`. A model reads that full source and supplies `extraction`:
`document_kind` (`invoice` or `payment_confirmation`), `payment_status`,
`date`, `purpose`, `payee`, `amount`, `currency`, and `payment_method`. Every
field except document kind is a fact object with exactly `value`, `source_id`,
and `quote`. Unknown facts use null for all three. Quotes must occur in the
bound source. This is provenance validation; it does not prove a model's
semantic interpretation correct.

`journal` contains `complete: true`, five `headers`, and all observed `rows`
after the header, using displayed string values in sheet order. Header names
are Date, Purpose, Recepient (also Recipient or Payee), Amount, Payment type.
Dates use the existing US display convention. Amounts represent USD with
exact cents. Unsupported or partial journal observations refuse comparison.
An invoice or pending notice requires payment clarification. No field defaults
to the mail receipt date, sender name, guessed amount, or converted currency.

The result reports `needs_clarification`, `already_recorded`,
`possible_duplicate`, or `ready_for_owner_review`. Matching sheet row numbers
include the header offset. Same-date/payee/amount rows remain possible
duplicates even if purpose or method differs. `write_authorized` is always
false, including for a complete proposal. Only a future host-owned, exact-row
approval consumer can authorize an append, with a fresh complete sheet read,
durable pre-dispatch intent, and uncertain-outcome recovery without replay.

Native intake, full model classification, protected owner approval, OneCLI
Sheets access, approved append, publication, and installed runtime acceptance
remain required before this feature can ship. All tests use synthetic data.
