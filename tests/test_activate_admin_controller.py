"""No-device tests for the one-window controller activation wrapper."""
from __future__ import annotations

import json
from contextlib import ExitStack
import types
import unittest
from unittest import mock

from scripts import activate_admin_controller as activation


class ControllerActivationTests(unittest.TestCase):
    def _mock_window(self, stack, *, gates, starts):
        record = {"version": 1, "pid": activation.EXPECTED_PID, "uid": 1000,
                  "executable": activation.EXECUTABLE, "argv": list(activation.ARGV),
                  "cwd": str(activation.RELEASE), "start_ticks": activation.EXPECTED_TICKS,
                  "boot_id": "boot"}
        stack.enter_context(mock.patch.object(activation.os, "geteuid", return_value=1000))
        stack.enter_context(mock.patch.object(activation.Path, "cwd", return_value=activation.RELEASE))
        stack.enter_context(mock.patch.object(activation.subprocess, "run", side_effect=[
            types.SimpleNamespace(stdout=activation.RELEASE_SHA + "\n"),
            types.SimpleNamespace(stdout="")]))
        stack.enter_context(mock.patch.object(activation, "open_lifecycle_lock", return_value=object()))
        stack.enter_context(mock.patch.object(activation, "acquire_lifecycle_lock"))
        stack.enter_context(mock.patch.object(activation, "release_lifecycle_lock"))
        stack.enter_context(mock.patch.object(activation, "private_bytes", side_effect=lambda path: (
            json.dumps(record).encode() if path == activation.IDENTITY else
            b"AI_CONTROL_DRAFTS_ENABLED=0\nAI_CONTROL_MUTATIONS_ENABLED=0\n")))
        stack.enter_context(mock.patch.object(activation, "read_process_snapshot",
                                      return_value=types.SimpleNamespace(boot_id="boot")))
        stack.enter_context(mock.patch.object(activation.Path, "exists", return_value=False))
        stack.enter_context(mock.patch.object(activation, "listeners", return_value=set()))
        stack.enter_context(mock.patch.object(activation, "gates", side_effect=gates))
        write = stack.enter_context(mock.patch.object(activation, "atomic_private_write"))
        stop = stack.enter_context(mock.patch.object(activation, "stop_exact"))
        start = stack.enter_context(mock.patch.object(activation, "start_controller", side_effect=starts))
        return write, stop, start

    def test_enabled_config_changes_only_two_flags(self):
        old = b"NODE=jetson-b\nAI_CONTROL_DRAFTS_ENABLED=0\nAI_CONTROL_MUTATIONS_ENABLED=0\n"
        new = activation.enabled_config(old)
        self.assertEqual(new, old.replace(b"ENABLED=0", b"ENABLED=1"))

    def test_enabled_config_rejects_missing_or_active_flags(self):
        for raw in (b"AI_CONTROL_DRAFTS_ENABLED=0\n",
                    b"AI_CONTROL_DRAFTS_ENABLED=1\nAI_CONTROL_MUTATIONS_ENABLED=0\n"):
            with self.subTest(raw=raw), self.assertRaises(activation.ActivationError):
                activation.enabled_config(raw)

    def test_exact_process_requires_full_owner_identity(self):
        snap = types.SimpleNamespace(pid=9, uid=1000, start_ticks=77,
                                     executable=activation.EXECUTABLE,
                                     argv=activation.ARGV, cwd=str(activation.RELEASE))
        with mock.patch.object(activation.os, "geteuid", return_value=1000), \
             mock.patch.object(activation, "read_process_snapshot", return_value=snap):
            self.assertTrue(activation.exact_process(9, 77))
            self.assertFalse(activation.exact_process(9, 78))
            snap.cwd = "/unexpected"
            self.assertFalse(activation.exact_process(9, 77))

    def test_check_only_cannot_stop_or_write(self):
        record = {"version": 1, "pid": activation.EXPECTED_PID, "uid": 1000,
                  "executable": activation.EXECUTABLE, "argv": list(activation.ARGV),
                  "cwd": str(activation.RELEASE), "start_ticks": activation.EXPECTED_TICKS,
                  "boot_id": "boot"}
        snap = types.SimpleNamespace(boot_id="boot")
        process = types.SimpleNamespace(stdout=activation.RELEASE_SHA + "\n")
        clean = types.SimpleNamespace(stdout="")
        with mock.patch.object(activation.os, "geteuid", return_value=1000), \
             mock.patch.object(activation.Path, "cwd", return_value=activation.RELEASE), \
             mock.patch.object(activation.subprocess, "run", side_effect=[process, clean]), \
             mock.patch.object(activation, "open_lifecycle_lock", return_value=object()), \
             mock.patch.object(activation, "acquire_lifecycle_lock"), \
             mock.patch.object(activation, "release_lifecycle_lock"), \
             mock.patch.object(activation, "private_bytes", side_effect=lambda path: (
                 json.dumps(record).encode() if path == activation.IDENTITY else
                 b"AI_CONTROL_DRAFTS_ENABLED=0\nAI_CONTROL_MUTATIONS_ENABLED=0\n")), \
             mock.patch.object(activation, "read_process_snapshot", return_value=snap), \
             mock.patch.object(activation, "exact_process", return_value=True), \
             mock.patch.object(activation, "gates", return_value=({}, "digest")), \
             mock.patch.object(activation.BACKUP.__class__, "exists", return_value=False), \
             mock.patch.object(activation, "atomic_private_write") as write, \
             mock.patch.object(activation, "stop_exact") as stop, \
             mock.patch.object(activation, "start_controller") as start:
            activation.run(check_only=True)
            write.assert_not_called()
            stop.assert_not_called()
            start.assert_not_called()

    def test_failed_enabled_bootstrap_restores_read_only_owner(self):
        with ExitStack() as stack:
            write, stop, start = self._mock_window(
                stack, gates=[({}, "digest"), activation.ActivationError("arming_failed"), ({}, "digest")],
                starts=[(123, 456), (124, 457)])
            stack.enter_context(mock.patch.object(activation, "exact_process", side_effect=[True, False]))
            close = stack.enter_context(mock.patch.object(
                activation, "close_admission_after_failed_rollback"))
            with self.assertRaisesRegex(activation.ActivationError, "activation_failed_rolled_back"):
                activation.run(check_only=False)
            self.assertEqual(start.call_count, 2)
            self.assertEqual(stop.call_count, 2)
            self.assertEqual(write.call_count, 3)
            self.assertEqual(write.call_args.args[0], activation.IDENTITY)
            close.assert_not_called()

    def test_failed_read_only_rollback_closes_admission(self):
        with ExitStack() as stack:
            self._mock_window(
                stack, gates=[({}, "digest"), activation.ActivationError("arming_failed")],
                starts=[(123, 456), activation.ActivationError("rollback_start_failed")])
            stack.enter_context(mock.patch.object(activation, "exact_process", side_effect=[True, False]))
            close = stack.enter_context(mock.patch.object(
                activation, "close_admission_after_failed_rollback"))
            with self.assertRaisesRegex(activation.ActivationError, "rollback_failed_admission_closed"):
                activation.run(check_only=False)
            close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
