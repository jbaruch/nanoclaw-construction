#!/usr/bin/env python3
"""Nightly precheck: wake when the last finished capture day has no saved digest.

No arguments. The last stdout line is {"wake_agent": bool, "data": {"site_date": D}}.
A failure exits 1 with a repair on stderr, which the scheduler records as a failed run.
"""

from __future__ import annotations

import json
import sys

import frames


def main() -> int:
    try:
        zone = frames.site_zone()
    except frames.SiteError as error:
        print(str(error), file=sys.stderr)
        return 1
    day = frames.finished_day(zone, frames.utc_now())
    saved = frames.digest_path(day).exists()
    print(json.dumps({"wake_agent": not saved, "data": {"site_date": day.isoformat()}}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
