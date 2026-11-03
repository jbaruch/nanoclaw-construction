#!/usr/bin/env python3
"""Read the construction camera's frames: health numbers, contact sheets, daily digest.

Commands, each printing one JSON object on stdout:

  health --hours 07:00-18:00 --every 5 [--date D]
      Frame counts, gaps, odd frames and plain problems for one site day.
  sheet --window 10:00-13:00 --step 5 [--date D] | --at 2026-11-02T10:40 ...
        [--kind scheduled|manual] [--cols 4] [--tile 480] [--crop x,y,w,h]
      Renders the selected frames to one PNG and prints its path. Crop is in
      full-resolution pixels; --tile is the width of each tile.
  save-digest --hours 07:00-18:00 --every 5
      stdin {site_date, lines, frames}. Stores that day's digest with its health.
  digest [--date D]
      That day's digest, or the last finished capture day's. A day without one is
      availability "unavailable", never a quiet day.

Times are wall-clock in the frames' own time zone. A failure exits 1 with a repair
on stderr and nothing on stdout. The camera mount is read, never written.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

FRAMES = Path("/workspace/extra/construction-site")
DIGESTS = Path("/workspace/group/state/construction-site")
SCHEMA = 1
# A frame lands about 20 seconds after its slot; don't count it missing before then.
ARRIVAL_GRACE = timedelta(minutes=2)
# Matches this skill's cadence: the 18:00 frame is in and the digest run has started.
DAY_FINISHED_AT = time(18, 30)
STALE_SLOTS = 3
LOW_BATTERY_PERCENT = 20
RENDER_TIMEOUT_SECONDS = 180


class SiteError(ValueError):
    """A request or a stored file this script can't honor; the message says what to do."""


@dataclass(frozen=True)
class Frame:
    at: datetime
    capture_id: str
    path: Path
    meta: dict[str, Any]


def utc_now() -> datetime:
    return datetime.now(UTC)


def read_meta(capture: Path) -> dict[str, Any]:
    value = json.loads((capture / "metadata.json").read_text())
    if not isinstance(value, dict):
        raise ValueError("metadata is not an object")
    return value


def day_folders() -> list[Path]:
    return sorted(FRAMES.glob("[0-9][0-9][0-9][0-9]/[0-9][0-9]/[0-9][0-9]"))


def site_zone() -> ZoneInfo:
    """The site's zone, from the newest readable frame."""
    for folder in reversed(day_folders()):
        for capture in sorted(folder.iterdir()):
            try:
                return ZoneInfo(read_meta(capture)["site_time_zone"])
            except (OSError, ValueError, KeyError, ZoneInfoNotFoundError):
                continue
    raise SiteError(
        f"No readable frames under {FRAMES}. Check that main has the construction-site "
        "mount and that the eufy-time-lapse service is writing."
    )


def load_day(day: date, zone: ZoneInfo) -> tuple[list[Frame], list[str]]:
    """Every frame of a site day in time order, plus folders that couldn't be read."""
    folder = FRAMES / f"{day.year:04d}" / f"{day.month:02d}" / f"{day.day:02d}"
    frames: list[Frame] = []
    unreadable: list[str] = []
    if not folder.is_dir():
        return frames, unreadable
    for capture in sorted(folder.iterdir()):
        try:
            meta = read_meta(capture)
            received = datetime.fromisoformat(
                meta["frame_received_at"].replace("Z", "+00:00")
            )
        except (OSError, ValueError, KeyError, AttributeError):
            unreadable.append(capture.name)
            continue
        frames.append(
            Frame(received.astimezone(zone), capture.name, capture / "frame.jpg", meta)
        )
    frames.sort(key=lambda frame: frame.at)
    return frames, unreadable


def parse_span(value: str) -> tuple[time, time]:
    try:
        first, last = (time.fromisoformat(part) for part in value.split("-"))
    except ValueError:
        raise SiteError(f"Use HH:MM-HH:MM, got {value!r}.") from None
    if last <= first:
        raise SiteError(f"The span {value!r} must end after it starts.")
    return first, last


def parse_date(value: str | None, zone: ZoneInfo, now: datetime) -> date:
    if value is None:
        return now.astimezone(zone).date()
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise SiteError(f"Use YYYY-MM-DD, got {value!r}.") from None


def odd_reasons(meta: dict[str, Any]) -> list[str]:
    reasons = []
    if meta.get("kind") != "scheduled":
        reasons.append(f"kind {meta.get('kind')}")
    if meta.get("quality_status") != "ok":
        reasons.append(f"quality {meta.get('quality_status')}")
    if meta.get("source") != "live_p2p":
        reasons.append(f"source {meta.get('source')}")
    if meta.get("retained"):
        reasons.append("retained")
    return reasons


