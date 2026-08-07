import sqlite3
from unittest.mock import patch

import database
from services import notifications

URL = "/api/ussd"


def _post(client, session_id, phone, text):
    resp = client.post(
        URL,
        data={
            "sessionId": session_id,
            "phoneNumber": phone,
            "serviceCode": "*384*1#",
            "text": text,
        },
    )
    assert resp.status_code == 200
    return resp.text


def _walk_session(client, session_id, phone, choices):
    """choices: list of menu numbers, one per question, in order."""
    reply = _post(client, session_id, phone, "")
    assert reply.startswith("CON ")

    accumulated = []
    for choice in choices:
        accumulated.append(choice)
        reply = _post(client, session_id, phone, "*".join(accumulated))
    return reply


def test_first_screen_shows_question_one(client):
    reply = _post(client, "s1", "+263770000001", "")
    assert reply.startswith("CON ")
    assert "Makangoshanda mangani emakore" in reply  # YEARS_UNDERGROUND question text


def test_invalid_choice_reshows_same_question(client):
    _post(client, "s2", "+263770000002", "")
    reply = _post(client, "s2", "+263770000002", "99")  # out of range for Q1 (only 4 options)
    assert reply.startswith("CON ")
    assert "Makangoshanda mangani emakore" in reply  # still on Q1, not advanced


def test_full_session_green_low_risk(client):
    # under_2 years, surface job, always wet, always N95, no symptoms at all
    reply = _walk_session(
        client, "s3", "+263770000003", ["1", "4", "1", "1", "1", "1", "1", "1", "1", "1"]
    )
    assert reply.startswith("END ")
    assert "Njodzi yako iri pasi" in reply  # GREEN fixed Shona message


def test_full_session_red_via_safety_trigger(client):
    # severe breathlessness alone should force RED regardless of other answers
    reply = _walk_session(
        client, "s4", "+263770000004", ["1", "4", "1", "1", "1", "3", "1", "1", "1", "1"]
    )
    assert reply.startswith("END ")
    assert "njodzi yakakwira" in reply  # RED dangerous-trigger Shona message


def test_full_session_yellow_via_score(client):
    # 2-5 years (score2) + loading job (score3) + sometimes wet (score2) = 7 total,
    # no dangerous triggers -> should land in the YELLOW band (6-11)
    reply = _walk_session(
        client, "s5", "+263770000005", ["2", "2", "2", "1", "1", "1", "1", "1", "1", "1"]
    )
    assert reply.startswith("END ")
    assert "njodzi yakati wandei" in reply  # YELLOW fixed Shona message


def test_full_session_orange_via_score_no_trigger(client):
    # over_10 years (5) + drilling (5) + never wet (4) = 14 total, no dangerous
    # triggers touched -> should land in ORANGE (score >= 12, no safety trigger)
    reply = _walk_session(
        client, "s5b", "+263770000015", ["4", "1", "3", "1", "1", "1", "1", "1", "1", "1"]
    )
    assert reply.startswith("END ")
    assert "Zvakafanana nemamiriro ane njodzi" in reply  # ORANGE score-based Shona message


def test_completed_session_persists_to_database(client):
    _walk_session(
        client, "s6", "+263770000006", ["1", "4", "1", "1", "1", "1", "1", "1", "1", "1"]
    )

    conn = sqlite3.connect(database.DATABASE_URL)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT s.*, m.phone FROM screenings s JOIN miners m ON m.id = s.miner_id "
        "WHERE m.phone = ?",
        ("+263770000006",),
    ).fetchone()
    assert row is not None
    assert row["channel"] == "USSD"
    assert row["screened_by"] == "USSD_SELF"
    assert row["tier"] == "GREEN"
    assert row["fallback_used"] == 1

    answer_count = conn.execute(
        "SELECT COUNT(*) FROM screening_answers WHERE screening_id = ?", (row["id"],)
    ).fetchone()[0]
    assert answer_count == 10
    conn.close()


def test_green_result_sends_screening_result_sms_not_referral(client):
    with patch.object(notifications, "send_screening_result_sms", return_value=True) as mock_sms:
        reply = _walk_session(
            client, "s8", "+263770000008", ["1", "4", "1", "1", "1", "1", "1", "1", "1", "1"]
        )

    assert reply.startswith("END ")
    mock_sms.assert_called_once()
    assert mock_sms.call_args[0][2] == "GREEN"

    conn = sqlite3.connect(database.DATABASE_URL)
    conn.row_factory = sqlite3.Row
    referral = conn.execute(
        "SELECT r.* FROM referrals r JOIN miners m ON m.id = r.miner_id WHERE m.phone = ?",
        ("+263770000008",),
    ).fetchone()
    conn.close()
    assert referral is None


def test_session_state_cleared_after_completion(client):
    from services import ussd_handler

    _walk_session(
        client, "s7", "+263770000007", ["1", "4", "1", "1", "1", "1", "1", "1", "1", "1"]
    )
    assert "s7" not in ussd_handler._sessions
