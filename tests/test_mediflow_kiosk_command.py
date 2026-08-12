import importlib.machinery
import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path


COMMAND_PATH = Path(__file__).resolve().parents[1] / "scripts" / "mediflow-kiosk"
LOADER = importlib.machinery.SourceFileLoader("mediflow_kiosk_command", str(COMMAND_PATH))
SPEC = importlib.util.spec_from_loader(LOADER.name, LOADER)
mediflow_kiosk = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = mediflow_kiosk
LOADER.exec_module(mediflow_kiosk)


class MediflowKioskCommandTest(unittest.TestCase):
    def test_parse_action_accepts_only_one_known_action(self):
        self.assertEqual(
            mediflow_kiosk.parse_action(["mediflow-kiosk", "status"]),
            "status",
        )
        for argv in (
            ["mediflow-kiosk"],
            ["mediflow-kiosk", "status", "extra"],
            ["mediflow-kiosk", "start;id"],
            ["mediflow-kiosk", "unknown"],
        ):
            with self.subTest(argv=argv):
                with self.assertRaises(mediflow_kiosk.UsageError):
                    mediflow_kiosk.parse_action(argv)

    def test_tail_lines_returns_only_requested_suffix(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "service.log"
            path.write_text("one\ntwo\nthree\n", encoding="utf-8")
            self.assertEqual(mediflow_kiosk.tail_lines(path, 2), ["two\n", "three\n"])

    @unittest.skipUnless(Path("/proc/self/stat").exists(), "requires Linux /proc")
    def test_process_record_detects_start_time_tampering(self):
        snapshot = mediflow_kiosk.read_process_snapshot(os.getpid())
        self.assertIsNotNone(snapshot)
        spec = mediflow_kiosk.ServiceSpec(
            key="test",
            label="test",
            launch_argv=snapshot.argv,
            executable=snapshot.executable,
            cwd=snapshot.cwd,
            port=0,
            health_url="http://127.0.0.1/",
        )
        record = mediflow_kiosk.build_process_record(spec, os.getpid())
        valid, _, _ = mediflow_kiosk.validate_record(spec, record)
        self.assertTrue(valid)

        record["start_ticks"] = int(record["start_ticks"]) + 1
        valid, reason, _ = mediflow_kiosk.validate_record(spec, record)
        self.assertFalse(valid)
        self.assertEqual(reason, "PID was reused")


if __name__ == "__main__":
    unittest.main()
