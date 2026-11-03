"""Site camera script against fixture frames shaped like the live metadata."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from datetime import UTC, date, datetime, time
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

SCRIPTS = Path(__file__).resolve().parents[1] / "skills/construction-site/scripts"
sys.path.insert(0, str(SCRIPTS))

import frames  # noqa: E402

ZONE = ZoneInfo("America/Chicago")
DAY = date(2026, 11, 2)
HOURS = (time(7), time(18))
# 2026-11-02 is CST, so 07:00 site time is 13:00 UTC.
AT_1410 = datetime(2026, 11, 2, 20, 10, tzinfo=UTC)
AFTER_HOURS = datetime(2026, 11, 3, 1, 0, tzinfo=UTC)


def live_meta(hhmm: str, day: date = DAY, **changes) -> dict:
    """The fields of a real frame's metadata.json from 2026-11-02."""
    site_time = datetime.combine(day, time.fromisoformat(hhmm), ZONE)
    utc = site_time.astimezone(UTC).strftime("%Y-%m-%dT%H:%M")
    meta = {
        "schema_version": 1,
        "project_id": "construction",
        "camera_id": "site-overview",
        "kind": "scheduled",
        "scheduled_at_utc": f"{utc}:00.000Z",
        "frame_received_at": f"{utc}:19.252Z",
        "camera_captured_at": None,
        "site_time_zone": "America/Chicago",
        "local_date": day.isoformat(),
        "source": "live_p2p",
        "retained": False,
        "width": 3840,
        "height": 2160,
        "quality_status": "ok",
        "battery_percent": 100,
        "every_minutes": 5,
    }
    return {**meta, **changes}


class SiteCase(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root)
        for name, value in (
            ("FRAMES", self.root / "frames"),
            ("DIGESTS", self.root / "state"),
        ):
            patch = mock.patch.object(frames, name, value)
            patch.start()
            self.addCleanup(patch.stop)
        (self.root / "frames").mkdir()

    def frame(self, hhmm: str, day: date = DAY, **changes) -> str:
        capture = (
            f"id-{day.isoformat()}-{hhmm.replace(':', '')}-{changes.get('kind', 's')}"
        )
        folder = self.root / "frames" / f"{day:%Y/%m/%d}" / capture
        folder.mkdir(parents=True)
        meta = live_meta(hhmm, day, **changes)
        (folder / "metadata.json").write_text(json.dumps(meta))
        (folder / "frame.jpg").write_bytes(b"jpeg")
        return capture

    def slots(self, first: str, last: str, every: int = 5) -> None:
        hour, minute = (int(part) for part in first.split(":"))
        end_hour, end_minute = (int(part) for part in last.split(":"))
        while (hour, minute) <= (end_hour, end_minute):
            self.frame(f"{hour:02d}:{minute:02d}")
            minute += every
            if minute >= 60:
                hour, minute = hour + 1, minute - 60

    def health(self, now: datetime = AT_1410, day: date = DAY) -> dict:
        return frames.health(day, HOURS, 5, ZONE, now)


