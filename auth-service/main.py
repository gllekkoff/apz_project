import hashlib
import hmac
import os
import secrets
import time
from datetime import datetime
from typing import Optional

import psycopg2
import psycopg2.extras
import redis
from fastapi import Depends, FastAPI, Header, HTTPException, Response, status
from pydantic import BaseModel, Field


AUTH_DB_DSN = os.getenv("AUTH_DB_DSN")
REDIS_URL = os.getenv("REDIS_URL")
TOKEN_TTL_SECONDS = int(os.getenv("AUTH_TOKEN_TTL_SECONDS"))
INSTANCE_ID = os.getenv("INSTANCE_ID")
PBKDF2_ITERATIONS = int(os.getenv("AUTH_PBKDF2_ITERATIONS"))


app = FastAPI(
    title="Authentication Service",
    description="Register, login, logout, and validate Redis-backed sessions.",
    version="1.0.0",
)


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    password: str = Field(..., min_length=6, max_length=256)


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    password: str = Field(..., min_length=6, max_length=256)


class AuthResponse(BaseModel):
    token: str
    token_type: str = "bearer"
    expires_in: int
    user: dict
    instance: str


class UserResponse(BaseModel):
    id: int
    username: str
    created_at: datetime
    instance: str


class ValidateResponse(BaseModel):
    active: bool
    user: Optional[dict] = None
    instance: str


def pg_conn():
    return psycopg2.connect(AUTH_DB_DSN)


def redis_client() -> redis.Redis:
    return redis.from_url(REDIS_URL, decode_responses=True)


def password_hash(password: str, salt_hex: Optional[str] = None) -> str:
    salt = bytes.fromhex(salt_hex) if salt_hex else secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS,
    )
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, iterations, salt_hex, digest_hex = stored_hash.split("$", 3)
    except ValueError:
        return False
    if algorithm != "pbkdf2_sha256":
        return False

    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        bytes.fromhex(salt_hex),
        int(iterations),
    )
    return hmac.compare_digest(digest.hex(), digest_hex)


def session_key(token: str) -> str:
    return f"auth:session:{token}"


def create_schema() -> None:
    last_exc: Optional[Exception] = None
    for _ in range(30):
        try:
            with pg_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        CREATE TABLE IF NOT EXISTS users (
                            id bigserial PRIMARY KEY,
                            username text NOT NULL UNIQUE,
                            password_hash text NOT NULL,
                            created_at timestamptz NOT NULL DEFAULT now()
                        );
                        """
                    )
            return
        except Exception as exc:
            last_exc = exc
            time.sleep(2)
    raise RuntimeError(f"auth database not reachable: {last_exc}")


def get_user_by_username(username: str) -> Optional[dict]:
    with pg_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT id, username, password_hash, created_at FROM users WHERE username = %s",
                (username,),
            )
            return cur.fetchone()


def get_user_by_id(user_id: int) -> Optional[dict]:
    with pg_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT id, username, created_at FROM users WHERE id = %s",
                (user_id,),
            )
            return cur.fetchone()


def create_user(username: str, password: str) -> dict:
    try:
        with pg_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO users (username, password_hash)
                    VALUES (%s, %s)
                    RETURNING id, username, created_at
                    """,
                    (username, password_hash(password)),
                )
                return cur.fetchone()
    except psycopg2.errors.UniqueViolation as exc:
        raise HTTPException(status_code=409, detail="username already exists") from exc


def issue_token(user: dict) -> AuthResponse:
    token = secrets.token_urlsafe(32)
    now = int(time.time())
    expires_at = now + TOKEN_TTL_SECONDS
    payload = {
        "user_id": str(user["id"]),
        "username": user["username"],
        "created_at": str(now),
        "expires_at": str(expires_at),
    }
    client = redis_client()
    client.hset(session_key(token), mapping=payload)
    client.expire(session_key(token), TOKEN_TTL_SECONDS)
    return AuthResponse(
        token=token,
        expires_in=TOKEN_TTL_SECONDS,
        user={"id": user["id"], "username": user["username"]},
        instance=INSTANCE_ID,
    )


def bearer_token(authorization: Optional[str] = Header(None)) -> str:
    if not authorization:
        raise HTTPException(status_code=401, detail="missing Authorization header")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="expected Bearer token")
    return token


def current_session(token: str = Depends(bearer_token)) -> dict:
    client = redis_client()
    data = client.hgetall(session_key(token))
    if not data:
        raise HTTPException(status_code=401, detail="invalid or expired token")
    if int(data.get("expires_at", "0")) <= int(time.time()):
        client.delete(session_key(token))
        raise HTTPException(status_code=401, detail="expired token")
    return data


@app.on_event("startup")
def startup() -> None:
    create_schema()
    redis_client().ping()


@app.get("/health")
def health() -> dict:
    try:
        with pg_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        redis_client().ping()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"status": "ok", "service": "auth-service", "instance": INSTANCE_ID}


@app.post("/auth/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(req: RegisterRequest) -> UserResponse:
    user = create_user(req.username.strip(), req.password)
    return UserResponse(instance=INSTANCE_ID, **user)


@app.post("/auth/login", response_model=AuthResponse)
def login(req: LoginRequest) -> AuthResponse:
    user = get_user_by_username(req.username.strip())
    if not user or not verify_password(req.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="invalid username or password")
    return issue_token(user)


@app.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(token: str = Depends(bearer_token)) -> Response:
    redis_client().delete(session_key(token))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/auth/me", response_model=UserResponse)
def me(session: dict = Depends(current_session)) -> UserResponse:
    user = get_user_by_id(int(session["user_id"]))
    if not user:
        raise HTTPException(status_code=401, detail="user no longer exists")
    return UserResponse(instance=INSTANCE_ID, **user)


@app.post("/auth/validate", response_model=ValidateResponse)
def validate(session: dict = Depends(current_session)) -> ValidateResponse:
    return ValidateResponse(
        active=True,
        user={"id": int(session["user_id"]), "username": session["username"]},
        instance=INSTANCE_ID,
    )
