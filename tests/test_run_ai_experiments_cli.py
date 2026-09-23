import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import run_ai_experiments


class RunAIExperimentsCliTest(unittest.TestCase):
    def test_explicit_env_works_without_dotenv_and_uses_isolated_store(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store_path = root / 'research'
            (root / '.env').write_text(
                'EXPERIMENT_DATA_DIR=/should/not/be/used\n', encoding='utf-8'
            )
            output = io.StringIO()
            with (
                mock.patch.object(run_ai_experiments, 'PROJECT_ROOT', root),
                mock.patch.object(sys, 'argv', ['run_ai_experiments.py', '--explicit-env', 'init']),
                mock.patch.dict(sys.modules, {'dotenv': None}),
                mock.patch.dict(os.environ, {'EXPERIMENT_DATA_DIR': str(store_path)}),
                contextlib.redirect_stdout(output),
            ):
                self.assertEqual(run_ai_experiments.main(), 0)
            self.assertEqual(
                json.loads(output.getvalue())['db'],
                str((store_path / 'experiments.db').resolve()),
            )
            self.assertTrue((store_path / 'experiments.db').is_file())

    def test_default_mode_fails_closed_without_dotenv(self):
        with tempfile.TemporaryDirectory() as directory:
            store_path = Path(directory) / 'research'
            error = io.StringIO()
            with (
                mock.patch.object(sys, 'argv', ['run_ai_experiments.py', 'init']),
                mock.patch.dict(sys.modules, {'dotenv': None}),
                mock.patch.dict(os.environ, {'EXPERIMENT_DATA_DIR': str(store_path)}),
                contextlib.redirect_stderr(error),
            ):
                self.assertEqual(run_ai_experiments.main(), 1)
            self.assertEqual(json.loads(error.getvalue()), {
                'status': 'error', 'error_code': 'missing_dotenv',
            })
            self.assertFalse(store_path.exists())

    def test_explicit_env_worker_once_checks_empty_e2_queue_without_dotenv(self):
        with tempfile.TemporaryDirectory() as directory:
            output = io.StringIO()
            env = {
                'EXPERIMENT_DATA_DIR': str(Path(directory) / 'research'),
                'AI_EXPERIMENTS_ENABLED': '1',
                'VLM_ENABLED': '1',
                'SURVEY_VLM_EXPERIMENTS_ENABLED': '1',
                'AI_EXPERIMENT_MODE': 'shadow',
                'AI_DEPLOYMENT_PROFILE': 'vlm_only',
            }
            with (
                mock.patch.object(
                    sys, 'argv',
                    ['run_ai_experiments.py', '--explicit-env', 'worker', '--once'],
                ),
                mock.patch.dict(sys.modules, {'dotenv': None}),
                mock.patch.dict(os.environ, env),
                contextlib.redirect_stdout(output),
            ):
                self.assertEqual(run_ai_experiments.main(), 0)
            self.assertEqual(json.loads(output.getvalue()), {
                'status': 'ok', 'processed': False,
            })


if __name__ == '__main__':
    unittest.main()