def slot_time(frame: Frame, zone: ZoneInfo) -> datetime:
    """The slot a frame was scheduled for. It can arrive a minute or more after it."""
    value = frame.meta.get("scheduled_at_utc")
    if not isinstance(value, str):
        return frame.at
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(zone)
    except ValueError:
        return frame.at


def health(
    day: date, hours: tuple[time, time], every: int, zone: ZoneInfo, now: datetime
) -> dict:
    """Capture hours include their start and exclude their end: 07:00-18:00 ends at 17:55."""
    if every < 1:
        raise SiteError("The capture interval must be at least one minute.")
    frames, unreadable = load_day(day, zone)
    start = datetime.combine(day, hours[0], zone)
    end = datetime.combine(day, hours[1], zone)
    current = now.astimezone(zone)
    slot = timedelta(minutes=every)
    slots = sorted(
        moment
        for moment in (
            slot_time(frame, zone)
            for frame in frames
            if frame.meta.get("kind") == "scheduled"
        )
        if start <= moment < end
    )

    latest_due = min(current - ARRIVAL_GRACE, end - timedelta.resolution)
    expected = 0 if latest_due < start else (latest_due - start) // slot + 1
    missing = max(0, expected - len(slots))
    gaps = [
        {
            "from": a.strftime("%H:%M"),
            "to": b.strftime("%H:%M"),
            "minutes": round((b - a).total_seconds() / 60),
        }
        for a, b in zip(slots, slots[1:], strict=False)
        if b - a > slot
    ]
    odd = [
        {"time": f.at.strftime("%H:%M"), "capture_id": f.capture_id, "reasons": reasons}
        for f in frames
        if (reasons := odd_reasons(f.meta))
    ]
    newest = frames[-1] if frames else None
    battery = newest.meta.get("battery_percent") if newest else None

    problems = []
    if expected and not frames:
        problems.append("no frames for this day")
    elif newest and start <= current < end and current - newest.at > STALE_SLOTS * slot:
        age = round((current - newest.at).total_seconds() / 60)
        problems.append(f"newest frame is {age} minutes old")
    if frames and missing:
        problems.append(f"{missing} of {expected} scheduled frames missing")
    problems.extend(
        f"gap {g['from']} to {g['to']}, {g['minutes']} minutes" for g in gaps
    )
    problems.extend(
        f"frame at {row['time']}: {', '.join(row['reasons'])}"
        for row in odd
        if row["reasons"] != ["kind manual"]
    )
    if unreadable:
        problems.append(f"{len(unreadable)} capture folders unreadable")
    if isinstance(battery, int | float) and battery < LOW_BATTERY_PERCENT:
        problems.append(f"battery at {battery}%")

    return {
        "date": day.isoformat(),
        "time_zone": zone.key,
        "frames": len(frames),
        "scheduled": len(slots),
        "expected_by_now": expected,
        "missing": missing,
        "newest": (
            {
                "time": newest.at.strftime("%H:%M"),
                "age_minutes": round((current - newest.at).total_seconds() / 60),
                "capture_id": newest.capture_id,
            }
            if newest
            else None
        ),
        "battery_percent": battery,
        "gaps": gaps,
        "odd": odd,
        "unreadable": unreadable,
        "problems": problems,
    }


def nearest(frames: list[Frame], target: datetime) -> Frame | None:
    return min(frames, key=lambda frame: abs(frame.at - target), default=None)


def select_window(
    frames: list[Frame], day: date, span: tuple[time, time], step: int, zone: ZoneInfo
) -> list[Frame]:
    """The frame nearest each step of the window; a step with no frame near it is skipped."""
    if step < 1:
        raise SiteError("The step must be at least one minute.")
    selected: list[Frame] = []
    target = datetime.combine(day, span[0], zone)
    end = datetime.combine(day, span[1], zone)
    while target <= end:
        frame = nearest(frames, target)
        if (
            frame is not None
            and abs(frame.at - target) * 2 <= timedelta(minutes=step)
            and frame not in selected
        ):
            selected.append(frame)
        target += timedelta(minutes=step)
    return selected


