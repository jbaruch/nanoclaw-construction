[![tessl](https://img.shields.io/endpoint?url=https%3A%2F%2Fapi.tessl.io%2Fv1%2Fbadges%2Fjbaruch%2Fnanoclaw-construction)](https://tessl.io/registry/jbaruch/nanoclaw-construction)

# NanoClaw Construction

Construction integration boundary for NanoClaw, tracked in
[nanoclaw#1039](https://github.com/jbaruch/nanoclaw/issues/1039).

## Install

```sh
tessl install jbaruch/nanoclaw-construction
```

Installation loads the boundary rule. It grants no provider access, registers no
runtime overlay and enables no spreadsheet write.

## Rules

| Rule | Purpose |
| --- | --- |
| [construction-provider-boundary](rules/construction-provider-boundary.md) | Require published native authority and content-bound owner approval for construction writes. |

## Skills

| Skill | Purpose |
| --- | --- |
| None | This bootstrap declares no executable skill. |

## Review and Publication

The `.github/fleet-review-enabled` marker enrolls independent policy and code
quality review. `.github/fleet-publish-enabled` enrolls source-bound Tessl
publication through the
[central coding-policy owner](https://github.com/jbaruch/coding-policy/blob/main/skills/release/references/fleet-publication.md).
That owner validates the projected package, stamps `CHANGELOG.md`, publishes and
confirms registry and moderation results. Publication credentials and App
permissions remain in `coding-policy`. This repository has no competing
publisher workflow or dispatch secret.

The payment journal implementation and its native acceptance remain separate
work. This boundary-only package contains no financial data or credentials.
