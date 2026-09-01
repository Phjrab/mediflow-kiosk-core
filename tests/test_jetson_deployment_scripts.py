import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class JetsonDeploymentScriptTest(unittest.TestCase):
    def test_installer_does_not_add_autostart_or_guessed_wheels(self):
        source = (ROOT / 'scripts' / 'install_jetson.sh').read_text(encoding='utf-8')
        self.assertNotIn('systemctl enable', source)
        self.assertNotIn('@reboot', source)
        self.assertNotIn('nvarguscamerasrc', source)
        self.assertNotRegex(source, r'https?://[^\s]+\.whl')
        self.assertIn('--torch-wheel', source)
        self.assertIn('--torchvision-wheel', source)

    def test_preflight_supports_camera_skip_and_service_smoke(self):
        source = (ROOT / 'scripts' / 'jetson_preflight.py').read_text(encoding='utf-8')
        self.assertIn('--allow-no-camera', source)
        self.assertIn('--service-smoke-test', source)
        self.assertNotIn('nvarguscamerasrc', source)
        self.assertIn("[str(manager), 'status']", source)

    def test_legacy_wrappers_delegate_without_pattern_kills(self):
        for filename in ('start_services.sh', 'stop_services.sh'):
            source = (ROOT / filename).read_text(encoding='utf-8')
            self.assertIn('scripts/mediflow-kiosk', source)
            self.assertNotIn('pkill', source)
            self.assertNotIn('killall', source)


if __name__ == '__main__':
    unittest.main()
