"""
tests/test_step1_ai_client.py

Unit tests for agents/ai_client.py.

All watsonx SDK calls are mocked — no real API calls are made.
Tests pass whether or not watsonx credentials are configured in the environment.

Environment variables are saved before each test class and restored afterward,
so pre-existing credentials in the developer's environment are never destroyed.
"""

import sys
import os
import time
import unittest
from unittest.mock import patch, MagicMock

# Ensure the project root is on sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

_CRED_VARS = ("WATSONX_API_KEY", "WATSONX_PROJECT_ID", "WATSONX_URL")


def _save_env():
    """Return a snapshot of the three credential env vars (value or None)."""
    return {var: os.environ.get(var) for var in _CRED_VARS}


def _restore_env(snapshot):
    """Restore the environment to a previously saved snapshot."""
    for var, value in snapshot.items():
        if value is None:
            os.environ.pop(var, None)
        else:
            os.environ[var] = value


def _reload_ai_client():
    """Force a fresh import of ai_client so module-level credential reads re-execute."""
    if "agents.ai_client" in sys.modules:
        del sys.modules["agents.ai_client"]
    import agents.ai_client as ai_client
    return ai_client


# ---------------------------------------------------------------------------
# Tests: credentials absent
# ---------------------------------------------------------------------------

class TestAIClientUnavailable(unittest.TestCase):
    """Behaviour when all three credential env vars are absent."""

    def setUp(self):
        self._snapshot = _save_env()
        for var in _CRED_VARS:
            os.environ.pop(var, None)
        self.ai = _reload_ai_client()

    def tearDown(self):
        _restore_env(self._snapshot)
        if "agents.ai_client" in sys.modules:
            del sys.modules["agents.ai_client"]

    def test_is_available_false(self):
        self.assertFalse(self.ai.is_available())

    def test_generate_text_returns_none(self):
        self.assertIsNone(self.ai.generate_text("Hello"))

    def test_embed_texts_returns_none(self):
        self.assertIsNone(self.ai.embed_texts(["Hello", "World"]))

    def test_embed_empty_list_returns_empty_regardless_of_credentials(self):
        """Empty input always returns [] — no API call needed."""
        result = self.ai.embed_texts([])
        self.assertEqual(result, [])


# ---------------------------------------------------------------------------
# Tests: credentials present, SDK mocked
# ---------------------------------------------------------------------------

