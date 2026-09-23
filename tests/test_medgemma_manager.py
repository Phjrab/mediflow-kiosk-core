import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from scripts import local_llm_service
from scripts import medgemma_service as service
from utils.lifecycle_lock import acquire_lifecycle_lock, open_lifecycle_lock, release_lifecycle_lock


class MedGemmaManagerTest(unittest.TestCase):
    def make_spec(self, root: Path) -> service.ServiceSpec:
        executable = str(Path(sys.executable).resolve())
        key = root / "vlm.key"
        key.write_text("fixture-token\n", encoding="utf-8")
        key.chmod(0o600)
        return service.ServiceSpec(
            project_root=root,
            executable=executable,
            argv=(executable, "-m", "services.medgemma.app"),
            control_dir=root,
            pid_path=root / "medgemma.pid.json",
            log_path=root / "medgemma.log",
            lock_path=root / "medgemma.lock",
            key_file=key,
            ready_url="http://127.0.0.1:18081/readyz",
        )

    def snapshot(self, spec, *, pid=4242, ticks=100):
        return local_llm_service.ProcessSnapshot(
            pid, os.getuid(), spec.executable, spec.argv, str(spec.project_root),
            "S", ticks, "fixture-boot",
        )

    @staticmethod
    def record(snapshot):
        return {
            "version": 1, "pid": snapshot.pid, "uid": snapshot.uid,
            "executable": snapshot.executable, "argv": list(snapshot.argv),
            "cwd": snapshot.cwd, "start_ticks": snapshot.start_ticks,
            "boot_id": snapshot.boot_id,
        }

    def test_direct_cli_imports_repo_and_rejects_unknown_action(self):
        result = subprocess.run(
            [sys.executable, str(Path(service.__file__)), "invalid"],
            cwd=Path(service.__file__).resolve().parents[1],
            capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("usage:", result.stderr)
        self.assertNotIn("ModuleNotFoundError", result.stderr)

    def test_pid_reuse_and_argv_drift_are_never_owned(self):
        with tempfile.TemporaryDirectory() as directory:
            spec = self.make_spec(Path(directory))
            record = self.record(self.snapshot(spec))
            reused = self.snapshot(spec, ticks=101)
            with mock.patch.object(local_llm_service, "read_boot_id", return_value="fixture-boot"), \
                    mock.patch.object(local_llm_service, "read_process_snapshot", return_value=reused):
                valid, reason, _snapshot = service.validate_record(spec, record)
            self.assertFalse(valid)
            self.assertEqual(reason, "live process identity mismatch")

    def test_stop_signals_only_exact_recorded_pid(self):
        with tempfile.TemporaryDirectory() as directory:
            spec = self.make_spec(Path(directory))
            live = self.snapshot(spec)
            snapshots = [live, None]
            with mock.patch.object(local_llm_service, "read_boot_id", return_value="fixture-boot"), \
                    mock.patch.object(local_llm_service, "read_process_snapshot", side_effect=snapshots), \
                    mock.patch.object(service.os, "kill") as kill:
                service.terminate_record(spec, self.record(live))
            kill.assert_called_once_with(4242, signal.SIGTERM)

    def test_owned_stop_waits_for_loopback_port_release(self):
        with tempfile.TemporaryDirectory() as directory:
            spec = self.make_spec(Path(directory))
            record = {'pid': 4242}
            with mock.patch.object(local_llm_service, 'load_record', return_value=record), \
                    mock.patch.object(service, 'terminate_record') as terminate, \
                    mock.patch.object(local_llm_service, 'port_is_open', side_effect=[True, False, False]), \
                    mock.patch.object(service.time, 'sleep') as sleep:
                service.stop_owned(spec, 4242)
            terminate.assert_called_once_with(spec, record)
            sleep.assert_called_once_with(0.05)

    def test_owned_stop_rejects_port_that_remains_open(self):
        with tempfile.TemporaryDirectory() as directory:
            spec = self.make_spec(Path(directory))
            record = {'pid': 4242}
            ticks = iter((0.0, 0.0, 6.0))
            with mock.patch.object(local_llm_service, 'load_record', return_value=record), \
                    mock.patch.object(service, 'terminate_record'), \
                    mock.patch.object(local_llm_service, 'port_is_open', return_value=True), \
                    mock.patch.object(service.time, 'monotonic', side_effect=lambda: next(ticks)), \
                    mock.patch.object(service.time, 'sleep'):
                with self.assertRaisesRegex(service.ManagerError, 'still in use'):
                    service.stop_owned(spec, 4242)

    def test_start_refuses_unmanaged_loopback_port(self):
        with tempfile.TemporaryDirectory() as directory:
            spec = self.make_spec(Path(directory))
            with mock.patch.object(service, "inspect_service", return_value=("unmanaged-port", None, None)), \
                    mock.patch.object(service.subprocess, "Popen") as popen:
                with self.assertRaisesRegex(service.ManagerError, "unmanaged-port"):
                    service.start_service(spec, env={"MEDGEMMA_API_KEY_FILE": str(spec.key_file)})
            popen.assert_not_called()

    def test_shared_lock_blocks_direct_cli_action(self):
        with tempfile.TemporaryDirectory() as directory:
            spec = self.make_spec(Path(directory))
            shared = Path(directory) / "device.lock"
            held = open_lifecycle_lock(shared)
            acquire_lifecycle_lock(held)
            try:
                with self.assertRaisesRegex(service.ManagerError, "another device lifecycle"):
                    service.run_locked("status", spec, env={"AI_DEVICE_LIFECYCLE_LOCK": str(shared)})
            finally:
                release_lifecycle_lock(held)

    def test_source_has_no_autostart_download_or_broad_kill(self):
        source = Path(service.__file__).read_text(encoding="utf-8")
        for forbidden in ("systemctl", "crontab", "@reboot", "pkill", "killall", "git clone"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