def select_times(moments: list[str], kind: str, zone: ZoneInfo) -> list[Frame]:
    selected = []
    for moment in moments:
        try:
            target = datetime.fromisoformat(moment).replace(tzinfo=zone)
        except ValueError:
            raise SiteError(f"Use YYYY-MM-DDTHH:MM for --at, got {moment!r}.") from None
        frames, _ = load_day(target.date(), zone)
        frame = nearest([f for f in frames if f.meta.get("kind") == kind], target)
        if frame is None:
            raise SiteError(
                f"No {kind} frame on {target.date()}; run health for that day."
            )
        selected.append(frame)
    return selected


def parse_crop(value: str | None) -> tuple[int, int, int, int] | None:
    if value is None:
        return None
    try:
        x, y, w, h = (int(part) for part in value.split(","))
    except ValueError:
        raise SiteError(
            f"Use x,y,w,h in full-resolution pixels, got {value!r}."
        ) from None
    if min(x, y) < 0 or min(w, h) < 1:
        raise SiteError(f"The crop {value!r} needs a position and a size.")
    return x, y, w, h


def sheet_html(frames: list[Frame], cols: int, tile: int, crop) -> tuple[str, int, int]:
    """A contact sheet page and its pixel size."""
    cells = []
    tile_height = 0
    for frame in frames:
        full_w, full_h = frame.meta.get("width", 3840), frame.meta.get("height", 2160)
        x, y, w, h = crop or (0, 0, full_w, full_h)
        scale = tile / w
        tile_height = round(h * scale)
        style = (
            f"width:{tile}px;height:{tile_height}px;"
            f"background-image:url('{html.escape(frame.path.as_uri())}');"
            f"background-size:{round(full_w * scale)}px {round(full_h * scale)}px;"
            f"background-position:{-round(x * scale)}px {-round(y * scale)}px"
        )
        label = frame.at.strftime("%m-%d %H:%M")
        if frame.meta.get("kind") != "scheduled":
            label += f" {frame.meta.get('kind')}"
        cells.append(
            f'<div class="c" style="{style}"><span>{html.escape(label)}</span></div>'
        )
    rows = (len(frames) + cols - 1) // cols
    width = cols * tile + (cols + 1) * 4
    height = rows * (tile_height + 4) + 4
    page = (
        f'<html><body style="margin:0;background:#000;width:{width}px"><style>'
        ".c{display:inline-block;margin:4px 0 0 4px;position:relative;vertical-align:top}"
        ".c span{position:absolute;left:4px;top:2px;color:#ff0;font:bold 20px sans-serif;"
        "text-shadow:0 0 3px #000,0 0 3px #000}"
        f"</style>{''.join(cells)}</body></html>"
    )
    return page, width, height


def render(page: str, width: int, height: int) -> Path:
    """Render a page to a PNG with the image's headless Chromium."""
    # The PNG outlives this call so the agent can read it; the browser profile doesn't.
    folder = Path(tempfile.mkdtemp(prefix="construction-site-"))
    source, output = folder / "sheet.html", folder / "sheet.png"
    source.write_text(page)
    try:
        with tempfile.TemporaryDirectory(prefix="construction-chromium-") as profile:
            result = subprocess.run(
                [
                    "chromium",
                    "--headless=new",
                    "--no-sandbox",
                    "--disable-gpu",
                    "--hide-scrollbars",
                    "--allow-file-access-from-files",
                    f"--user-data-dir={profile}",
                    "--virtual-time-budget=15000",
                    f"--window-size={width},{height}",
                    f"--screenshot={output}",
                    source.as_uri(),
                ],
                capture_output=True,
                text=True,
                timeout=RENDER_TIMEOUT_SECONDS,
                check=False,
            )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise SiteError(
            f"Chromium could not render the sheet: {error}. Try fewer tiles."
        ) from None
    if result.returncode != 0 or not output.is_file():
        tail = result.stderr[-300:]
        raise SiteError(
            f"Chromium could not render the sheet (exit {result.returncode}): {tail}"
        )
    return output


def sheet(args: argparse.Namespace, zone: ZoneInfo, now: datetime) -> dict:
    if args.cols < 1 or args.tile < 1:
        raise SiteError("Use at least one column and a positive tile width.")
    if args.at:
        if args.window or args.date:
            raise SiteError("Use --at alone, or --window with an optional --date.")
        selected = select_times(args.at, args.kind, zone)
    else:
        if not args.window or args.step is None:
            raise SiteError("Use --window with --step, or --at.")
        day = parse_date(args.date, zone, now)
        frames, _ = load_day(day, zone)
        selected = select_window(
            [f for f in frames if f.meta.get("kind") == args.kind],
            day,
            parse_span(args.window),
            args.step,
            zone,
        )
    if not selected:
        raise SiteError("No frames in that window; run health for that day.")
    page, width, height = sheet_html(
        selected, args.cols, args.tile, parse_crop(args.crop)
    )
    return {
        "png": str(render(page, width, height)),
        "width": width,
        "height": height,
        "frames": [
            {
                "date": frame.at.date().isoformat(),
                "time": frame.at.strftime("%H:%M"),
                "kind": frame.meta.get("kind"),
                "capture_id": frame.capture_id,
            }
            for frame in selected
        ],
    }


