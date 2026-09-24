import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PROVIDER_ENV = (
    "GROQ_API_KEY",
    "GEMINI_API_KEY",
    "NVIDIA_NIM_API_KEY",
    "DEEPSEEK_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "PROVIDER_ORDER",
)


def _clean_env(extra=None):
    env = {k: "" for k in PROVIDER_ENV}
    if extra:
        env.update(extra)
    return env


class ConfigTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._env_patch = mock.patch.dict(os.environ, _clean_env(), clear=False)
        self._env_patch.start()
        for k in PROVIDER_ENV:
            os.environ[k] = ""
        import importlib

        import config

        self.config = importlib.reload(config)
        self.config.settings_file = lambda: self.tmp / "settings.json"
        self.config.history_file = lambda: self.tmp / "history.json"
        self.config.data_dir = lambda: self.tmp
        self.config._settings_cache = None
        self.config.API_KEYS.clear()
        self.config.reload_api_keys()

    def tearDown(self):
        self._env_patch.stop()


class TestConfig(ConfigTestCase):
    def test_settings_roundtrip(self):
        cfg = self.config
        settings = cfg.load_settings()
        settings["hotkey"] = "ctrl+alt+x"
        settings["auto_replace"] = True
        settings["provider_order"] = ["deepseek", "groq"]
        cfg.save_settings(settings)
        cfg._settings_cache = None
        loaded = cfg.load_settings()
        self.assertEqual(loaded["hotkey"], "ctrl+alt+x")
        self.assertTrue(loaded["auto_replace"])
        self.assertEqual(loaded["provider_order"], ["deepseek", "groq"])

    def test_settings_overrides_env_order_when_env_empty(self):
        cfg = self.config
        settings = cfg.load_settings()
        self.assertNotEqual(settings["provider_order"], None)
        settings["provider_order"] = ["gemini", "groq"]
        cfg.save_settings(settings)
        cfg._settings_cache = None
        self.assertEqual(cfg.load_settings()["provider_order"], ["gemini", "groq"])

    def test_env_keys_loaded(self):
        os.environ["GROQ_API_KEY"] = "env-groq"
        cfg = self.config
        cfg.API_KEYS.clear()
        cfg.reload_api_keys()
        self.assertEqual(cfg.API_KEYS.get("groq"), "env-groq")

    def test_settings_api_keys_override_env(self):
        os.environ["GROQ_API_KEY"] = "env-groq"
        cfg = self.config
        cfg.save_settings(
            {**cfg.load_settings(), "api_keys": {"groq": "settings-groq"}}
        )
        self.assertEqual(cfg.API_KEYS.get("groq"), "settings-groq")

    def test_provider_urls_cover_all_labels(self):
        cfg = self.config
        for name in cfg.PROVIDER_LABELS:
            self.assertIn(name, cfg.PROVIDER_URLS)
            self.assertTrue(cfg.PROVIDER_URLS[name].startswith("https://"))

    def test_default_hotkey(self):
        self.assertEqual(self.config.DEFAULT_SETTINGS["hotkey"], "ctrl+alt+z")


class TestHistory(ConfigTestCase):
    def setUp(self):
        super().setUp()
        import importlib

        import history

        self.history = importlib.reload(history)
        self.config._settings_cache = {
            **self.config.DEFAULT_SETTINGS,
            "max_history": 3,
            "api_keys": {},
        }
        self.history.clear()

    def test_add_and_list(self):
        self.history.add("orig", "fixed", "groq")
        items = self.history.list_items()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["original"], "orig")
        self.assertEqual(items[0]["corrected"], "fixed")
        self.assertEqual(items[0]["provider"], "groq")

    def test_max_history(self):
        for i in range(10):
            self.history.add(f"o{i}", f"c{i}", "groq")
        self.assertLessEqual(len(self.history.list_items()), 3)

    def test_clear(self):
        self.history.add("a", "b", "groq")
        self.history.clear()
        self.assertEqual(self.history.list_items(), [])

    def test_invalid_file_returns_empty(self):
        self.config.history_file().write_text("not-json", encoding="utf-8")
        self.assertEqual(self.history.list_items(), [])


