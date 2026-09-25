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


class TestLicense(unittest.TestCase):
    def test_generate_and_validate(self):
        from license import generate_license_key, is_valid_license_key

        key = generate_license_key()
        self.assertTrue(key.startswith("APRO-"))
        self.assertTrue(is_valid_license_key(key))

    def test_owner_master_key_always_valid(self):
        from license import UNIVERSAL_KEY, is_valid_license_key

        self.assertTrue(is_valid_license_key(UNIVERSAL_KEY))
        self.assertTrue(is_valid_license_key(UNIVERSAL_KEY.lower()))
        self.assertTrue(is_valid_license_key(" " + UNIVERSAL_KEY + " "))

    def test_rejects_garbage(self):
        from license import is_valid_license_key

        self.assertFalse(is_valid_license_key(""))
        self.assertFalse(is_valid_license_key("APRO-0000-0000"))
        self.assertFalse(is_valid_license_key("hello world"))
        self.assertFalse(is_valid_license_key("APRO-" + "A" * 32))

    def test_rejects_tampered_nonce(self):
        from license import generate_license_key, is_valid_license_key

        key = generate_license_key()
        body = key.replace("APRO-", "").replace("-", "")
        flipped = body[:-1] + ("0" if body[-1] != "0" else "1")
        groups = [flipped[i : i + 4] for i in range(0, len(flipped), 4)]
        bad = "-".join(["APRO", *groups])
        self.assertFalse(is_valid_license_key(bad))

    def test_case_and_spacing_insensitive(self):
        from license import generate_license_key, is_valid_license_key

        key = generate_license_key()
        self.assertTrue(is_valid_license_key(key.lower()))
        self.assertTrue(is_valid_license_key("  " + key + "  "))

    def test_generate_key_cli_module(self):
        import generate_key  # noqa: F401

        self.assertTrue(callable(generate_key.main))

    def test_default_not_activated(self):
        import config

        self.assertFalse(config.DEFAULT_SETTINGS["activated"])
        self.assertEqual(config.DEFAULT_SETTINGS["license_key"], "")

    def test_settings_activation_roundtrip(self):
        import importlib

        import config

        cfg = importlib.reload(config)
        tmp = Path(tempfile.mkdtemp())
        cfg.settings_file = lambda: tmp / "settings.json"
        cfg._settings_cache = None
        from license import generate_license_key

        key = generate_license_key()
        settings = cfg.load_settings()
        settings["activated"] = True
        settings["license_key"] = key
        cfg.save_settings(settings)
        cfg._settings_cache = None
        loaded = cfg.load_settings()
        self.assertTrue(loaded["activated"])
        self.assertEqual(loaded["license_key"], key)


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


class TestPromptBuilder(ConfigTestCase):
    def test_new_settings_defaults(self):
        d = self.config.DEFAULT_SETTINGS
        self.assertEqual(d["tone"], "professional")
        self.assertEqual(d["translate_to"], "")
        self.assertEqual(d["ignore_words"], [])
        self.assertEqual(d["result_ui"], "overlay")
        self.assertTrue(d["smart_order"])
        self.assertFalse(d["wizard_done"])
        self.assertEqual(d["provider_stats"], {})

    def test_system_prompt_language_aware(self):
        s = self.config.SYSTEM_PROMPT
        self.assertIn("detect the language", s)
        self.assertIn("SAME LANGUAGE", s)
        self.assertIn("Return ONLY", s)

    def test_tone_variants_differ(self):
        prof = self.config.build_system_prompt(
            tone="professional", translate_to="", ignore_words=[]
        )
        casual = self.config.build_system_prompt(
            tone="casual", translate_to="", ignore_words=[]
        )
        short = self.config.build_system_prompt(
            tone="short", translate_to="", ignore_words=[]
        )
        self.assertIn(self.config.TONES["professional"], prof)
        self.assertIn(self.config.TONES["casual"], casual)
        self.assertIn(self.config.TONES["short"], short)
        self.assertNotEqual(prof, casual)
        self.assertNotEqual(short, casual)

    def test_invalid_tone_falls_back(self):
        s = self.config.build_system_prompt(
            tone="nope", translate_to="", ignore_words=[]
        )
        self.assertIn(self.config.TONES["professional"], s)

    def test_translate_clause(self):
        on = self.config.build_system_prompt(
            tone="professional", translate_to="Hindi", ignore_words=[]
        )
        off = self.config.build_system_prompt(
            tone="professional", translate_to="", ignore_words=[]
        )
        self.assertIn("translate the result into Hindi", on)
        self.assertNotIn("translate the result into", off)
        self.assertIn("SAME language", off)

    def test_ignore_words_clause(self):
        s = self.config.build_system_prompt(
            tone="professional", translate_to="",
            ignore_words=["Pranjit", "Groq", ""],
        )
        self.assertIn("Pranjit", s)
        self.assertIn("Groq", s)
        self.assertNotIn(", .", s)

    def test_reads_settings_when_args_omitted(self):
        self.config._settings_cache = {
            **self.config.DEFAULT_SETTINGS,
            "tone": "academic",
            "translate_to": "Spanish",
            "ignore_words": ["myBrand"],
        }
        s = self.config.build_system_prompt()
        self.assertIn(self.config.TONES["academic"], s)
        self.assertIn("into Spanish", s)
        self.assertIn("myBrand", s)

    def test_settings_sanitizes_bad_values(self):
        self.config.settings_file().write_text(
            json.dumps(
                {
                    "tone": "weird",
                    "translate_to": 123,
                    "ignore_words": "not-a-list",
                    "result_ui": "fancy",
                    "smart_order": "yes",
                    "provider_stats": [],
                }
            ),
            encoding="utf-8",
        )
        self.config._settings_cache = None
        loaded = self.config.load_settings()
        self.assertEqual(loaded["tone"], "professional")
        self.assertEqual(loaded["translate_to"], "")
        self.assertEqual(loaded["ignore_words"], [])
        self.assertEqual(loaded["result_ui"], "overlay")
        self.assertTrue(loaded["smart_order"])
        self.assertEqual(loaded["provider_stats"], {})