def finished_day(zone: ZoneInfo, now: datetime) -> date:
    """The last capture day that is over."""
    current = now.astimezone(zone)
    if current.time() >= DAY_FINISHED_AT:
        return current.date()
    return current.date() - timedelta(days=1)


def digest_path(day: date) -> Path:
    return DIGESTS / f"digest-{day.isoformat()}.json"


def save_digest(raw: str, hours, every: int, zone: ZoneInfo, now: datetime) -> dict:
    try:
        value = json.loads(raw)
    except ValueError:
        raise SiteError("Supply the digest as JSON on stdin.") from None
    if not isinstance(value, dict) or set(value) != {"site_date", "lines", "frames"}:
        raise SiteError("Supply exactly site_date, lines and frames.")
    if not isinstance(value["site_date"], str):
        raise SiteError("Supply site_date as YYYY-MM-DD, the wake's date.")
    day = parse_date(value["site_date"], zone, now)
    lines, cited = value["lines"], value["frames"]
    if (
        not isinstance(lines, list)
        or not lines
        or not all(isinstance(line, str) and line.strip() for line in lines)
    ):
        raise SiteError(
            "Supply at least one line; a quiet day still gets one short line."
        )
    if not isinstance(cited, list) or not all(isinstance(row, str) for row in cited):
        raise SiteError("Supply frames as the list of capture ids the lines cite.")
    record = {
        "schema_version": SCHEMA,
        "site_date": day.isoformat(),
        "lines": lines,
        "frames": cited,
        "health": health(day, hours, every, zone, now),
        "saved_at": now.isoformat(),
    }
    DIGESTS.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = digest_path(day)
    handle, temporary = tempfile.mkstemp(dir=DIGESTS, prefix=f".{path.name}.")
    with os.fdopen(handle, "w") as stream:
        json.dump(record, stream, ensure_ascii=False)
    os.replace(temporary, path)
    return {"saved": str(path), "site_date": record["site_date"]}


def read_digest(day: date) -> dict:
    """A stored digest; anything but this schema is no digest for that day."""
    unavailable = {
        "schema_version": SCHEMA,
        "availability": "unavailable",
        "site_date": day.isoformat(),
    }
    try:
        value = json.loads(digest_path(day).read_text())
    except FileNotFoundError:
        return unavailable
    except ValueError:
        raise SiteError(
            f"Digest {digest_path(day)} is damaged; remove it to rerun."
        ) from None
    if not isinstance(value, dict) or value.get("schema_version") != SCHEMA:
        return unavailable
    return {**value, "availability": "available"}


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    check = commands.add_parser("health")
    check.add_argument("--date")
    check.add_argument("--hours", required=True)
    check.add_argument("--every", type=int, required=True)
    draw = commands.add_parser("sheet")
    draw.add_argument("--date")
    draw.add_argument("--window")
    draw.add_argument("--step", type=int)
    draw.add_argument("--at", action="append")
    draw.add_argument("--kind", choices=("scheduled", "manual"), default="scheduled")
    draw.add_argument("--cols", type=int, default=4)
    draw.add_argument("--tile", type=int, default=480)
    draw.add_argument("--crop")
    keep = commands.add_parser("save-digest")
    keep.add_argument("--hours", required=True)
    keep.add_argument("--every", type=int, required=True)
    show = commands.add_parser("digest")
    show.add_argument("--date")
    return root


def run(args: argparse.Namespace, zone: ZoneInfo, now: datetime) -> dict:
    if args.command == "health":
        day = parse_date(args.date, zone, now)
        return health(day, parse_span(args.hours), args.every, zone, now)
    if args.command == "sheet":
        return sheet(args, zone, now)
    if args.command == "save-digest":
        return save_digest(
            sys.stdin.read(), parse_span(args.hours), args.every, zone, now
        )
    return read_digest(
        parse_date(args.date, zone, now) if args.date else finished_day(zone, now)
    )


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        print(json.dumps(run(args, site_zone(), utc_now()), ensure_ascii=False))
    except SiteError as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
