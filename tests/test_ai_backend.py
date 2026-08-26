from __future__ import annotations

import unittest
import os
from types import SimpleNamespace
from unittest.mock import patch

import bb_summarizer as bb


def args(**overrides):
    values = {
        "ai_backend": "auto",
        "agent_command": None,
        "agent_model": None,
        "agent_timeout": 30,
        "api_key": None,
        "model": bb.DEFAULT_ANTHROPIC_MODEL,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class AiBackendTests(unittest.TestCase):
    def test_default_backend_is_local_auto(self):
        parsed = bb.build_args(["--list-only"])
        self.assertEqual(parsed.ai_backend, "auto")
        self.assertEqual(parsed.ai_workers, 4)
        self.assertFalse(parsed.transcript_only)

    def test_auto_prefers_codex(self):
        options = args()
        with patch.object(bb, "_run_codex_agent", return_value="translated") as codex, \
             patch.object(bb, "_run_claude_agent") as claude:
            self.assertEqual(bb._ai_call("instructions", "input", options), "translated")
        codex.assert_called_once()
        claude.assert_not_called()
        self.assertEqual(options._resolved_ai_backend, "codex")

    @unittest.skipUnless(os.name == "nt", "Windows npm-shim behavior")
    def test_windows_prefers_npm_shim_over_store_alias(self):
        options = args()
        with patch.dict(os.environ, {"APPDATA": r"C:\Users\test\AppData\Roaming"}), \
             patch.object(bb.Path, "exists", return_value=True), \
             patch.object(bb.shutil, "which", return_value=r"C:\WindowsApps\codex.exe"):
            command = bb._find_agent_command("codex", options)
        self.assertEqual(command, r"C:\Users\test\AppData\Roaming\npm\codex.cmd")

    def test_auto_falls_back_to_claude_code(self):
        options = args()
        with patch.object(bb, "_run_codex_agent", side_effect=RuntimeError("missing")), \
             patch.object(bb, "_run_claude_agent", return_value="translated"):
            self.assertEqual(bb._ai_call("instructions", "input", options), "translated")
        self.assertEqual(options._resolved_ai_backend, "claude")

    def test_anthropic_api_is_only_used_when_explicit(self):
        options = args(ai_backend="anthropic")
        with patch.object(bb, "_anthropic_call", return_value="api result") as api:
            self.assertEqual(bb._ai_call("instructions", "input", options), "api result")
        api.assert_called_once()

    def test_auto_never_falls_back_to_anthropic_api(self):
        options = args()
        with patch.object(bb, "_run_codex_agent", side_effect=RuntimeError("missing")), \
             patch.object(bb, "_run_claude_agent", side_effect=RuntimeError("missing")), \
             patch.object(bb, "_anthropic_call") as api:
            with self.assertRaisesRegex(RuntimeError, "No usable local AI agent"):
                bb._ai_call("instructions", "input", options)
        api.assert_not_called()


if __name__ == "__main__":
    unittest.main()