class HealthTests(SiteCase):
    def test_a_complete_day_so_far_has_no_problems(self) -> None:
        self.slots("07:00", "14:05")
        result = self.health()
        self.assertEqual(result["scheduled"], 86)
        self.assertEqual(result["expected_by_now"], 86)
        self.assertEqual(result["missing"], 0)
        self.assertEqual(result["newest"]["time"], "14:05")
        self.assertEqual(result["battery_percent"], 100)
        self.assertEqual(result["problems"], [])

    def test_a_frame_still_on_its_way_is_not_missing(self) -> None:
        self.slots("07:00", "14:05")
        just_after_slot = datetime(2026, 11, 2, 20, 10, 30, tzinfo=UTC)
        self.assertEqual(self.health(just_after_slot)["missing"], 0)

    def test_a_hole_reports_the_gap_and_the_count(self) -> None:
        self.slots("07:00", "10:00")
        self.slots("10:30", "14:05")
        result = self.health()
        self.assertEqual(result["missing"], 5)
        self.assertEqual(
            result["gaps"], [{"from": "10:00", "to": "10:30", "minutes": 30}]
        )
        self.assertIn("5 of 86 scheduled frames missing", result["problems"])
        self.assertIn("gap 10:00 to 10:30, 30 minutes", result["problems"])

    def test_a_stale_newest_frame_during_capture_hours_comes_up(self) -> None:
        self.slots("07:00", "09:00")
        problems = self.health()["problems"]
        self.assertIn("newest frame is 310 minutes old", problems)

    def test_an_old_newest_frame_after_hours_is_not_stale(self) -> None:
        self.slots("07:00", "17:55")
        result = self.health(AFTER_HOURS)
        self.assertEqual(result["expected_by_now"], 132)
        self.assertEqual(result["problems"], [])

    def test_a_frame_arriving_late_is_not_a_gap(self) -> None:
        # Live 2026-11-02: the 14:45 slot's frame arrived at 14:46:05.
        self.slots("07:00", "14:40")
        self.frame("14:45", frame_received_at="2026-11-02T20:46:05.000Z")
        self.slots("14:50", "14:55")
        result = self.health(datetime(2026, 11, 2, 21, 0, tzinfo=UTC))
        self.assertEqual(result["gaps"], [])
        self.assertEqual(result["problems"], [])

    def test_frames_outside_capture_hours_count_for_nothing(self) -> None:
        # Live 2026-11-01: the camera's first day also ran overnight.
        self.frame("03:00")
        self.slots("07:00", "14:05")
        result = self.health()
        self.assertEqual(result["frames"], 87)
        self.assertEqual(result["scheduled"], 86)
        self.assertEqual(result["gaps"], [])
        self.assertEqual(result["problems"], [])

    def test_a_day_with_no_frames_is_a_problem_once_capture_started(self) -> None:
        self.frame("07:00", date(2026, 11, 1))
        result = self.health()
        self.assertEqual(result["frames"], 0)
        self.assertIsNone(result["newest"])
        self.assertEqual(result["problems"], ["no frames for this day"])

    def test_before_capture_hours_nothing_is_expected(self) -> None:
        self.frame("07:00", date(2026, 11, 1))
        before = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)
        result = self.health(before)
        self.assertEqual(result["expected_by_now"], 0)
        self.assertEqual(result["problems"], [])

    def test_degraded_and_retained_frames_are_problems_but_a_manual_one_is_not(
        self,
    ) -> None:
        self.slots("13:50", "14:05")
        self.frame("10:00", quality_status="degraded")
        self.frame("11:00", retained=True, source="retained_clip")
        self.frame("12:00", kind="manual")
        result = self.health()
        problems = " | ".join(result["problems"])
        self.assertIn("frame at 10:00: quality degraded", problems)
        self.assertIn("frame at 11:00: source retained_clip, retained", problems)
        self.assertNotIn("kind manual", problems)
        self.assertEqual(
            [row["time"] for row in result["odd"]], ["10:00", "11:00", "12:00"]
        )

    def test_low_battery_comes_from_the_newest_frame(self) -> None:
        self.frame("07:00", battery_percent=90)
        self.frame("14:05", battery_percent=12)
        self.assertIn("battery at 12%", self.health()["problems"])

    def test_an_unreadable_capture_is_counted_rather_than_crashing(self) -> None:
        self.frame("14:05")
        broken = self.root / "frames" / f"{DAY:%Y/%m/%d}" / "broken"
        broken.mkdir()
        (broken / "metadata.json").write_text("{not json")
        result = self.health()
        self.assertEqual(result["unreadable"], ["broken"])
        self.assertIn("1 capture folders unreadable", result["problems"])


