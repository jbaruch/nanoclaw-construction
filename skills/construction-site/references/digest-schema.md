# Daily digest

`scripts/frames.py` owns `/workspace/group/state/construction-site/digest-YYYY-MM-DD.json`. It alone writes, reads and migrates these files. The site skill's Step 2 supplies the content through `save-digest`. Other readers go through `frames.py digest`, including the morning brief's `jbaruch/nanoclaw-admin` `skills/morning-brief/scripts/construction-brief-source.py`.

| Field | Meaning |
| --- | --- |
| `schema_version` | `1` |
| `site_date` | The capture day, `YYYY-MM-DD` in the site's zone |
| `lines` | At least one non-empty line, in Russian |
| `frames` | The capture ids the lines cite |
| `health` | The `health` command's result when the digest was saved |
| `saved_at` | ISO timestamp of the save |

`digest` adds `availability: "available"`. A day with no file, or a file of another schema version, returns `{schema_version, availability: "unavailable", site_date}`. Readers report that as unavailable, never as a quiet day. A damaged file is a failure, with a repair on stderr.

A digest is what the camera showed when it was saved, and the frames remain the source.
