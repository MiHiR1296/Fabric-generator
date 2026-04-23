from __future__ import annotations

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app.blender_session as blender_session  # noqa: E402


class FakeProcess:
    def __init__(self, pid: int = 4242) -> None:
        self.pid = pid
        self._returncode: int | None = None
        self.terminated = False
        self.killed = False

    def poll(self) -> int | None:
        return self._returncode

    def terminate(self) -> None:
        self.terminated = True
        self._returncode = 0

    def kill(self) -> None:
        self.killed = True
        self._returncode = -9

    def wait(self, timeout: float | None = None) -> int:
        return 0 if self._returncode is None else self._returncode


class BlenderSessionTests(unittest.TestCase):
    def tearDown(self) -> None:
        with blender_session._LOCK:
            if blender_session._IDLE_TIMER is not None:
                blender_session._IDLE_TIMER.cancel()
                blender_session._IDLE_TIMER = None
            blender_session._PROCESS = None
            blender_session._BUSY_COUNT = 0
            blender_session._STATE = blender_session.BlenderSessionState()

    def test_begin_command_attaches_to_existing_socket(self) -> None:
        with patch.dict("os.environ", {"BLENDER_SESSION_MODE": "managed"}, clear=False), patch(
            "app.blender_session._socket_available",
            return_value=True,
        ):
            blender_session.begin_blender_command("health-check")
            blender_session.finish_blender_command()
            snapshot = blender_session.get_blender_session_snapshot()

        self.assertTrue(snapshot["socketAvailable"])
        self.assertEqual(snapshot["status"], "running")
        self.assertFalse(snapshot["launchedByManager"])

    def test_begin_command_launches_managed_session_when_socket_is_missing(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            fake_binary = root / "blender-bin"
            fake_blend = root / "preview.blend"
            fake_binary.write_text("", encoding="utf-8")
            fake_blend.write_text("", encoding="utf-8")
            fake_process = FakeProcess(pid=6001)

            with patch.dict(
                "os.environ",
                {
                    "BLENDER_SESSION_MODE": "managed",
                    "BLENDER_BINARY_PATH": str(fake_binary),
                    "WEAVE_BLEND_FILE": str(fake_blend),
                    "BLENDER_IDLE_TIMEOUT_SECONDS": "0",
                },
                clear=False,
            ), patch(
                "app.blender_session.subprocess.Popen",
                return_value=fake_process,
            ) as popen_mock, patch(
                "app.blender_session._socket_available",
                side_effect=[False, False, True, True],
            ):
                blender_session.begin_blender_command("live-preview")
                blender_session.finish_blender_command()
                snapshot = blender_session.get_blender_session_snapshot()

        self.assertEqual(snapshot["status"], "running")
        self.assertTrue(snapshot["launchedByManager"])
        self.assertEqual(snapshot["pid"], 6001)
        self.assertEqual(snapshot["mode"], "managed")
        launch_command = popen_mock.call_args.args[0]
        self.assertIn("--python", launch_command)
        self.assertTrue(str(snapshot["startupScript"]).endswith("blender_session_startup.py"))
        self.assertEqual(snapshot["launchPrefix"], [])

    def test_begin_command_uses_launch_prefix_for_terminal_only_hosts(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            fake_binary = root / "blender-bin"
            fake_blend = root / "preview.blend"
            fake_binary.write_text("", encoding="utf-8")
            fake_blend.write_text("", encoding="utf-8")
            fake_process = FakeProcess(pid=6002)

            with patch.dict(
                "os.environ",
                {
                    "BLENDER_SESSION_MODE": "managed",
                    "BLENDER_BINARY_PATH": str(fake_binary),
                    "WEAVE_BLEND_FILE": str(fake_blend),
                    "BLENDER_IDLE_TIMEOUT_SECONDS": "0",
                    "BLENDER_LAUNCH_PREFIX": 'xvfb-run -a -s "-screen 0 1920x1080x24"',
                },
                clear=False,
            ), patch(
                "app.blender_session.subprocess.Popen",
                return_value=fake_process,
            ) as popen_mock, patch(
                "app.blender_session._socket_available",
                side_effect=[False, False, True, True],
            ):
                blender_session.begin_blender_command("server-preview")
                blender_session.finish_blender_command()
                snapshot = blender_session.get_blender_session_snapshot()

        launch_command = popen_mock.call_args.args[0]
        self.assertEqual(launch_command[:4], ["xvfb-run", "-a", "-s", "-screen 0 1920x1080x24"])
        self.assertEqual(snapshot["launchPrefix"], ["xvfb-run", "-a", "-s", "-screen 0 1920x1080x24"])

    def test_stop_session_terminates_managed_process(self) -> None:
        fake_process = FakeProcess(pid=7123)

        with patch.dict(
            "os.environ",
            {
                "BLENDER_SESSION_MODE": "managed",
                "BLENDER_IDLE_TIMEOUT_SECONDS": "0",
            },
            clear=False,
        ), patch(
            "app.blender_session._socket_available",
            return_value=False,
        ):
            with blender_session._LOCK:
                blender_session._PROCESS = fake_process
                blender_session._STATE = blender_session.BlenderSessionState(
                    status="running",
                    message="Managed Blender session is ready.",
                    pid=fake_process.pid,
                    launched_by_manager=True,
                    started_at="2026-04-23T00:00:00Z",
                    last_used_at="2026-04-23T00:01:00Z",
                )
            snapshot = blender_session.stop_blender_session("Stopped for test.")

        self.assertTrue(fake_process.terminated)
        self.assertEqual(snapshot["status"], "stopped")
        self.assertFalse(snapshot["launchedByManager"])


if __name__ == "__main__":
    unittest.main()
