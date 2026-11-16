from fastapi import APIRouter, BackgroundTasks, Form
from fastapi.responses import PlainTextResponse

from services.ussd_handler import handle_ussd

router = APIRouter(prefix="/api", tags=["ussd"])


@router.post("/ussd", response_class=PlainTextResponse)
def ussd_webhook(
    background: BackgroundTasks,
    sessionId: str = Form(...),
    phoneNumber: str = Form(...),
    serviceCode: str = Form(...),
    text: str = Form(""),
):
    """Africa's Talking posts form-encoded fields on every screen of a session.
    `text` accumulates every input the user has entered so far, joined by '*'
    (e.g. "1*3*2").

    **Must respond within 10 seconds, and the budget is 3** (`CLAUDE.md`).
    The decision tree is pure and the database work is two or three queries,
    but the final turn also owes the miner an SMS and the facility a pre-alert
    — three outbound calls with 10-second timeouts each, which measured 6
    seconds against a merely slow gateway and could reach 30. This docstring
    claimed "no network calls, so this is effectively instant" while that was
    happening.

    `background.add_task` is what makes the claim true: FastAPI runs those
    tasks after the response has gone back to the gateway, so the sending
    cannot cost the miner the screen that tells him where to go. The screening
    is committed before any send either way.
    """
    return handle_ussd(sessionId, phoneNumber, text, defer=background.add_task)
