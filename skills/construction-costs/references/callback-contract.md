# Construction Journal Callback Contract v1

This contract belongs to `jbaruch/nanoclaw-construction`. The matching host
contract is `jbaruch/nanoclaw-host`'s
`skills/host-contracts/references/construction-journal-authority.md`.
Registration requires both actual installed contracts. Source branches and
synthetic fixtures supply no installed or provider acceptance.

## Proposed payment and owner decision

A proposal contains the complete ISO payment date, literal purpose, literal
payee, canonical positive USD amount with exactly two decimal cents, and one
new-write method: ACH, Wire, Check, Cash or Card. Source identity, SHA256 and
summary are cited hints. They prove neither a native payment nor owner approval.
Historical journal method labels remain literal read-only data.

The host builds the exact visible card from its protected proposal. It includes
all five row fields, source summary and any duplicate warning. Its two public
choices are «Добавить» or «Добавить ещё», and «Пропустить». Each choice carries only
`schema_version:1`, the opaque `proposal_id`, exact `row_sha256` and its
`decision` of `append` or `cancel`. Public card text, labels, choice order and
payload must match the stored proposal. Owner-facing card/status text is
Russian; quoted business values and wire identifiers remain literal. Generic owner-answer JSON cannot release
this effect.

The proposal expires after 24 hours. The private card transaction binds the
actual card to the protected proposal before publication. The configured owner
must claim that exact native Telegram card in the current main chat. The host
rechecks the current main registration, owner, claim, target, content, expiry
and duplicate count immediately before dispatch. No wrapper input replaces
those checks.

## Read and cancellation tools

`construction_journal_preview` receives the complete row and cited source hints.
It returns the host-built proposal/card and `write_authorized:false`; preview
never appends. `construction_journal_status` receives a 22-character proposal ID
and optional boolean `reconcile`, default false. Reconciliation reads only
existing append gates and exact live sheet evidence. It never appends or retries.
`construction_journal_cancel` can retract only an unreleased held proposal.
Attempted, uncertain and confirmed gates remain permanent.

The target spreadsheet is selected only by protected host configuration. The
native title is Construction costs, locale en_US, sheet ID 0 and title Sheet1.
No public sheet ID, credential, provider URL, host path, role, clock or executable
selector belongs in a callback payload.

## Private document diagnostics

Financial row values and source/document text must never enter shared host
logs at any level, including rejected requests and recoverable delivery errors.
The host classifies validated construction cards as sensitive before transport;
callers supply no privacy or approval flag. Preserve routing/length/fixed error
metadata and the protected uncertainty gate, without raw payload previews or
transport/JSON error objects. Recoverable delivery failures cannot authorize
replay; unexpected programming defects still surface.

## Fixed host lookup

The registered adapter is
`skills/construction-costs/scripts/construction-journal-callback-v1.mjs`.
It runs under the host's actual Node executable with exactly one argument
matching `^[A-Za-z0-9_-]{22}$`. That argument is the native callback ID, never
proposal JSON or an approval flag. Agent containers must not invoke this
host-only adapter as an alternative approval route.

The host supplies absolute `NANOCLAW_CALLBACK_HOST_ROOT`, its actual
`NANOCLAW_CALLBACK_NODE`, and fixed `NANOCLAW_CALLBACK_MAIN_GROUP` and
`NANOCLAW_CALLBACK_MAIN_CHAT`. Payloads cannot supply or replace them. Resolve
the real host directory and regular contained
`dist/construction-journal-callback-cli.js`. Select the trusted host working
directory before dynamic import. That module exports async
`runConstructionJournalCallbackV1(callbackId)`. Invoke it once with the opaque
callback ID; no provider operation occurs in this wrapper. The adapter selects
the cwd before starting its private worker, which performs the dynamic import.
Worker stdout/stderr remain private and are never forwarded; their combined
8,192-byte cap refuses overflow. A worker error or malformed/multiple result
refuses without exposing raw host diagnostics.

The host action owns the 300-second execution deadline, 2,048-byte stdout cap
and 24-hour card expiry. A deadline or lost result never clears an append gate.
Return exactly `{status,text}`, with status `applied`, `rejected`, `stale` or
`failed`, and text at most 200 valid Unicode scalars. Emit only that bounded
JSON object and a newline. Preserve handled failed results; never turn them
into applied. Invalid arguments, unsupported deployment, protocol violations
or unexpected failures exit nonzero with empty stdout and a fixed bounded
recovery diagnostic. Never emit raw source, provider errors, paths or credentials.

## Native append and recovery

The host's dedicated channel-free OneCLI identity is
`nanoclaw-host-construction-journal`. Its exact Sheets grant permits only
get_spreadsheet, get_values and append_values; no secrets, other reads, other
writes or ASK expansion. Actual least-privilege role readback precedes each
provider operation. Missing identity, connection, target or compatible authority
refuses; no ordinary chat route or credential fallback is allowed.

The host reads the full physical A:E journal with its native header Date,
Purpose, Recepient, Amount, Payment type. Internal blank gaps remain represented
by physical row offsets. Partial, malformed or clipped reads cannot authorize
a write. Immediately before the sole append POST, a synchronous private hook
revalidates the owner claim and stores its permanent intent under cross-source
and duplicate gates. Any dispatched unknown result remains uncertain.

Only a matching native 2xx one-row/five-cell append ACK followed by exact fresh
journal readback confirms the row. Store its native range, row hash and host
acknowledgment time. Reconciliation can grow positive facts for an existing
intent but cannot dispatch, replay, reconstruct owner choices or infer success
from unrelated rows. Cancellation cannot promise to undo a dispatched append.
Keep runtime acceptance open until the owner/root verifies the actual installed
role, target, native card decision and append/readback path.
