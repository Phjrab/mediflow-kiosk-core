import importlib.machinery
import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path


COMMAND_PATH = Path(__file__).resolve().parents[1] / "scripts" / "mediflow"
LOADER = importlib.machinery.SourceFileLoader("mediflow_command", str(COMMAND_PATH))
SPEC = importlib.util.spec_from_loader(LOADER.name, LOADER)
mediflow = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = mediflow
LOADER.exec_module(mediflow)


class MediflowCommandTest(unittest.TestCase):
    def test_parse_action_accepts_only_one_known_action(self):
        self.assertEqual(mediflow.parse_action(["mediflow", "status"]), "status")
        for argv in (
            ["mediflow"],
            ["mediflow", "status", "extra"],
            ["mediflow", "start;id"],
            ["mediflow", "unknown"],
        ):
            with self.subTest(argv=argv):
                with self.assertRaises(mediflow.UsageError):
                    mediflow.parse_action(argv)

    def test_tail_lines_returns_only_requested_suffix(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "service.log"
            path.write_text("one\ntwo\nthree\n", encoding="utf-8")
            self.assertEqual(mediflow.tail_lines(path, 2), ["two\n", "three\n"])

    @unittest.skipUnless(Path("/proc/self/stat").exists(), "requires Linux /proc")
    def test_process_record_detects_start_time_tampering(self):
        snapshot = mediflow.read_process_snapshot(os.getpid())
        self.assertIsNotNone(snapshot)
        spec = mediflow.ServiceSpec(
            key="test",
            label="test",
            launch_argv=snapshot.argv,
            executable=snapshot.executable,
            cwd=snapshot.cwd,
            port=0,
            health_url="http://127.0.0.1/",
        )
        record = mediflow.build_process_record(spec, os.getpid())
        valid, _, _ = mediflow.validate_record(spec, record)
        self.assertTrue(valid)

        record["start_ticks"] = int(record["start_ticks"]) + 1
        valid, reason, _ = mediflow.validate_record(spec, record)
        self.assertFalse(valid)
        self.assertEqual(reason, "PID was reused")


if __name__ == "__main__":
    unittest.main()
