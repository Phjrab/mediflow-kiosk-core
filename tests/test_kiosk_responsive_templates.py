from pathlib import Path
import unittest


TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "web" / "templates"
STATIC_CSS_DIR = Path(__file__).resolve().parents[1] / "web" / "static" / "css"


def read_template(name: str) -> str:
    return (TEMPLATE_DIR / name).read_text(encoding="utf-8")


class KioskResponsiveTemplateTests(unittest.TestCase):
    def test_legacy_desktop_pages_no_longer_fix_body_to_1280_by_800(self) -> None:
        for name in ("index.html", "login.html", "capture.html", "result.html", "admin_config.html"):
            source = read_template(name)
            self.assertNotIn("width: 1280px", source, name)
            self.assertNotIn("height: 800px", source, name)

    def test_desktop_shells_are_viewport_aware_and_centered(self) -> None:
        for name in ("capture.html", "result.html", "report.html", "admin_config.html"):
            source = read_template(name)
            self.assertIn("margin: 0 auto", source, name)
            self.assertIn("width: 100%", source, name)
            self.assertIn("min-height: 100vh", source, name)

    def test_training_and_survey_constrain_content_without_fixed_viewport(self) -> None:
        training = read_template("training.html")
        survey = read_template("survey.html")
        self.assertIn("width: min(1240px, calc(100vw - 40px))", training)
        self.assertIn("height: min(760px, calc(100dvh - 40px))", training)
        self.assertIn("width: min(100%, 1280px)", survey)

    def test_chat_panel_accounts_for_bottom_controls_on_short_viewports(self) -> None:
        source = (STATIC_CSS_DIR / "chat-widget.css").read_text(encoding="utf-8")
        self.assertIn("height: min(520px, calc(100dvh - 260px))", source)

    def test_admin_config_exposes_a_working_theme_toggle(self) -> None:
        source = read_template("admin_config.html")
        self.assertIn('id="global-theme-toggle"', source)
        self.assertIn("themeToggle.addEventListener('click'", source)
        self.assertIn("applyTheme(currentTheme() === 'dark' ? 'light' : 'dark', true)", source)


if __name__ == "__main__":
    unittest.main()