class TestLLM(ConfigTestCase):
    def setUp(self):
        super().setUp()
        import importlib

        import llm

        self.llm = importlib.reload(llm)
        self.llm.API_KEYS = self.config.API_KEYS

    def test_providers_registered(self):
        for name in ("groq", "gemini", "nvidia_nim", "deepseek", "openai", "claude"):
            self.assertIn(name, self.llm.PROVIDERS)
            self.assertTrue(callable(self.llm.PROVIDERS[name]))

    def test_available_providers_skips_missing_keys(self):
        self.config.API_KEYS.clear()
        self.config.API_KEYS.update({"groq": "k"})
        self.config._settings_cache = {
            **self.config.DEFAULT_SETTINGS,
            "provider_order": ["groq", "gemini"],
            "api_keys": {"groq": "k"},
        }
        self.assertEqual(self.llm.available_providers(["groq", "gemini"]), ["groq"])

    def test_check_text_no_keys_raises(self):
        self.config.API_KEYS.clear()
        self.config._settings_cache = {
            **self.config.DEFAULT_SETTINGS,
            "provider_order": ["groq"],
            "api_keys": {},
        }
        with self.assertRaises(self.llm.ProviderError) as ctx:
            self.llm.check_text("hello")
        self.assertIn("No API keys", str(ctx.exception))

    def test_test_provider_without_key(self):
        ok, msg = self.llm.test_provider("groq")
        self.assertFalse(ok)
        self.assertEqual(msg, "no API key")

    def test_test_provider_unknown(self):
        ok, msg = self.llm.test_provider("nope")
        self.assertFalse(ok)
        self.assertEqual(msg, "unknown provider")


class TestInstaller(unittest.TestCase):
    def test_iss_references_exe(self):
        iss = Path(__file__).resolve().parents[1] / "installer" / "AIProofreader.iss"
        self.assertTrue(iss.is_file())
        text = iss.read_text(encoding="utf-8")
        self.assertIn("AI_Proofreader.exe", text)
        self.assertIn("LICENSE", text)
        self.assertIn("PRIVACY.md", text)

    def test_license_and_privacy_exist(self):
        root = Path(__file__).resolve().parents[1]
        self.assertTrue((root / "LICENSE").is_file())
        license_text = (root / "LICENSE").read_text(encoding="utf-8")
        self.assertIn("BRING YOUR OWN KEY", license_text)
        privacy = (root / "PRIVACY.md").read_text(encoding="utf-8")
        self.assertIn("API keys", privacy)
        self.assertIn("No analytics or telemetry", privacy)

    def test_spec_includes_license_privacy(self):
        root = Path(__file__).resolve().parents[1]
        spec = (root / "AI_Proofreader.spec").read_text(encoding="utf-8")
        self.assertIn("LICENSE", spec)
        self.assertIn("PRIVACY.md", spec)


class TestUpdater(ConfigTestCase):
    def setUp(self):
        super().setUp()
        import importlib

        import updater

        self.updater = importlib.reload(updater)

    def test_parse_ver(self):
        self.assertEqual(self.updater._parse_ver("v1.2.3"), (1, 2, 3))
        self.assertEqual(self.updater._parse_ver("1.0"), (1, 0, 0))
        self.assertEqual(self.updater._parse_ver(""), (0, 0, 0))

    def test_is_newer(self):
        self.assertTrue(self.updater.is_newer("v1.0.1", "1.0.0"))
        self.assertFalse(self.updater.is_newer("v1.0.0", "1.0.0"))
        self.assertFalse(self.updater.is_newer("v0.9.9", "1.0.0"))
        self.assertTrue(self.updater.is_newer("2.0.0", "1.9.9"))

    def test_check_without_repo_returns_none(self):
        self.config._settings_cache = {
            **self.config.DEFAULT_SETTINGS,
            "update_repo": "",
            "api_keys": {},
        }
        # Falls back to DEFAULT_UPDATE_REPO if set; force no repo.
        old = self.updater.DEFAULT_UPDATE_REPO
        self.updater.DEFAULT_UPDATE_REPO = ""
        try:
            self.assertIsNone(self.updater.check_for_update())
        finally:
            self.updater.DEFAULT_UPDATE_REPO = old

    def test_update_repo_setting(self):
        self.config._settings_cache = {
            **self.config.DEFAULT_SETTINGS,
            "update_repo": "someone/ai-proofreader",
            "api_keys": {},
        }
        self.assertEqual(self.updater.update_repo(), "someone/ai-proofreader")

    def test_default_update_repo(self):
        self.assertEqual(
            self.config.DEFAULT_SETTINGS["update_repo"],
            "HITESHDAS-01/proofread_ai",
        )
        self.assertEqual(
            self.updater.DEFAULT_UPDATE_REPO,
            "HITESHDAS-01/proofread_ai",
        )

    def test_default_auto_update_enabled(self):
        self.assertTrue(self.config.DEFAULT_SETTINGS["auto_update"])


if __name__ == "__main__":
    unittest.main()
