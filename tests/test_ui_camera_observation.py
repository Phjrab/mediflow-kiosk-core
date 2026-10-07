"""Test additive camera freshness telemetry without importing model/camera startup."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest


class CameraObservationTest(unittest.TestCase):
    def observe(self, frame, timestamp, now=10):
        tree = ast.parse(Path('eye_server.py').read_text())
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'camera_observation')
        namespace = {'current_frame': frame, 'current_frame_observed_at': timestamp,
                     'last_camera_error': None,
                     'time': SimpleNamespace(monotonic=lambda: now)}
        exec(compile(ast.Module(body=[function], type_ignores=[]), 'eye_server.py', 'exec'), namespace)
        return namespace['camera_observation']()

    def test_missing_unknown_age_does_not_claim_ready(self):
        self.assertEqual(self.observe(None, None), {'camera_state': 'missing', 'frame_age_ms': None})

    def test_fresh_and_stale_frames(self):
        self.assertEqual(self.observe(object(), 9.5), {'camera_state': 'streaming', 'frame_age_ms': 500})
        self.assertEqual(self.observe(object(), 5), {'camera_state': 'stale', 'frame_age_ms': 5000})


if __name__ == '__main__':
    unittest.main()
