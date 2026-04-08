# router/user_rt.py — User endpoints
# Java equivalent: @RestController @RequestMapping("/api/user")

import httpx

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from db.database import get_db
from models.schemas import UserLoginRequest, UserLoginResponse, UserRegisterRequest
from services.user_service import UserService

router = APIRouter(tags=["User"])


@router.post("/login", response_model=UserLoginResponse)
async def login(body: UserLoginRequest, db: AsyncSession = Depends(get_db)):
    """
    Java equivalent:
        @PostMapping("/login")
        public ResponseEntity<TokenResponse> login(@RequestBody LoginRequest body) { ... }
    """
    return await UserService(db).login(body.username, body.password)


@router.post("/register", status_code=201)
async def register(body: UserRegisterRequest, db: AsyncSession = Depends(get_db)):
    """
    Java equivalent:
        @PostMapping("/register")
        @ResponseStatus(HttpStatus.CREATED)
        public void register(@RequestBody RegisterRequest body) { ... }
    """
    return await UserService(db).register(body.username, body.password)


@router.post("/sts-token")
async def get_sts_token():
    """Proxy to Volcano/ByteDance speech-to-text STS token API."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(
                "https://openspeech.bytedance.com/api/v1/sts",
                json={
                    "appid": settings.VOLCANO_APPID,
                    "accessKey": settings.VOLCANO_ACCESS_KEY,
                    "expireTime": 3600,
                },
            )
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=502, detail=f"Volcano STS error: {e.response.text}")
        except httpx.RequestError as e:
            raise HTTPException(status_code=502, detail=f"Volcano STS unreachable: {e}")
    data = resp.json()
    return {"jwt_token": data.get("result", {}).get("token")}
