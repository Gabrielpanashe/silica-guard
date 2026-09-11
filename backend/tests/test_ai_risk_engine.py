"""services/ai_risk_engine.py's retry-with-backoff (23 August 2026) — found
live via Render's own logs that POST /api/screen's 502s were caused by
Gemini genuinely returning "503 Service Unavailable" for gemini-flash-latest,
not a code/key/network bug (the same key succeeded on a different network
moments later). A transient 503 should not surface as a failed screening at
all if a quick retry would have succeeded."""

from unittest.mock import MagicMock, patch

from services import ai_risk_engine


def _fake_response(text):
    resp = MagicMock()
    resp.text = text
    return resp


def _ten_answers():
    return [
        MagicMock(question_code=f"Q{i}", answer_value="x", answer_score=1)
        for i in range(10)
    ]


VALID_JSON = (
    '{"tier": "GREEN", "confidence": 0.9, '
    '"contributing_factors": [], "explanation_english": "fine"}'
)


def test_succeeds_first_try_without_any_retry():
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = _fake_response(VALID_JSON)

    with patch("services.ai_risk_engine._client", return_value=mock_client), \
         patch("services.ai_risk_engine.time.sleep") as mock_sleep:
        result = ai_risk_engine.assess_risk(_ten_answers())

    assert result["tier"] == "GREEN"
    assert mock_client.models.generate_content.call_count == 1
    mock_sleep.assert_not_called()


def test_recovers_after_one_transient_failure():
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = [
        Exception("503 Service Unavailable"),
        _fake_response(VALID_JSON),
    ]

    with patch("services.ai_risk_engine._client", return_value=mock_client), \
         patch("services.ai_risk_engine.time.sleep") as mock_sleep:
        result = ai_risk_engine.assess_risk(_ten_answers())

    assert result["tier"] == "GREEN"
    assert mock_client.models.generate_content.call_count == 2
    mock_sleep.assert_called_once()


def test_raises_the_real_error_after_exhausting_all_retries():
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = Exception("503 Service Unavailable")

    with patch("services.ai_risk_engine._client", return_value=mock_client), \
         patch("services.ai_risk_engine.time.sleep") as mock_sleep:
        try:
            ai_risk_engine.assess_risk(_ten_answers())
            assert False, "expected an exception"
        except Exception as e:
            assert "503" in str(e)

    assert mock_client.models.generate_content.call_count == ai_risk_engine._MAX_ATTEMPTS
    assert mock_sleep.call_count == ai_risk_engine._MAX_ATTEMPTS - 1
