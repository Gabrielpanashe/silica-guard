import os
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from models import LoginRequest, LoginResponse

router = APIRouter(prefix="/api", tags=["auth"])

ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 12

_bearer_scheme = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
) -> dict:
    """Reusable dependency — import this into any router that needs a logged-in
    hospital/cimas user (e.g. future dashboard endpoints in routers/dashboard.py).
    Screening/miner endpoints stay unauthenticated on purpose: they're called by
    VHWs in the field and by USSD, neither of which holds a dashboard login."""
    try:
        payload = jwt.decode(
            credentials.credentials,
            os.getenv("SECRET_KEY", "dev-secret"),
            algorithms=[ALGORITHM],
        )
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return payload


def _demo_accounts() -> dict:
    return {
        os.getenv("HOSPITAL_EMAIL", "hospital@silicaguard.health"): {
            "password": os.getenv("HOSPITAL_PASSWORD", "change-me"),
            "role": "hospital",
        },
        os.getenv("CIMAS_EMAIL", "cimas@silicaguard.health"): {
            "password": os.getenv("CIMAS_PASSWORD", "change-me"),
            "role": "cimas",
        },
    }


@router.post("/auth/login", response_model=LoginResponse)
def login(payload: LoginRequest):
    account = _demo_accounts().get(payload.email)
    if account is None or account["password"] != payload.password:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    expire = datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRE_HOURS)
    token = jwt.encode(
        {"sub": payload.email, "role": account["role"], "exp": expire},
        os.getenv("SECRET_KEY", "dev-secret"),
        algorithm=ALGORITHM,
    )

    return LoginResponse(access_token=token, role=account["role"])


@router.get("/auth/me")
def read_current_user(user: dict = Depends(get_current_user)):
    """Demo protected route — proves a token is valid and shows what's inside it.
    Not part of the SILICAGUARD.md API contract; here purely so we can see the
    JWT flow work end-to-end in Swagger before real dashboard endpoints exist."""
    return {"email": user["sub"], "role": user["role"]}
