from __future__ import annotations

import os
from pathlib import Path
import unittest
from unittest.mock import patch

from pulso_brain_host.config import BrainConfig


class BrainConfigTest(unittest.TestCase):
    def test_default_artifact_targets_gemma_4_e4b(self):
        with patch.dict(os.environ, {}, clear=True):
            config = BrainConfig.from_env(Path("/project"))

        self.assertEqual(config.model_id, "gemma-4-E4B-it.litertlm")
        self.assertEqual(config.semantic_cooldown_s, 8.0)
        self.assertEqual(
            config.model_path, Path("/project/.tools/models/gemma-4-E4B-it.litertlm")
        )

    def test_model_identity_follows_configured_artifact_without_exposing_path(self):
        configured = "/private/models/site-tuned-gemma-4-E4B-it.litertlm"
        with patch.dict(os.environ, {"PULSO_GEMMA_MODEL": configured}, clear=True):
            config = BrainConfig.from_env(Path("/project"))

        self.assertEqual(config.model_id, "site-tuned-gemma-4-E4B-it.litertlm")
        self.assertNotIn("/private/", config.model_id)

    def test_semantic_cooldown_is_configurable_but_bounded(self):
        with patch.dict(
            os.environ, {"PULSO_SEMANTIC_COOLDOWN_S": "12.5"}, clear=True
        ):
            config = BrainConfig.from_env(Path("/project"))
        self.assertEqual(config.semantic_cooldown_s, 12.5)

        for invalid in (-0.1, 60.1):
            with self.subTest(invalid=invalid):
                invalid_config = BrainConfig(
                    "ws://test",
                    Path(__file__),
                    semantic_cooldown_s=invalid,
                )
                with self.assertRaisesRegex(ValueError, "between 0 and 60"):
                    invalid_config.validate()


if __name__ == "__main__":
    unittest.main()
