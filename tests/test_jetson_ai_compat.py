import unittest
from pathlib import Path

from utils.jetson_compat import classify_runtime, known_platform, parse_l4t_release, version_pair


ROOT = Path(__file__).resolve().parents[1]


class JetsonAICompatTest(unittest.TestCase):
    def test_l4t_parser_and_known_platform(self):
        release = parse_l4t_release('# R36 (release), REVISION: 5.2, GCID: 123')
        self.assertEqual(release, '36.5.2')
        self.assertEqual(known_platform(release)['jetpack_family'], '6.2.2')
        self.assertEqual(known_platform(release)['expected_cuda_family'], '12.6')

    def test_version_parser_is_bounded_and_explicit(self):
        self.assertEqual(version_pair('2.11.0+cu130'), (2, 11))
        self.assertEqual(version_pair('13.0'), (13, 0))
        self.assertIsNone(version_pair(None))

    def test_observed_b_mismatch_is_blocked(self):
        result = classify_runtime(
            architecture='aarch64',
            l4t_release='36.5.2',
            torch_imported=True,
            torch_version='2.11.0+cu130',
            torch_cuda='13.0',
            cuda_available=False,
        )
        self.assertEqual(result['state'], 'BLOCKED_COMPATIBILITY')
        self.assertEqual(len(result['reasons']), 3)
        self.assertFalse(result['replacement_selected'])
        self.assertFalse(result['installation_performed'])

    def test_compatible_core_observation_can_pass_without_model_claim(self):
        result = classify_runtime(
            architecture='aarch64',
            l4t_release='36.5.0',
            torch_imported=True,
            torch_version='2.8.0a0+nv25.06',
            torch_cuda='12.6',
            cuda_available=True,
        )
        self.assertEqual(result['state'], 'READY_CORE')
        self.assertFalse(result['model_loaded'])

    def test_report_script_contains_no_mutating_package_action(self):
        source = (ROOT / 'scripts' / 'jetson_ai_compat_report.py').read_text(encoding='utf-8')
        for forbidden in ('apt install', 'pip install', 'sudo ', 'systemctl', 'docker pull'):
            self.assertNotIn(forbidden, source)
        self.assertIn("'inspection': 'read_only_no_network_no_model_load'", source)


if __name__ == '__main__':
    unittest.main()