class TestAIClientAvailable(unittest.TestCase):
    """Behaviour when credentials are present and SDK is mocked."""

    def setUp(self):
        self._snapshot = _save_env()
        os.environ["WATSONX_API_KEY"]    = "test-key"
        os.environ["WATSONX_PROJECT_ID"] = "test-project"
        os.environ["WATSONX_URL"]        = "https://us-south.ml.cloud.ibm.com"
        self.ai = _reload_ai_client()

    def tearDown(self):
        _restore_env(self._snapshot)
        if "agents.ai_client" in sys.modules:
            del sys.modules["agents.ai_client"]

    def test_is_available_true(self):
        self.assertTrue(self.ai.is_available())

    # --- generate_text ---

    def test_generate_text_success(self):
        mock_model = MagicMock()
        mock_model.generate_text.return_value = "Career tip: learn Python."
        with patch("ibm_watsonx_ai.foundation_models.ModelInference",
                   return_value=mock_model):
            result = self.ai.generate_text("Give me career advice")
        self.assertEqual(result, "Career tip: learn Python.")

    def test_generate_text_api_error_returns_none(self):
        mock_model = MagicMock()
        mock_model.generate_text.side_effect = ValueError("bad request")
        with patch("ibm_watsonx_ai.foundation_models.ModelInference",
                   return_value=mock_model):
            result = self.ai.generate_text("prompt")
        self.assertIsNone(result)

    def test_generate_text_timeout_returns_none(self):
        """
        Set a very short timeout so the slow mock exceeds it.
        The call must return None quickly rather than blocking indefinitely.
        """
        self.ai._TIMEOUT = 0.05

        mock_model = MagicMock()

        def _slow(*args, **kwargs):
            time.sleep(2)
            return "should not reach here"

        mock_model.generate_text.side_effect = _slow
        with patch("ibm_watsonx_ai.foundation_models.ModelInference",
                   return_value=mock_model):
            start = time.monotonic()
            result = self.ai.generate_text("slow prompt")
            elapsed = time.monotonic() - start

        self.assertIsNone(result)
        # Should have returned in well under 1 second (generous allowance for CI)
        self.assertLess(elapsed, 1.5,
                        f"generate_text did not time out quickly enough ({elapsed:.2f}s)")

    def test_generate_text_retries_transient_error(self):
        """
        Transient errors (e.g. 'service unavailable') trigger up to MAX_RETRIES retries.
        After all retries are exhausted the function returns None.
        """
        mock_model = MagicMock()
        mock_model.generate_text.side_effect = RuntimeError("503 service unavailable")
        with patch("ibm_watsonx_ai.foundation_models.ModelInference",
                   return_value=mock_model):
            # Patch sleep to avoid actual delay in the test
            with patch("agents.ai_client.time.sleep"):
                result = self.ai.generate_text("prompt")

        self.assertIsNone(result)
        # Should have been called 1 original + MAX_RETRIES times
        expected_calls = 1 + self.ai.MAX_RETRIES
        self.assertEqual(mock_model.generate_text.call_count, expected_calls)

    # --- embed_texts ---

    def test_embed_texts_flat_list_response(self):
        """SDK returns list[list[float]] directly (newer SDK form)."""
        mock_emb = MagicMock()
        mock_emb.embed_documents.return_value = [
            [0.1, 0.2, 0.3],
            [0.4, 0.5, 0.6],
        ]
        with patch("ibm_watsonx_ai.foundation_models.Embeddings",
                   return_value=mock_emb):
            result = self.ai.embed_texts(["text one", "text two"])

        self.assertIsNotNone(result)
        self.assertEqual(len(result), 2)
        self.assertIsInstance(result[0], list)
        self.assertAlmostEqual(result[0][0], 0.1)

    def test_embed_texts_dict_response_normalised(self):
        """SDK returns list[dict] with 'embedding' key — must be normalised to list[list[float]]."""
        mock_emb = MagicMock()
        mock_emb.embed_documents.return_value = [
            {"embedding": [0.1, 0.2, 0.3]},
            {"embedding": [0.4, 0.5, 0.6]},
        ]
        with patch("ibm_watsonx_ai.foundation_models.Embeddings",
                   return_value=mock_emb):
            result = self.ai.embed_texts(["text one", "text two"])

        self.assertIsNotNone(result)
        self.assertEqual(len(result), 2)
        self.assertIsInstance(result[0], list)
        self.assertAlmostEqual(result[0][0], 0.1)

    def test_embed_texts_api_error_returns_none(self):
        mock_emb = MagicMock()
        mock_emb.embed_documents.side_effect = RuntimeError("embed error")
        with patch("ibm_watsonx_ai.foundation_models.Embeddings",
                   return_value=mock_emb):
            result = self.ai.embed_texts(["text one"])
        self.assertIsNone(result)

    def test_embed_texts_timeout_returns_none(self):
        """Slow embed call must return None before the timeout elapses."""
        self.ai._TIMEOUT = 0.05

        mock_emb = MagicMock()

        def _slow(*args, **kwargs):
            time.sleep(2)
            return [[0.1, 0.2]]

        mock_emb.embed_documents.side_effect = _slow
        with patch("ibm_watsonx_ai.foundation_models.Embeddings",
                   return_value=mock_emb):
            start = time.monotonic()
            result = self.ai.embed_texts(["text one"])
            elapsed = time.monotonic() - start

        self.assertIsNone(result)
        self.assertLess(elapsed, 1.5,
                        f"embed_texts did not time out quickly enough ({elapsed:.2f}s)")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
