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
        iss = Path(__file__).resolve().parents[1] / "installer" / "TextMateAI.iss"
        self.assertTrue(iss.is_file())
        text = iss.read_text(encoding="utf-8")
        self.assertIn("TextMate_AI.exe", text)
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
        spec = (root / "TextMate_AI.spec").read_text(encoding="utf-8")
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
            "update_repo": "someone/textmate-ai",
            "api_keys": {},
        }
        self.assertEqual(self.updater.update_repo(), "someone/textmate-ai")

    def test_default_update_repo(self):
        self.assertEqual(
            self.config.DEFAULT_SETTINGS["update_repo"],
            "HITESHDAS-01/textmate-ai-releases",
        )
        self.assertEqual(
            self.updater.DEFAULT_UPDATE_REPO,
            "HITESHDAS-01/textmate-ai-releases",
        )

    def test_update_repo_migration_from_private_repo(self):
        self.config.settings_file().write_text(
            json.dumps({**self.config.DEFAULT_SETTINGS,
                        "update_repo": "HITESHDAS-01/proofread_ai"}),
            encoding="utf-8",
        )
        self.config._settings_cache = None
        self.assertEqual(
            self.config.load_settings()["update_repo"],
            "HITESHDAS-01/textmate-ai-releases",
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


class TestTranslateLanguages(ConfigTestCase):
    def test_all_scheduled_indian_languages_present(self):
        scheduled = [
            "Assamese", "Bengali", "Bodo", "Dogri", "Gujarati", "Hindi",
            "Kannada", "Kashmiri", "Konkani", "Maithili", "Malayalam",
            "Manipuri", "Marathi", "Nepali", "Odia", "Punjabi", "Sanskrit",
            "Santali", "Sindhi", "Tamil", "Telugu", "Urdu",
        ]
        indian = dict(self.config.TRANSLATE_LANG_GROUPS)["Indian languages"]
        for lang in scheduled:
            self.assertIn(lang, indian)
        self.assertIn("English", indian)

    def test_only_famous_world_languages(self):
        world = dict(self.config.TRANSLATE_LANG_GROUPS)["World languages"]
        expected = {
            "Spanish", "French", "German", "Portuguese", "Italian",
            "Russian", "Japanese", "Chinese", "Korean", "Arabic", "Turkish",
        }
        self.assertEqual(set(world), expected)
        self.assertNotIn("Dutch", self.config.TRANSLATE_LANGS)

    def test_no_duplicates_across_groups(self):
        langs = self.config.TRANSLATE_LANGS
        self.assertEqual(len(langs), len(set(langs)))


class TestActions(ConfigTestCase):
    def test_all_actions_have_valid_kinds(self):
        for aid, spec in self.config.ACTIONS.items():
            self.assertIn(spec["kind"], ("edit", "info"))
            self.assertTrue(self.config.action_label(aid))
            if aid != "proofread":
                self.assertTrue(spec["rule"].strip())
        self.assertEqual(self.config.action_kind("explain"), "info")
        self.assertEqual(self.config.action_kind("improve"), "edit")
        self.assertEqual(self.config.action_kind("unknown"), "edit")

    def test_explain_is_info_prompt(self):
        s = self.config.build_system_prompt(
            action="explain", tone="professional", translate_to="Hindi",
            ignore_words=[],
        )
        self.assertIn(self.config.ACTIONS["explain"]["rule"][:40], s)
        self.assertIn("preamble", s)
        # tone/translate clauses are edit-only
        self.assertNotIn(self.config.TONES["professional"], s)
        self.assertNotIn("translate the result into Hindi", s)

    def test_improve_keeps_tone_and_language(self):
        s = self.config.build_system_prompt(
            action="improve", tone="casual", translate_to="", ignore_words=[],
        )
        self.assertIn(self.config.ACTIONS["improve"]["rule"][:40], s)
        self.assertIn(self.config.TONES["casual"], s)
        self.assertIn("SAME language", s)
        self.assertIn("Return ONLY the text", s)

    def test_summarize_hint_appended(self):
        plain = self.config.build_system_prompt(action="summarize")
        hinted = self.config.build_system_prompt(
            action="summarize", hint="Summarize in one sentence."
        )
        self.assertIn("one sentence", hinted)
        self.assertNotEqual(plain, hinted)

    def test_custom_prompt_system(self):
        s = self.config.custom_prompt_system("Convert to professional email")
        self.assertIn("Convert to professional email", s)
        self.assertIn("Return ONLY the result", s)

    def test_summarize_presets_exist(self):
        self.assertGreaterEqual(len(self.config.SUMMARIZE_PRESETS), 3)
        for label, hint in self.config.SUMMARIZE_PRESETS:
            self.assertTrue(label and hint)


class TestMyCommands(ConfigTestCase):
    def test_defaults_present(self):
        cmds = self.config.load_settings()["my_commands"]
        self.assertGreaterEqual(len(cmds), 4)
        for c in cmds:
            self.assertTrue(c["name"] and c["prompt"])

    def test_sanitize_drops_invalid_entries(self):
        self.config.settings_file().write_text(
            json.dumps(
                {
                    "my_commands": [
                        {"name": "", "prompt": "x"},
                        {"name": "Good", "prompt": "do it"},
                        "junk",
                        {"name": "No prompt"},
                    ]
                }
            ),
            encoding="utf-8",
        )
        self.config._settings_cache = None
        cmds = self.config.load_settings()["my_commands"]
        self.assertEqual(cmds, [{"name": "Good", "prompt": "do it"}])

    def test_roundtrip(self):
        settings = self.config.load_settings()
        settings["my_commands"] = [{"name": "My cmd", "prompt": "Say hi"}]
        self.config.save_settings(settings)
        self.config._settings_cache = None
        loaded = self.config.load_settings()
        self.assertEqual(loaded["my_commands"], [{"name": "My cmd", "prompt": "Say hi"}])

    def test_new_hotkey_defaults(self):
        d = self.config.load_settings()
        self.assertEqual(d["palette_hotkey"], "ctrl+alt+space")
        self.assertEqual(d["ocr_hotkey"], "ctrl+alt+o")
        self.assertEqual(d["undo_hotkey"], "ctrl+alt+u")


class TestTextDiff(unittest.TestCase):
    def setUp(self):
        import textdiff

        self.td = textdiff

    def test_reconstructs_corrected(self):
        spans = self.td.diff_spans("he go to offce", "He went to office")
        rebuilt = "".join(t for t, _ in spans)
        self.assertEqual(rebuilt, "He went to office")

    def test_changed_words_flagged(self):
        spans = self.td.diff_spans("bad text here", "good text here")
        flags = {t.strip(): c for t, c in spans}
        self.assertTrue(flags.get("good"))
        self.assertFalse(flags.get("text here", flags.get("text")))

    def test_identical_has_no_changes(self):
        spans = self.td.diff_spans("same text", "same text")
        self.assertFalse(self.td.has_changes(spans))
        self.assertEqual("".join(t for t, _ in spans), "same text")

    def test_preview_limit(self):
        spans = self.td.diff_spans("a b c d e f", "a b c d e f g h i j")
        prev = self.td.preview_spans(spans, 6)
        text = "".join(t for t, _ in prev)
        self.assertLessEqual(len(text), 6)


class TestOCR(unittest.TestCase):
    def setUp(self):
        import ocr

        self.ocr = ocr
        from PIL import Image

        self.image = Image.new("RGB", (20, 10), "white")

    def test_available_is_bool(self):
        self.assertIsInstance(self.ocr.available(), bool)

    def test_non_windows_raises(self):
        with mock.patch.object(self.ocr, "available", return_value=False):
            with self.assertRaises(self.ocr.OcrError):
                self.ocr.recognize(self.image)

    def test_script_failure_raises(self):
        def fake_run(*args, **kwargs):
            return mock.Mock(returncode=1, stderr=b"kapow", stdout=b"")

        with mock.patch.object(self.ocr, "available", return_value=True), \
                mock.patch.object(self.ocr.subprocess, "run", side_effect=fake_run):
            with self.assertRaises(self.ocr.OcrError):
                self.ocr.recognize(self.image)

    def test_missing_language_pack_message(self):
        def fake_run(*args, **kwargs):
            return mock.Mock(returncode=3, stderr=b"", stdout=b"")

        with mock.patch.object(self.ocr, "available", return_value=True), \
                mock.patch.object(self.ocr.subprocess, "run", side_effect=fake_run):
            with self.assertRaises(self.ocr.OcrError) as ctx:
                self.ocr.recognize(self.image)
        self.assertIn("OCR language", str(ctx.exception))

    def test_success_reads_output_file(self):
        def fake_run(cmd, **kwargs):
            out_path = cmd[cmd.index("-OutPath") + 1]
            with open(out_path, "w", encoding="utf-8") as fh:
                fh.write("recognized text")
            return mock.Mock(returncode=0, stderr=b"", stdout=b"")

        with mock.patch.object(self.ocr, "available", return_value=True), \
                mock.patch.object(self.ocr.subprocess, "run", side_effect=fake_run):
            text = self.ocr.recognize(self.image)
        self.assertEqual(text, "recognized text")


class TestVisionOCR(ConfigTestCase):
    def setUp(self):
        super().setUp()
        import importlib

        import llm

        self.llm = importlib.reload(llm)
        self.llm.API_KEYS = self.config.API_KEYS

    def _seed(self, order, keys):
        self.config.API_KEYS.clear()
        self.config.API_KEYS.update(keys)
        self.config._settings_cache = {
            **self.config.DEFAULT_SETTINGS,
            "provider_order": order,
            "api_keys": keys,
        }

    def test_vision_available_with_groq_key(self):
        self._seed(["groq"], {"groq": "k"})
        self.assertTrue(self.llm.vision_available())

    def test_vision_unavailable_text_only_key(self):
        self._seed(["deepseek"], {"deepseek": "k"})
        self.assertFalse(self.llm.vision_available())

    def test_vision_ocr_uses_groq_qwen(self):
        self._seed(["groq"], {"groq": "k"})
        captured = {}

        def fake_post(url, headers, payload):
            captured["url"] = url
            captured["payload"] = payload
            return {"choices": [{"message": {"content": "Hello world"}}]}

        with mock.patch.object(self.llm, "_post_json", side_effect=fake_post):
            out = self.llm.vision_ocr("AAAA")
        self.assertEqual(out, "Hello world")
        self.assertEqual(
            captured["payload"]["model"],
            "qwen/qwen3.8-27b",
        )
        content = captured["payload"]["messages"][0]["content"]
        self.assertEqual(content[0]["text"], self.llm.VISION_OCR_PROMPT)
        self.assertEqual(
            content[1]["image_url"]["url"], "data:image/jpeg;base64,AAAA"
        )
        self.assertEqual(self.llm.LAST_PROVIDER, "groq")

    def test_vision_ocr_falls_through_to_gemini(self):
        self._seed(["groq", "gemini"], {"groq": "k", "gemini": "k"})

        def fake_post(url, headers, payload):
            if "groq" in url:
                raise self.llm.ProviderError("kapow")
            self.assertIn("inline_data", str(payload))
            return {"candidates": [{"content": {"parts": [{"text": "from gemini"}]}}]}

        with mock.patch.object(self.llm, "_post_json", side_effect=fake_post):
            out = self.llm.vision_ocr("AAAA")
        self.assertEqual(out, "from gemini")

    def test_vision_ocr_no_vision_provider_raises(self):
        self._seed(["deepseek"], {"deepseek": "k"})
        with self.assertRaises(self.llm.ProviderError) as ctx:
            self.llm.vision_ocr("AAAA")
        self.assertIn("vision-capable", str(ctx.exception))

    def test_prepare_image_upscales_small_and_encodes_jpeg(self):
        import base64

        import main
        from PIL import Image

        img = Image.new("RGB", (100, 40), "white")
        b64, size = main._prepare_ocr_image(img)
        self.assertEqual(size, (200, 80))
        raw = base64.b64decode(b64)
        self.assertEqual(raw[:2], b"\xff\xd8")

    def test_prepare_image_caps_large_captures(self):
        import main
        from PIL import Image

        img = Image.new("RGB", (4000, 1000), "white")
        b64, size = main._prepare_ocr_image(img)
        self.assertLessEqual(max(size), 1600)
        self.assertGreater(len(b64), 100)


class TestPaletteUI(unittest.TestCase):
    def test_fuzzy_match(self):
        import ui

        self.assertTrue(ui.fuzzy_match("eml", "Professional Email"))
        self.assertTrue(ui.fuzzy_match("", "anything"))
        self.assertFalse(ui.fuzzy_match("zzz", "Professional Email"))

    def test_fuzzy_score_orders_prefix_first(self):
        import ui

        self.assertGreater(
            ui._fuzzy_score("assamese", "Assamese"),
            ui._fuzzy_score("assamese", "Translate to Assamese"),
        )

    def test_palette_items_include_actions_commands_utils(self):
        import ui

        items = ui.palette_items()
        ids = [i["id"] for i in items]
        self.assertIn("action:proofread", ids)
        self.assertIn("action:explain", ids)
        self.assertIn("undo", ids)
        self.assertIn("settings", ids)
        self.assertTrue(any(i.startswith("command:") for i in ids))
        self.assertTrue(any(i.startswith("summary:") for i in ids))


if __name__ == "__main__":
    unittest.main()
