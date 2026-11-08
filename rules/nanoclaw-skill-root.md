---
alwaysApply: false
applyTo: "skills/construction-costs/SKILL.md, skills/construction-site/SKILL.md, skills/construction-site/references/*.md — when invoking a co-shipped construction script"
description: Fixed installed construction skill lookup and data-only script protocols
---

# Construction Skill Root

- Authored scope: `skills/construction-costs/SKILL.md`.
- Native agent mount: `/home/node/.claude/skills/tessl__construction-costs/`.
- Co-shipped agent target: `scripts/costs.py` beneath that root, with the commands and output its docstring defines.
- Authored scope for the camera: `skills/construction-site/SKILL.md` and its `references/*.md`.
- Native agent mount: `/home/node/.claude/skills/tessl__construction-site/`.
- Co-shipped agent target: `scripts/frames.py` beneath that root, with the commands and output its docstring defines. `scripts/digest-precheck.py` runs only as the declared cadence precheck.
- Reference reads name the repository source and its corresponding native mounted path. No computed root, `.tessl/plugins` fallback or caller path selector is used.
- `tests/test_skill_script_paths.py` verifies the declared regular targets and authored command paths.
- A path or script result confers no owner approval; a row is written only after Baruch's «Записать».