class SelectionTests(SiteCase):
    def rendered(self, argv: list[str]) -> tuple[dict, str]:
        pages = []

        def fake_render(page, width, height):
            pages.append(page)
            return Path("/tmp/sheet.png")

        args = frames.parser().parse_args(argv)
        with mock.patch.object(frames, "render", fake_render):
            result = frames.sheet(args, ZONE, AT_1410)
        return result, pages[0]

    def test_hourly_picks_one_frame_per_hour_and_skips_an_hour_with_none(self) -> None:
        self.slots("07:00", "08:00")
        self.slots("11:00", "11:55")
        result, _ = self.rendered(["sheet", "--window", "07:00-11:00", "--step", "60"])
        self.assertEqual(
            [row["time"] for row in result["frames"]], ["07:00", "08:00", "11:00"]
        )

    def test_a_tile_shows_the_nearby_frame_labelled_with_its_real_time(self) -> None:
        self.slots("08:50", "08:55")
        result, page = self.rendered(
            ["sheet", "--window", "09:00-09:10", "--step", "60"]
        )
        self.assertEqual([row["time"] for row in result["frames"]], ["08:55"])
        self.assertIn("11-02 08:55", page)

    def test_at_picks_the_nearest_frame_of_the_requested_kind(self) -> None:
        self.frame("10:40")
        self.frame("10:42", kind="manual")
        result, page = self.rendered(["sheet", "--at", "2026-11-02T10:41"])
        self.assertEqual(result["frames"][0]["time"], "10:40")
        self.assertNotIn("manual", page)
        result, page = self.rendered(
            ["sheet", "--at", "2026-11-02T10:41", "--kind", "manual"]
        )
        self.assertEqual(result["frames"][0]["time"], "10:42")
        self.assertIn("11-02 10:42 manual", page)

    def test_at_compares_across_days(self) -> None:
        self.frame("10:40")
        self.frame("10:40", date(2026, 11, 1))
        result, _ = self.rendered(
            ["sheet", "--at", "2026-11-01T10:40", "--at", "2026-11-02T10:40"]
        )
        self.assertEqual(
            [row["date"] for row in result["frames"]], ["2026-11-01", "2026-11-02"]
        )

    def test_a_crop_scales_the_full_frame_and_offsets_it(self) -> None:
        self.frame("10:40")
        result, page = self.rendered(
            [
                "sheet",
                "--at",
                "2026-11-02T10:40",
                "--crop",
                "1000,500,800,400",
                "--tile",
                "400",
                "--cols",
                "1",
            ]
        )
        self.assertIn("width:400px;height:200px", page)
        self.assertIn("background-size:1920px 1080px", page)
        self.assertIn("background-position:-500px -250px", page)
        self.assertIn("frame.jpg", page)
        self.assertEqual((result["width"], result["height"]), (408, 208))

    def test_empty_selection_and_bad_arguments_refuse(self) -> None:
        self.frame("07:00")
        for argv in (
            ["sheet", "--window", "12:00-13:00", "--step", "5"],
            ["sheet", "--window", "07:00-08:00"],
            ["sheet", "--window", "bad", "--step", "5"],
            ["sheet", "--at", "2026-11-05T10:00"],
            ["sheet", "--at", "not-a-time"],
            ["sheet", "--at", "2026-11-02T07:00", "--crop", "1,2"],
            ["sheet", "--at", "2026-11-02T07:00", "--window", "07:00-08:00"],
        ):
            with self.subTest(argv=argv), self.assertRaises(frames.SiteError):
                self.rendered(argv)


class RenderTests(unittest.TestCase):
    def run_render(self, returncode: int, write: bool, stderr: str = "") -> Path:
        def fake_run(command, **kwargs):
            shot = next(arg for arg in command if arg.startswith("--screenshot="))
            if write:
                Path(shot.split("=", 1)[1]).write_bytes(b"png")
            return subprocess.CompletedProcess(command, returncode, "", stderr)

        with mock.patch.object(frames.subprocess, "run", fake_run):
            return frames.render("<html></html>", 100, 100)

    def test_a_successful_render_returns_the_png(self) -> None:
        output = self.run_render(0, True)
        self.addCleanup(shutil.rmtree, output.parent)
        self.assertEqual(output.read_bytes(), b"png")
        self.assertEqual(
            sorted(p.name for p in output.parent.iterdir()), ["sheet.html", "sheet.png"]
        )

    def test_the_browser_profile_is_removed_after_the_screenshot(self) -> None:
        profiles = []

        def fake_run(command, **kwargs):
            profile = next(arg for arg in command if arg.startswith("--user-data-dir="))
            profiles.append(Path(profile.split("=", 1)[1]))
            shot = next(arg for arg in command if arg.startswith("--screenshot="))
            Path(shot.split("=", 1)[1]).write_bytes(b"png")
            return subprocess.CompletedProcess(command, 0, "", "")

        with mock.patch.object(frames.subprocess, "run", fake_run):
            output = frames.render("<html></html>", 100, 100)
        self.addCleanup(shutil.rmtree, output.parent)
        self.assertFalse(profiles[0].exists())

    def test_a_chromium_failure_is_reported_with_its_error(self) -> None:
        with self.assertRaisesRegex(frames.SiteError, "exit 1.*no display"):
            self.run_render(1, False, "no display")

    def test_a_missing_png_is_a_failure_even_on_exit_zero(self) -> None:
        with self.assertRaises(frames.SiteError):
            self.run_render(0, False)

    def test_a_missing_chromium_is_a_failure(self) -> None:
        with (
            mock.patch.object(
                frames.subprocess, "run", side_effect=FileNotFoundError("chromium")
            ),
            self.assertRaises(frames.SiteError),
        ):
            frames.render("<html></html>", 100, 100)


