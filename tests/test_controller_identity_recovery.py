"""Synthetic fail-closed tests for the one-window controller PID repair."""
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import recover_controller_identity as recovery


class ControllerIdentityRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.current = SimpleNamespace(
            pid=recovery.LIVE_PID, uid=os.geteuid(),
            executable=recovery.EXECUTABLE, argv=recovery.ARGV,
            cwd=str(recovery.RELEASE), start_ticks=recovery.LIVE_TICKS,
            boot_id="test-boot-id",
        )
        self.record = {
            "version": 1, "pid": recovery.OLD_PID, "uid": os.geteuid(),
            "executable": recovery.EXECUTABLE, "argv": list(recovery.ARGV),
            "cwd": str(recovery.RELEASE), "start_ticks": recovery.OLD_TICKS,
            "boot_id": self.current.boot_id,
        }

    def test_stale_absent_pid_and_exact_live_identity_pass(self):
        recovery.validate_recovery_candidates(self.record, None, self.current)

    def test_stale_pid_reuse_fails_closed(self):
        with self.assertRaisesRegex(recovery.RecoveryError, "stale_pid_reused"):
            recovery.validate_recovery_candidates(self.record, self.current, self.current)

    def test_live_pid_reuse_fails_closed(self):
        reused = SimpleNamespace(**{**vars(self.current), "start_ticks": 99})
        with self.assertRaisesRegex(recovery.RecoveryError, "live_identity_drift"):
            recovery.validate_recovery_candidates(self.record, None, reused)

    def test_boot_id_drift_fails_closed(self):
        changed = {**self.record, "boot_id": "another-boot"}
        with self.assertRaisesRegex(recovery.RecoveryError, "stale_record_drift"):
            recovery.validate_recovery_candidates(changed, None, self.current)

    def test_argv_or_cwd_drift_fails_closed(self):
        for name, value in (("argv", ("python3", "-m", "other")), ("cwd", "/tmp")):
            with self.subTest(name=name):
                changed = SimpleNamespace(**{**vars(self.current), name: value})
                with self.assertRaisesRegex(recovery.RecoveryError, "live_identity_drift"):
                    recovery.validate_recovery_candidates(self.record, None, changed)

    def test_atomic_replacement_interrupted_keeps_original(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "controller.pid"
            path.write_bytes(b"old identity\n")
            with patch.object(recovery.os, "replace", side_effect=OSError("interrupted")):
                with self.assertRaises(OSError):
                    recovery.atomic_private_write(path, b"new identity\n", replace=True)
            self.assertEqual(path.read_bytes(), b"old identity\n")
            self.assertEqual(list(path.parent.glob(".controller.pid.recovery-*")), [])

    def test_atomic_backup_does_not_overwrite_prior_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "controller.pid.before-recovery"
            path.write_bytes(b"preserved\n")
            with self.assertRaises(FileExistsError):
                recovery.atomic_private_write(path, b"replacement\n", replace=False)
            self.assertEqual(path.read_bytes(), b"preserved\n")

    def test_matching_new_identity_requires_same_boot_and_start(self):
        new = {**self.record, "pid": recovery.LIVE_PID,
               "start_ticks": recovery.LIVE_TICKS}
        self.assertTrue(recovery.identity_matches(
            new, self.current, expected_pid=recovery.LIVE_PID,
            expected_ticks=recovery.LIVE_TICKS,
        ))
        self.assertFalse(recovery.identity_matches(
            {**new, "boot_id": "changed"}, self.current,
            expected_pid=recovery.LIVE_PID, expected_ticks=recovery.LIVE_TICKS,
        ))


if __name__ == "__main__":
    unittest.main()
