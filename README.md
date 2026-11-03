[![tessl](https://img.shields.io/endpoint?url=https%3A%2F%2Fapi.tessl.io%2Fv1%2Fbadges%2Fjbaruch%2Fnanoclaw-construction)](https://tessl.io/registry/jbaruch/nanoclaw-construction)

# NanoClaw Construction

Overlay for the house build: the site camera, and the construction payment journal
tracked in [nanoclaw#1039](https://github.com/jbaruch/nanoclaw/issues/1039).

## Install

```sh
tessl install jbaruch/nanoclaw-construction
```

Installation loads the skills and their rules. It grants no provider access,
registers no runtime overlay and enables no spreadsheet write.

`construction-site` answers «чо там как на стройке» from the camera frames on main's
read-only `construction-site` mount, and saves a digest each evening at 18:30 site time
for the morning brief. It reads frames only.

For payments, the source includes a one-shot main skill, complete-source validators and the
fixed owner callback provider. It selects candidate threads with Gmail label
`NanoClaw/Construction`, proposes the complete payment row, asks for missing facts
and uses the host's exact owner buttons. It never creates bank payments.

The matching core producer owns native journal reads, private append gates,
Sheets routing and positive acknowledgment/readback confirmation. A lost result
never permits an automatic retry. No payment data, sheet ID or credential is
part of this repository.

The payment journal is not deployed. Host authority publication, the matching core
producer, OneCLI Sheets connection/grants, main overlay registration, label
setup and actual native owner acceptance remain required. This one-shot skill
declares no recurring task or change to personal email cadence.

Run Python checks with the pinned `requirements-dev.txt` tools and unittest;
run `npm ci`, `npm run format:check`, `npm run typecheck`, and `npm test` for the
stdlib Node callback boundary. Dev packages do not ship in the plugin.

## Rules

| Rule | Purpose |
| --- | --- |
| [construction-provider-boundary](rules/construction-provider-boundary.md) | Require published native authority and content-bound owner approval for construction writes. |
| [construction-journal-callbacks](rules/construction-journal-callbacks.md) | Bind journal writes to the exact protected native owner callback. |
| [nanoclaw-skill-root](rules/nanoclaw-skill-root.md) | Resolve fixed installed skill paths. |

## Skills

| Skill | Purpose |
| --- | --- |
| [construction-costs](skills/construction-costs/SKILL.md) | Prepare source-cited rows, obtain a full native journal preview and present exact owner choices. |
| [construction-site](skills/construction-site/SKILL.md) | Answer site questions from the camera frames and save the daily digest. |

## Review and Publication

The `.github/fleet-review-enabled` marker enrolls independent policy and code
quality review. `.github/fleet-publish-enabled` enrolls source-bound Tessl
publication through the
[central coding-policy owner](https://github.com/jbaruch/coding-policy/blob/main/skills/release/references/fleet-publication.md).
That owner validates the projected package, stamps `CHANGELOG.md`, publishes and
confirms registry and moderation results. Publication credentials and App
permissions remain in `coding-policy`. This repository has no competing
publisher workflow or dispatch secret.

Publication does not establish native runtime acceptance. This package contains
no financial data or credentials.
