from fastapi import APIRouter, Form
from fastapi.responses import PlainTextResponse

from services.ussd_handler import handle_ussd

router = APIRouter(prefix="/api", tags=["ussd"])


@router.post("/ussd", response_class=PlainTextResponse)
def ussd_webhook(
    sessionId: str = Form(...),
    phoneNumber: str = Form(...),
    serviceCode: str = Form(...),
    text: str = Form(""),
):
    """Africa's Talking posts form-encoded fields on every screen of a session.
    `text` accumulates every input the user has entered so far, joined by '*'
    (e.g. "1*3*2"). Must respond within 10 seconds — handle_ussd is pure
    decision-tree logic, no network calls, so this is effectively instant."""
    return handle_ussd(sessionId, phoneNumber, text)
