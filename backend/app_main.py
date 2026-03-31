# app_main.py — FastAPI entry point
# Java equivalent: @SpringBootApplication main class

import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from db.database import init_db
from exceptions.auth import AuthError
from router import chat_rt, history_rt, user_rt

root_path = os.getenv("ROOT_PATH", "http://localhost:8000")

app = FastAPI(
    title="DeepSearch API",
    version="1.0.0",
    root_path=root_path,
)

# ── Middleware ────────────────────────────────────────────────────────────────
# Java equivalent: WebMvcConfigurer.addCorsMappings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Exception handlers ────────────────────────────────────────────────────────
# Java equivalent: @ExceptionHandler / @ControllerAdvice
@app.exception_handler(AuthError)
async def auth_error_handler(request: Request, exc: AuthError):
    return JSONResponse(status_code=401, content={"detail": exc.message})

# ── Routers (Controllers) ─────────────────────────────────────────────────────
# Java equivalent: @RestController classes auto-detected by component scan
app.include_router(user_rt.router)      # /login, /register
app.include_router(chat_rt.router)      # /create_session, /chat_on_docs, /quick_parse
app.include_router(history_rt.router)   # /get_sessions, /get_messages, /upload_files

@app.on_event("startup")
async def on_startup():
    await init_db()

@app.get("/health")
def health_check():
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
