"""Covers the 3 GEMINI_API_KEY scenarios for Writing's grade_writing_submission():
valid key + real response, missing key, and a rejected key. Mocks
httpx.post (the actual Gemini call site in writing_feedback.py) rather than
stubbing grade_writing_submission itself, so the real request-building /
response-parsing / fallback logic all runs.
"""

from __future__ import annotations

import json
import os
from unittest import mock

from django.test import TestCase

from app.models import User
from app.writing_feedback import grade_writing_submission


def _fake_gemini_response(status_code: int, payload: dict):
    response = mock.Mock()
    response.status_code = status_code
    response.json.return_value = payload
    return response


def _valid_gemini_payload():
    body = {
        "rubric_score": 88,
        "feedback_summary": "Clear structure and good vocabulary range.",
        "errors": [],
        "recommendations": ["Vary your sentence openings a bit more."],
    }
    return {"candidates": [{"content": {"parts": [{"text": json.dumps(body)}]}}]}


class GradeWritingSubmissionGeminiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(
            username="writer1",
            email="writer1@example.com",
            password="irrelevant-for-this-test",
        )
        self.grade_kwargs = dict(
            user=self.user,
            essay="This is my essay about my favorite hobby, which is reading books.",
            prompt_text="Describe your favorite hobby.",
            min_words=20,
            max_words=200,
            cefr_level="B1",
        )

    def test_valid_api_key_uses_real_gemini_feedback(self):
        """Scenario 1: valid key + mocked Gemini success -> real AI feedback,
        not the placeholder path (caller only falls back on a None result)."""
        with mock.patch.dict("os.environ", {"GEMINI_API_KEY": "valid-test-key"}):
            with mock.patch("app.writing_feedback.httpx.post") as mock_post:
                mock_post.return_value = _fake_gemini_response(200, _valid_gemini_payload())
                result = grade_writing_submission(**self.grade_kwargs)

        mock_post.assert_called_once()
        self.assertIsNotNone(result)
        self.assertEqual(result["rubric_score"], 88)
        self.assertEqual(result["feedback_summary"], "Clear structure and good vocabulary range.")
        self.assertEqual(result["recommendations"], ["Vary your sentence openings a bit more."])

    def test_missing_api_key_short_circuits_to_placeholder_without_http_call(self):
        """Scenario 2: no GEMINI_API_KEY -> None (placeholder path), and no
        HTTP call is even attempted, not just a failed one."""
        with mock.patch.dict("os.environ"):
            os.environ.pop("GEMINI_API_KEY", None)
            with mock.patch("app.writing_feedback.httpx.post") as mock_post:
                result = grade_writing_submission(**self.grade_kwargs)

        mock_post.assert_not_called()
        self.assertIsNone(result)

    def test_invalid_api_key_falls_back_to_placeholder_without_exception(self):
        """Scenario 3: Gemini rejects the key (400 API_KEY_INVALID, the real
        response shape for a bad key) -> falls back to None, same as the
        missing-key path, with no exception raised."""
        rejection_payload = {
            "error": {
                "code": 400,
                "message": "API key not valid. Please pass a valid API key.",
                "status": "INVALID_ARGUMENT",
            }
        }
        with mock.patch.dict("os.environ", {"GEMINI_API_KEY": "rejected-test-key"}):
            with mock.patch("app.writing_feedback.httpx.post") as mock_post:
                mock_post.return_value = _fake_gemini_response(400, rejection_payload)
                result = grade_writing_submission(**self.grade_kwargs)

        mock_post.assert_called_once()
        self.assertIsNone(result)
