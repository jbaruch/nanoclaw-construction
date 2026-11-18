[![tessl](https://img.shields.io/endpoint?url=https%3A%2F%2Fapi.tessl.io%2Fv1%2Fbadges%2Fjbaruch%2Fnanoclaw-construction)](https://tessl.io/registry/jbaruch/nanoclaw-construction)

# NanoClaw Construction

Overlay for the house build: the site camera, and the construction payments sheet
tracked in [nanoclaw#1039](https://github.com/jbaruch/nanoclaw/issues/1039).

## Install

```sh
tessl install jbaruch/nanoclaw-construction
```

Installation loads the skills and their rules.

`construction-site` answers «чо там как на стройке» from the camera frames on main's
read-only `construction-site` mount, and saves a digest each evening at 18:30 site time
for the morning brief. It reads frames only.

`construction-costs` turns a forwarded invoice or payment notice into a five-cell row
(date, purpose, payee, amount, method), shows it on a Да/Нет card and, after «Записать»,
appends it to the «Construction costs» sheet with `scripts/costs.py`, which refuses an
identical row and reads the written row back. It needs a Google Sheets connection on
main's OneCLI tier and `/workspace/group/construction-costs.json` with the `sheet_id`.
It never creates bank payments.

Run checks with the pinned `requirements-dev.txt` tools and unittest.

## Dependency updates

[Renovate](renovate.json) is the only dependency update scanner. Its native
[pip requirements manager](https://docs.renovatebot.com/modules/manager/pip_requirements/)
covers [requirements-dev.txt](requirements-dev.txt), and its
[GitHub Actions manager](https://docs.renovatebot.com/modules/manager/github-actions/)
covers actions and reusable workflows in [.github/workflows](.github/workflows).

The update window is `before 6am on monday`. Updates use `chore(deps)` commits,
with at most five concurrent PRs and one group for minor, patch and digest updates.
Renovate opens the grouped updates automatically. For major updates,
[the dependency-update requirements](https://github.com/jbaruch/nanoclaw/issues/1433)
explicitly require `dependencyDashboardApproval: true` in [renovate.json](renovate.json).
Select the major update's checkbox in the Dependency Dashboard to allow branch
and PR creation; see [Renovate's approval documentation](https://docs.renovatebot.com/configuration-options/#dependencydashboardapproval).

Validate configuration changes from the repository root:

```sh
npx --yes --package renovate -- renovate-config-validator renovate.json
```

## Rules

| Rule | Purpose |
| --- | --- |
| [nanoclaw-skill-root](rules/nanoclaw-skill-root.md) | Resolve fixed installed skill paths. |

## Skills

| Skill | Purpose |
| --- | --- |
| [construction-costs](skills/construction-costs/SKILL.md) | Turn a payment into a row, ask on a Да/Нет card, append it after «Записать». |
| [construction-site](skills/construction-site/SKILL.md) | Answer site questions from the camera frames and save the daily digest. |

## Review and Publication

The `.github/fleet-review-enabled` marker enrolls independent policy and code
quality review. `.github/workflows/publish.yml` publishes each merge to `main`
through the shared coding-policy publish workflow, like the other NanoClaw
plugins, and stamps `CHANGELOG.md`.

Publication does not establish native runtime acceptance. This package contains
no financial data or credentials.
