import signal
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import local_llm_service as service


class LocalLlmServiceTest(unittest.TestCase):
    def make_spec(self, root: Path) -> service.ServiceSpec:
        server = root / "llama-server"
        server.write_text("fixture", encoding="utf-8")
        launcher = root / "run_local_llm_candidate.sh"
        launcher.write_text("#!/bin/bash\n", encoding="utf-8")
        return service.ServiceSpec(
            project_root=root,
            launcher=launcher,
            server=server,
            control_dir=root,
            pid_path=root / "pid.json",
            log_path=root / "service.log",
            lock_path=root / "service.lock",
            health_url="http://127.0.0.1:8080/health",
        )

    def snapshot(self, spec: service.ServiceSpec, *, pid: int = 42, ticks: int = 99):
        return service.ProcessSnapshot(
            pid=pid,
            uid=service.os.getuid(),
            executable=str(spec.server),
            argv=(str(spec.server), "--port", "8080"),
            cwd=str(spec.project_root),
            state="S",
            start_ticks=ticks,
            boot_id="fixture-boot",
        )

    def record(self, snapshot: service.ProcessSnapshot):
        return {
            "version": 1,
            "pid": snapshot.pid,
            "uid": snapshot.uid,
            "executable": snapshot.executable,
            "argv": list(snapshot.argv),
            "cwd": snapshot.cwd,
            "start_ticks": snapshot.start_ticks,
            "boot_id": snapshot.boot_id,
        }

    def test_rejects_unknown_action(self):
        with self.assertRaises(service.UsageError):
            service.parse_action(["manager", "start;id"])

    def test_pid_reuse_is_not_treated_as_managed_process(self):
        with tempfile.TemporaryDirectory() as directory:
            spec = self.make_spec(Path(directory))
            original = self.snapshot(spec, ticks=99)
            reused = self.snapshot(spec, ticks=100)
            with mock.patch.object(service, "read_boot_id", return_value="fixture-boot"), mock.patch.object(
                service, "read_process_snapshot", return_value=reused
            ):
                valid, reason, live = service.validate_record(spec, self.record(original))
            self.assertFalse(valid)
            self.assertEqual(reason, "PID was reused")
            self.assertEqual(live, reused)

    def test_stop_refuses_identity_mismatch_without_signalling(self):
        with tempfile.TemporaryDirectory() as directory:
            spec = self.make_spec(Path(directory))
            expected = self.snapshot(spec)
            wrong = service.dataclasses.replace(expected, executable="/other/project/llama-server")
            with mock.patch.object(service, "read_boot_id", return_value="fixture-boot"), mock.patch.object(
                service, "read_process_snapshot", return_value=wrong
            ), mock.patch.object(service.os, "kill") as kill:
                with self.assertRaisesRegex(service.ManagerError, "refusing to stop"):
                    service.terminate_record(spec, self.record(expected))
            kill.assert_not_called()

    def test_stop_signals_only_the_validated_recorded_pid(self):
        with tempfile.TemporaryDirectory() as directory:
            spec = self.make_spec(Path(directory))
            expected = self.snapshot(spec, pid=4242)
            snapshots = [expected, None]
            with mock.patch.object(service, "read_boot_id", return_value="fixture-boot"), mock.patch.object(
                service, "read_process_snapshot", side_effect=snapshots
            ), mock.patch.object(service.os, "kill") as kill:
                service.terminate_record(spec, self.record(expected))
            kill.assert_called_once_with(4242, signal.SIGTERM)

    def test_start_refuses_unmanaged_port_without_spawning(self):
        with tempfile.TemporaryDirectory() as directory:
            spec = self.make_spec(Path(directory))
            with mock.patch.object(
                service, "inspect_service", return_value=("unmanaged-port", None, None)
            ), mock.patch.object(service.subprocess, "Popen") as popen:
                with self.assertRaisesRegex(service.ManagerError, "unmanaged-port"):
                    service.start_service(spec)
            popen.assert_not_called()

    def test_source_contains_no_autostart_download_or_broad_kill(self):
        source = Path(service.__file__).read_text(encoding="utf-8")
        for forbidden in ("systemctl", "crontab", "@reboot", "pkill", "killall", "git clone"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
