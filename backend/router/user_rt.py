# router/user_rt.py — User endpoints
# Java equivalent: @RestController @RequestMapping("/api/user")

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

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
