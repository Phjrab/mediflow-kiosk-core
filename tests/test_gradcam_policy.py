import unittest
from pathlib import Path

from utils.gradcam_policy import gradcam_mode, gradcam_result_state, should_generate_gradcam


class GradCamPolicyTest(unittest.TestCase):
    def test_modes_are_explicit(self):
        self.assertTrue(should_generate_gradcam('always'))
        self.assertFalse(should_generate_gradcam('off'))
        self.assertFalse(should_generate_gradcam('on_demand'))
        self.assertTrue(should_generate_gradcam('on_demand', on_demand=True))
        with self.assertRaises(ValueError):
            gradcam_mode('sometimes')

    def test_missing_heatmap_state_is_not_reported_as_success(self):
        self.assertEqual(gradcam_result_state('off', False), 'disabled')
        self.assertEqual(gradcam_result_state('on_demand', False), 'available_on_demand')
        self.assertEqual(gradcam_result_state('always', False), 'generation_failed')
        self.assertEqual(gradcam_result_state('always', True), 'generated')

    def test_normal_analysis_uses_policy_and_on_demand_is_admin_guarded(self):
        source = Path('eye_server.py').read_text(encoding='utf-8')
        self.assertEqual(source.count('generate_cam=should_generate_gradcam(config.GRADCAM_MODE)'), 3)
        self.assertEqual(source.count('generate_cam=True'), 1)
        route = source[source.index('def api_admin_gradcam_on_demand'):source.index('def _experiment_capabilities')]
        self.assertIn('require_admin_csrf()', route)
        self.assertIn('generate_saved_gradcam', route)

    def test_existing_result_templates_handle_absent_cam(self):
        for name in ('result.html', 'm_result.html'):
            source = (Path('web/templates') / name).read_text(encoding='utf-8')
            self.assertIn('EfficientNet 히트맵 없음', source)
            self.assertIn('sanitizeCamUrl', source)


if __name__ == '__main__':
    unittest.main()
