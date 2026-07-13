import os
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException
from jose import jwt

from models import LoginRequest, LoginResponse

router = APIRouter(prefix="/api", tags=["auth"])

ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 12


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