class DigestTests(SiteCase):
    def save(self, value: dict, now: datetime = AFTER_HOURS) -> dict:
        return frames.save_digest(json.dumps(value), HOURS, 5, ZONE, now)

    def test_a_saved_digest_reads_back_private_with_its_health(self) -> None:
        self.slots("07:00", "17:55")
        lines = ["Пикап на площадке в 10:40"]
        self.save({"site_date": "2026-11-02", "lines": lines, "frames": ["abc"]})
        result = frames.read_digest(DAY)
        self.assertEqual(result["availability"], "available")
        self.assertEqual(result["lines"], lines)
        self.assertEqual(result["frames"], ["abc"])
        self.assertEqual(result["health"]["scheduled"], 132)
        mode = stat.S_IMODE(frames.digest_path(DAY).stat().st_mode)
        self.assertEqual(mode, 0o600)

    def test_a_missing_digest_is_unavailable_never_quiet(self) -> None:
        self.assertEqual(
            frames.read_digest(DAY),
            {
                "schema_version": 1,
                "availability": "unavailable",
                "site_date": "2026-11-02",
            },
        )

    def test_another_schema_is_unavailable(self) -> None:
        frames.DIGESTS.mkdir()
        frames.digest_path(DAY).write_text(
            json.dumps({"schema_version": 2, "lines": ["x"]})
        )
        self.assertEqual(frames.read_digest(DAY)["availability"], "unavailable")

    def test_a_damaged_digest_is_a_failure(self) -> None:
        frames.DIGESTS.mkdir()
        frames.digest_path(DAY).write_text("{")
        with self.assertRaisesRegex(frames.SiteError, "damaged"):
            frames.read_digest(DAY)

    def test_a_bad_digest_saves_nothing(self) -> None:
        for value in (
            {"site_date": "2026-11-02", "lines": [], "frames": []},
            {"site_date": "2026-11-02", "lines": ["  "], "frames": []},
            {"site_date": "soon", "lines": ["x"], "frames": []},
            {"site_date": "2026-11-02", "lines": ["x"]},
            {"site_date": "2026-11-02", "lines": ["x"], "frames": [1]},
            {"site_date": None, "lines": ["x"], "frames": []},
            {"site_date": 20261102, "lines": ["x"], "frames": []},
        ):
            with self.subTest(value=value), self.assertRaises(frames.SiteError):
                self.save(value)
        self.assertFalse(frames.digest_path(DAY).exists())

    def test_the_day_finishes_at_the_digest_cadence(self) -> None:
        cases = {
            datetime(2026, 11, 3, 0, 29, tzinfo=UTC): "2026-11-01",
            datetime(2026, 11, 3, 0, 30, tzinfo=UTC): "2026-11-02",
            datetime(2026, 11, 3, 12, 0, tzinfo=UTC): "2026-11-02",
        }
        for now, expected in cases.items():
            with self.subTest(now=now):
                self.assertEqual(frames.finished_day(ZONE, now).isoformat(), expected)

    def cli(self, argv: list[str], now: datetime = AFTER_HOURS) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with (
            mock.patch.object(frames, "utc_now", return_value=now),
            contextlib.redirect_stdout(out),
            contextlib.redirect_stderr(err),
        ):
            code = frames.main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_cli_digest_defaults_to_the_last_finished_day(self) -> None:
        self.frame("07:00")
        code, out, _ = self.cli(["digest"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["site_date"], "2026-11-02")

    def test_cli_failure_has_a_repair_on_stderr_and_nothing_on_stdout(self) -> None:
        code, out, err = self.cli(["digest"])
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn("construction-site mount", err)

    def test_cli_save_reads_its_digest_from_stdin(self) -> None:
        self.frame("07:00")
        stdin = json.dumps({"site_date": "2026-11-02", "lines": ["тихо"], "frames": []})
        with mock.patch.object(sys, "stdin", io.StringIO(stdin)):
            code, out, _ = self.cli(
                ["save-digest", "--hours", "07:00-18:00", "--every", "5"]
            )
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["site_date"], "2026-11-02")


class PrecheckTests(SiteCase):
    def precheck(self) -> tuple[int, str, str]:
        spec = importlib.util.spec_from_file_location(
            "digest_precheck", SCRIPTS / "digest-precheck.py"
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        out, err = io.StringIO(), io.StringIO()
        with (
            mock.patch.object(frames, "utc_now", return_value=AFTER_HOURS),
            contextlib.redirect_stdout(out),
            contextlib.redirect_stderr(err),
        ):
            code = module.main()
        return code, out.getvalue(), err.getvalue()

    def test_wakes_until_the_day_has_a_digest(self) -> None:
        self.frame("07:00")
        code, out, _ = self.precheck()
        self.assertEqual(code, 0)
        self.assertEqual(
            json.loads(out.splitlines()[-1]),
            {"wake_agent": True, "data": {"site_date": "2026-11-02"}},
        )
        frames.DIGESTS.mkdir()
        frames.digest_path(DAY).write_text("{}")
        self.assertFalse(json.loads(self.precheck()[1])["wake_agent"])

    def test_a_missing_mount_fails_visibly(self) -> None:
        code, out, err = self.precheck()
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn("eufy-time-lapse", err)
