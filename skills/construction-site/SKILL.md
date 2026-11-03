---
name: construction-site
description: >
  Answer what is happening on the house build from the site camera's frames, and
  save a daily digest for the morning brief. Use for «чо там как на стройке»,
  «что нового на стройке», «что было вчера на стройке», "what happened on site
  today", "is anyone on site" and "is the construction camera working". Reads
  camera frames only. Main only.
cadence: "30 18 * * * (TZ=America/Chicago)"
script: "scripts/digest-precheck.py"
agentModel: "claude-opus-5-5[1m]"
---

# Construction Site

This skill is an action router — pick the step that matches the user's intent and execute only that step. Do not run other steps; do not parallelize. A question from the owner uses Step 1. A scheduled wake whose script output has `site_date` uses Step 2.

## Step 1 — Answer A Site Question

For a past day, try its saved digest first:

```bash
python3 /home/node/.claude/skills/tessl__construction-site/scripts/frames.py digest --date <YYYY-MM-DD>
```

With `availability: "available"`, answer from its `lines` and `health`. Otherwise read the frames for that day. For today, always read the frames. Read and follow the whole procedure:

```text
skills/construction-site/references/reading-frames.md
```

At `/home/node/.claude/skills/tessl__construction-site/references/reading-frames.md`.

Answer in Russian, in this order:

- The camera's problems, only when there are any.
- The newest frame's site time.
- What changed, with times.
- Any frame that points off.

A quiet day with a healthy camera gets one short line. Finish here.

## Step 2 — Save The Daily Digest

Read and follow the whole procedure for the wake's `site_date`:

```text
skills/construction-site/references/reading-frames.md
```

At `/home/node/.claude/skills/tessl__construction-site/references/reading-frames.md`.

Write a private JSON file with exactly these fields, and with `lines` in Russian:

- `site_date`: the wake's date.
- `lines`: one short line each for work, deliveries, vehicles, people, new ruts or material, and camera problems. A quiet day with a healthy camera gets one line saying so, because a day with no work on a build is news too.
- `frames`: the capture ids the lines cite.

Save it:

```bash
python3 /home/node/.claude/skills/tessl__construction-site/scripts/frames.py save-digest --hours <hours> --every <every> < /tmp/construction-digest.json
```

A success prints the saved path. The morning brief reads the digest, so send nothing to the chat and produce no output. A failed save prints a repair on stderr: send that to the chat in Russian, since the brief would otherwise only say the digest is unavailable. Finish here.