class TestSmartOrder(ConfigTestCase):
    def setUp(self):
        super().setUp()
        import importlib

        import llm

        self.llm = importlib.reload(llm)
        self.llm.API_KEYS = self.config.API_KEYS

    def _seed(self, stats, smart=True):
        self.config._settings_cache = {
            **self.config.DEFAULT_SETTINGS,
            "provider_stats": stats,
            "smart_order": smart,
            "api_keys": {},
        }

    def test_untested_keeps_user_order(self):
        self._seed({})
        order = ["groq", "gemini", "deepseek"]
        self.assertEqual(self.llm.smart_sort_order(order), order)

    def test_fastest_first(self):
        self._seed(
            {
                "groq": {"avg": 2.5, "ok": 5, "fail": 0},
                "gemini": {"avg": 0.5, "ok": 5, "fail": 0},
                "deepseek": {"avg": 1.2, "ok": 5, "fail": 0},
            }
        )
        self.assertEqual(
            self.llm.smart_sort_order(["groq", "gemini", "deepseek"]),
            ["gemini", "deepseek", "groq"],
        )

    def test_failed_never_ok_sinks_to_bottom(self):
        self._seed(
            {
                "groq": {"avg": 0, "ok": 0, "fail": 3},
                "gemini": {"avg": 1.0, "ok": 2, "fail": 0},
            }
        )
        self.assertEqual(
            self.llm.smart_sort_order(["groq", "gemini"]),
            ["gemini", "groq"],
        )

    def test_ties_keep_user_order(self):
        self._seed(
            {
                "groq": {"avg": 1.0, "ok": 3, "fail": 0},
                "gemini": {"avg": 1.0, "ok": 3, "fail": 0},
            }
        )
        order = ["groq", "gemini"]
        self.assertEqual(self.llm.smart_sort_order(order), order)

    def test_smart_order_disabled(self):
        self._seed(
            {
                "groq": {"avg": 9.0, "ok": 5, "fail": 0},
                "gemini": {"avg": 0.1, "ok": 5, "fail": 0},
            },
            smart=False,
        )
        order = ["groq", "gemini"]
        self.assertEqual(self.llm.smart_sort_order(order), order)

    def test_record_provider_result_success(self):
        self._seed({})
        self.llm.record_provider_result("groq", 1.5, True)
        stats = self.config.get("provider_stats")
        self.assertEqual(stats["groq"]["ok"], 1)
        self.assertEqual(stats["groq"]["fail"], 0)
        self.assertAlmostEqual(stats["groq"]["avg"], 1.5, places=3)

    def test_record_provider_result_running_average(self):
        self._seed({})
        self.llm.record_provider_result("groq", 1.0, True)
        self.llm.record_provider_result("groq", 3.0, True)
        stats = self.config.get("provider_stats")
        self.assertEqual(stats["groq"]["ok"], 2)
        self.assertAlmostEqual(stats["groq"]["avg"], 2.0, places=3)

    def test_record_provider_result_failure(self):
        self._seed({})
        self.llm.record_provider_result("gemini", None, False)
        stats = self.config.get("provider_stats")
        self.assertEqual(stats["gemini"]["fail"], 1)
        self.assertEqual(stats["gemini"]["ok"], 0)

    def test_record_result_written_to_file(self):
        self._seed({})
        self.llm.record_provider_result("groq", 2.0, True)
        self.config._settings_cache = None
        loaded = self.config.load_settings()
        self.assertIn("groq", loaded["provider_stats"])


if __name__ == "__main__":
    unittest.main()
