from __future__ import annotations

import hashlib
import hmac
import io
import json
import os
import secrets
import sqlite3
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, Response
from pydantic import BaseModel
from PIL import Image


app = FastAPI(title="Image Resizer")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://image-resizer-dusky.vercel.app",
        "https://desto374.github.io",
        "http://127.0.0.1:5500",
        "http://localhost:5500",
        "http://127.0.0.1:8001",
        "http://localhost:8001",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

OUTPUT_SIZES = {
    "album_ditto_soundcloud": (3000, 3000),
    "youtube_thumbnail": (1280, 720),
    "instagram_square": (1080, 1080),
    "instagram_portrait": (1080, 1350),
    "instagram_reels": (1080, 1920),
}

SUPPORTED_MIME_TYPES = {"image/jpeg", "image/png"}
SESSION_COOKIE_NAME = "pixelfit_session"
SESSION_MAX_AGE_SECONDS = 60 * 60 * 24 * 7
OAUTH_STATE_TTL_SECONDS = 600
DB_PATH = Path(__file__).with_name("pixelfit.db")


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


load_env_file(Path(__file__).with_name(".env.local"))
load_env_file(Path(__file__).with_name(".env"))

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URL = os.getenv("GOOGLE_REDIRECT_URL")
FRONTEND_REDIRECT_URL = os.getenv("FRONTEND_REDIRECT_URL", "http://127.0.0.1:5500/index.html")
ENV = os.getenv("ENV", "dev")
COOKIE_SECURE = os.getenv("COOKIE_SECURE")
COOKIE_SAMESITE = os.getenv("COOKIE_SAMESITE", "lax")


class HealthResponse(BaseModel):
    status: str


class SizeItem(BaseModel):
    label: str
    width: int
    height: int


class SizesResponse(BaseModel):
    sizes: List[SizeItem]


class SignupRequest(BaseModel):
    name: str
    username: str
    gender: str
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class UsernameRequest(BaseModel):
    username: str


def resize_stretch(img: Image.Image, target_size: tuple[int, int]) -> Image.Image:
    return img.resize(target_size, Image.LANCZOS)


def safe_stem(filename: str) -> str:
    stem = Path(filename).stem
    return stem or "image"


def parse_optional_json_list(raw_value: Optional[str], list_name: str) -> Optional[List[str]]:
    if raw_value is None or raw_value == "":
        return None
    try:
        parsed = json.loads(raw_value)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON for {list_name}.") from exc
    if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
        raise HTTPException(status_code=400, detail=f"{list_name} must be a JSON array of strings.")
    return parsed


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _ensure_users_table(conn: sqlite3.Connection) -> None:
    table = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='users'"
    ).fetchone()
    if table:
        columns = list(conn.execute("PRAGMA table_info(users)"))
        needs_migration = any(
            row["name"] in {"password_hash", "salt"} and row["notnull"] == 1 for row in columns
        )
        if needs_migration:
            _migrate_users_table(conn, columns)
        else:
            _ensure_column(conn, "users", "provider", "TEXT NOT NULL DEFAULT 'local'")
            _ensure_column(conn, "users", "provider_sub", "TEXT")
            _ensure_column(conn, "users", "name", "TEXT")
            _ensure_column(conn, "users", "username", "TEXT")
            _ensure_column(conn, "users", "gender", "TEXT")
            _ensure_column(conn, "users", "avatar_url", "TEXT")
            _ensure_column(conn, "users", "password_hash", "TEXT")
            _ensure_column(conn, "users", "salt", "TEXT")
            _ensure_column(
                conn, "users", "created_at", "INTEGER NOT NULL DEFAULT (strftime('%s','now'))"
            )
        return

    conn.execute(
        """
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            provider TEXT NOT NULL,
            provider_sub TEXT UNIQUE,
            name TEXT,
            username TEXT,
            gender TEXT,
            avatar_url TEXT,
            password_hash TEXT,
            salt TEXT,
            created_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
        )
        """
    )


def _migrate_users_table(conn: sqlite3.Connection, columns: list[sqlite3.Row]) -> None:
    existing = {row["name"] for row in columns}
    conn.execute(
        """
        CREATE TABLE users_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            provider TEXT NOT NULL,
            provider_sub TEXT UNIQUE,
            name TEXT,
            username TEXT,
            gender TEXT,
            avatar_url TEXT,
            password_hash TEXT,
            salt TEXT,
            created_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
        )
        """
    )
    select_parts = [
        "id" if "id" in existing else "NULL AS id",
        "email" if "email" in existing else "NULL AS email",
        "name" if "name" in existing else "NULL AS name",
        "password_hash" if "password_hash" in existing else "NULL AS password_hash",
        "salt" if "salt" in existing else "NULL AS salt",
        "created_at" if "created_at" in existing else "strftime('%s','now') AS created_at",
        "auth_provider" if "auth_provider" in existing else "provider" if "provider" in existing else "'local' AS provider",
        "google_sub" if "google_sub" in existing else "provider_sub" if "provider_sub" in existing else "NULL AS provider_sub",
        "username" if "username" in existing else "NULL AS username",
        "gender" if "gender" in existing else "NULL AS gender",
        "avatar_url" if "avatar_url" in existing else "NULL AS avatar_url",
    ]
    select_sql = ", ".join(select_parts)
    conn.execute(
        f"""
        INSERT INTO users_new (id, email, name, password_hash, salt, created_at, provider, provider_sub, username, gender, avatar_url)
        SELECT {select_sql} FROM users
        """
    )
    conn.execute("DROP TABLE users")
    conn.execute("ALTER TABLE users_new RENAME TO users")


def init_db() -> None:
    with get_db() as conn:
        _ensure_users_table(conn)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                token TEXT NOT NULL UNIQUE,
                created_at INTEGER NOT NULL,
                expires_at INTEGER NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
            """
        )
        _ensure_column(conn, "sessions", "expires_at", "INTEGER NOT NULL DEFAULT 0")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS oauth_states (
            state TEXT PRIMARY KEY,
            purpose TEXT NOT NULL,
            user_id INTEGER,
            created_at INTEGER NOT NULL
        )
        """
    )


def base_username_from_email(email: str) -> str:
    prefix = email.split("@", 1)[0].strip()
    return prefix or "user"


def ensure_unique_username(conn: sqlite3.Connection, base: str) -> str:
    candidate = base
    suffix = 1
    while conn.execute("SELECT 1 FROM users WHERE username = ? LIMIT 1", (candidate,)).fetchone():
        suffix += 1
        candidate = f"{base}{suffix}"
    return candidate


def hash_password(password: str, salt: bytes) -> str:
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120_000)
    return digest.hex()


def create_session(conn: sqlite3.Connection, user_id: int) -> str:
    cleanup_sessions(conn)
    token = secrets.token_urlsafe(32)
    conn.execute(
        "INSERT INTO sessions (user_id, token, created_at, expires_at) VALUES (?, ?, strftime('%s','now'), strftime('%s','now') + ?)",
        (user_id, token, SESSION_MAX_AGE_SECONDS),
    )
    return token


def cleanup_sessions(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM sessions WHERE expires_at <= strftime('%s','now')")


def get_user_by_session(conn: sqlite3.Connection, token: str) -> Optional[sqlite3.Row]:
    cleanup_sessions(conn)
    row = conn.execute(
        """
        SELECT users.id, users.name, users.username, users.gender, users.email, users.provider, users.avatar_url
        FROM sessions
        JOIN users ON users.id = sessions.user_id
        WHERE sessions.token = ? AND sessions.expires_at > strftime('%s','now')
        """,
        (token,),
    ).fetchone()
    return row


def delete_session(conn: sqlite3.Connection, token: str) -> None:
    conn.execute("DELETE FROM sessions WHERE token = ?", (token,))


def require_google_config() -> None:
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET or not GOOGLE_REDIRECT_URL:
        raise HTTPException(status_code=500, detail="Google auth is not configured.")


def cookie_settings() -> dict:
    secure_default = ENV == "prod"
    if COOKIE_SECURE is None:
        secure = secure_default
    else:
        secure = COOKIE_SECURE.lower() in {"1", "true", "yes"}
    if COOKIE_SAMESITE:
        samesite = COOKIE_SAMESITE.lower()
    else:
        samesite = "none" if ENV == "prod" else "lax"
    if samesite not in {"lax", "strict", "none"}:
        samesite = "lax"
    if samesite == "none" and not secure:
        secure = True
    return {
        "httponly": True,
        "samesite": samesite,
        "secure": secure,
        "max_age": SESSION_MAX_AGE_SECONDS,
        "path": "/",
    }


def create_oauth_state(conn: sqlite3.Connection, purpose: str, user_id: Optional[int]) -> str:
    state = secrets.token_urlsafe(24)
    conn.execute(
        "INSERT INTO oauth_states (state, purpose, user_id, created_at) VALUES (?, ?, ?, strftime('%s','now'))",
        (state, purpose, user_id),
    )
    return state


def pop_oauth_state(conn: sqlite3.Connection, state: str) -> Optional[sqlite3.Row]:
    row = conn.execute(
        "SELECT state, purpose, user_id, created_at FROM oauth_states WHERE state = ?",
        (state,),
    ).fetchone()
    if not row:
        return None
    conn.execute("DELETE FROM oauth_states WHERE state = ?", (state,))
    return row


def cleanup_oauth_states(conn: sqlite3.Connection) -> None:
    conn.execute(
        "DELETE FROM oauth_states WHERE created_at <= strftime('%s','now') - ?",
        (OAUTH_STATE_TTL_SECONDS,),
    )


@app.on_event("startup")
def on_startup() -> None:
    init_db()


@app.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    return HealthResponse(status="ok")


@app.get("/")
def root() -> JSONResponse:
    return JSONResponse({"ok": True})


@app.get("/api/health")
def api_health() -> JSONResponse:
    return JSONResponse({"ok": True})


@app.get("/sizes", response_model=SizesResponse)
def list_sizes() -> SizesResponse:
    sizes = [
        SizeItem(label=label, width=width, height=height)
        for label, (width, height) in OUTPUT_SIZES.items()
    ]
    return SizesResponse(sizes=sizes)


@app.post("/resize")
async def resize_images(
    files: List[UploadFile] = File(...),
    main_folder: Optional[str] = Form(None),
    base_names: Optional[str] = Form(None),
) -> Response:
    if not files:
        raise HTTPException(status_code=400, detail="No files provided.")

    base_name_list = parse_optional_json_list(base_names, "base_names")
    main_folder_list = parse_optional_json_list(main_folder, "main_folder")

    if base_name_list is not None and len(base_name_list) != len(files):
        raise HTTPException(status_code=400, detail="base_names length must match files length.")

    if main_folder_list is not None and len(main_folder_list) != len(files):
        raise HTTPException(status_code=400, detail="main_folder length must match files length.")

    zip_buffer = io.BytesIO()

    try:
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
            for index, upload in enumerate(files):
                if upload.content_type not in SUPPORTED_MIME_TYPES:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Unsupported file type for {upload.filename}.",
                    )

                file_bytes = await upload.read()
                try:
                    img = Image.open(io.BytesIO(file_bytes)).convert("RGB")
                except Exception as exc:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Unable to open {upload.filename} as an image.",
                    ) from exc

                base_name = (
                    base_name_list[index]
                    if base_name_list is not None
                    else safe_stem(upload.filename)
                )
                folder_name = (
                    main_folder_list[index]
                    if main_folder_list is not None
                    else (main_folder or safe_stem(upload.filename))
                )

                for label, (width, height) in OUTPUT_SIZES.items():
                    out_img = resize_stretch(img, (width, height))
                    out_name = f"{base_name}_{label}_{width}x{height}.jpeg"
                    img_buffer = io.BytesIO()
                    out_img.save(img_buffer, format="JPEG", quality=92, optimize=True)
                    img_buffer.seek(0)
                    zip_path = f"{folder_name}/{out_name}"
                    zipf.writestr(zip_path, img_buffer.read())
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Processing error: {exc}") from exc

    zip_buffer.seek(0)
    headers = {"Content-Disposition": "attachment; filename=resized_images.zip"}
    return Response(content=zip_buffer.getvalue(), media_type="application/zip", headers=headers)


@app.post("/api/signup")
def signup(payload: SignupRequest) -> JSONResponse:
    name = payload.name.strip()
    username = payload.username.strip()
    gender = payload.gender.strip().lower()
    email = payload.email.strip().lower()
    password = payload.password

    if not name or not username or not email or not password or not gender:
        raise HTTPException(status_code=400, detail="Name, username, gender, email, and password are required.")
    if gender not in {"male", "female"}:
        raise HTTPException(status_code=400, detail="Gender must be 'male' or 'female'.")

    salt = secrets.token_bytes(16)
    password_hash = hash_password(password, salt)

    with get_db() as conn:
        existing = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if existing:
            raise HTTPException(status_code=400, detail="An account with that email already exists.")

        if conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone():
            raise HTTPException(status_code=400, detail="That username is already taken.")

        cursor = conn.execute(
            """
            INSERT INTO users (email, provider, name, username, gender, password_hash, salt)
            VALUES (?, 'local', ?, ?, ?, ?, ?)
            """,
            (email, name, username, gender, password_hash, salt.hex()),
        )
        user_id = cursor.lastrowid
        token = create_session(conn, user_id)

    response = JSONResponse(
        {
            "status": "ok",
            "user": {"id": user_id, "name": name, "username": username, "gender": gender, "email": email},
        }
    )
    response.set_cookie(SESSION_COOKIE_NAME, token, **cookie_settings())
    return response


@app.post("/api/login")
def login(payload: LoginRequest) -> JSONResponse:
    email = payload.email.strip().lower()
    password = payload.password

    with get_db() as conn:
        user = conn.execute(
            """
            SELECT id, name, username, gender, email, password_hash, salt, provider
            FROM users
            WHERE email = ?
            """,
            (email,),
        ).fetchone()
        if not user:
            raise HTTPException(status_code=401, detail="Invalid email or password.")

        if not user["password_hash"] or not user["salt"]:
            raise HTTPException(status_code=401, detail="Please use Google sign-in for this account.")

        salt = bytes.fromhex(user["salt"])
        expected_hash = user["password_hash"]
        candidate_hash = hash_password(password, salt)
        if not hmac.compare_digest(candidate_hash, expected_hash):
            raise HTTPException(status_code=401, detail="Invalid email or password.")

        token = create_session(conn, user["id"])

    response = JSONResponse(
        {
            "status": "ok",
            "user": {
                "id": user["id"],
                "name": user["name"],
                "username": user["username"],
                "gender": user["gender"],
                "email": user["email"],
            },
        }
    )
    response.set_cookie(SESSION_COOKIE_NAME, token, **cookie_settings())
    return response


def build_google_auth_url(state: str, prompt: str) -> str:
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URL,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": prompt,
        "state": state,
    }
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)


def exchange_google_token(code: str) -> dict:
    token_payload = {
        "code": code,
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "redirect_uri": GOOGLE_REDIRECT_URL,
        "grant_type": "authorization_code",
    }
    token_request = urllib.request.Request(
        "https://oauth2.googleapis.com/token",
        data=urllib.parse.urlencode(token_payload).encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(token_request) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_google_profile(access_token: str) -> dict:
    userinfo_request = urllib.request.Request(
        "https://openidconnect.googleapis.com/v1/userinfo",
        headers={"Authorization": f"Bearer {access_token}"},
        method="GET",
    )
    with urllib.request.urlopen(userinfo_request) as response:
        return json.loads(response.read().decode("utf-8"))


@app.get("/api/auth/google/start")
def google_start() -> RedirectResponse:
    require_google_config()
    with get_db() as conn:
        cleanup_oauth_states(conn)
        state = create_oauth_state(conn, "login", None)
    url = build_google_auth_url(state, prompt="consent")
    return RedirectResponse(url=url)


@app.get("/api/auth/google/callback")
def google_callback(code: Optional[str] = None, state: Optional[str] = None) -> Response:
    require_google_config()
    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing code or state.")

    with get_db() as conn:
        cleanup_oauth_states(conn)
        state_row = pop_oauth_state(conn, state)
        if not state_row:
            raise HTTPException(status_code=400, detail="Invalid or expired OAuth state.")

    try:
        token_data = exchange_google_token(code)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Failed to exchange Google token.") from exc

    access_token = token_data.get("access_token")
    if not access_token:
        raise HTTPException(status_code=400, detail="Google token response missing access token.")

    try:
        profile = fetch_google_profile(access_token)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Failed to fetch Google profile.") from exc

    email = (profile.get("email") or "").lower()
    name = profile.get("name") or "Pixelfit User"
    google_sub = profile.get("sub")
    avatar_url = profile.get("picture")

    if not email or not google_sub:
        raise HTTPException(status_code=400, detail="Google profile missing required fields.")

    with get_db() as conn:
        user = conn.execute(
            """
            SELECT id, email, provider, provider_sub, username
            FROM users
            WHERE provider_sub = ? OR email = ?
            """,
            (google_sub, email),
        ).fetchone()

        if user and user["provider"] == "local" and not user["provider_sub"]:
            raise HTTPException(
                status_code=409,
                detail="Account exists with password. Log in and link Google.",
            )

        if user:
            username = user["username"] or ensure_unique_username(conn, base_username_from_email(email))
            conn.execute(
                """
                UPDATE users
                SET provider = 'google',
                    provider_sub = ?,
                    name = ?,
                    username = ?,
                    avatar_url = ?
                WHERE id = ?
                """,
                (google_sub, name, username, avatar_url, user["id"]),
            )
            user_id = user["id"]
        else:
            username = ensure_unique_username(conn, base_username_from_email(email))
            cursor = conn.execute(
                """
                INSERT INTO users (email, provider, provider_sub, name, username, avatar_url)
                VALUES (?, 'google', ?, ?, ?, ?)
                """,
                (email, google_sub, name, username, avatar_url),
            )
            user_id = cursor.lastrowid

        token = create_session(conn, user_id)

    response = RedirectResponse(url=FRONTEND_REDIRECT_URL)
    response.set_cookie(SESSION_COOKIE_NAME, token, **cookie_settings())
    return response


@app.post("/api/auth/google/link/start")
def google_link_start(request: Request) -> RedirectResponse:
    require_google_config()
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated.")

    with get_db() as conn:
        user = get_user_by_session(conn, token)
        if not user:
            raise HTTPException(status_code=401, detail="Not authenticated.")
        cleanup_oauth_states(conn)
        state = create_oauth_state(conn, "link", user["id"])

    url = build_google_auth_url(state, prompt="consent")
    return RedirectResponse(url=url)


@app.get("/api/auth/google/link/callback")
def google_link_callback(code: Optional[str] = None, state: Optional[str] = None, request: Request = None) -> Response:
    require_google_config()
    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing code or state.")

    token = request.cookies.get(SESSION_COOKIE_NAME) if request else None
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated.")

    with get_db() as conn:
        cleanup_oauth_states(conn)
        state_row = pop_oauth_state(conn, state)
        if not state_row:
            raise HTTPException(status_code=400, detail="Invalid or expired OAuth state.")
        if state_row["purpose"] != "link":
            raise HTTPException(status_code=400, detail="OAuth state mismatch.")
        user = get_user_by_session(conn, token)
        if not user or user["id"] != state_row["user_id"]:
            raise HTTPException(status_code=401, detail="Not authenticated.")

    try:
        token_data = exchange_google_token(code)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Failed to exchange Google token.") from exc

    access_token = token_data.get("access_token")
    if not access_token:
        raise HTTPException(status_code=400, detail="Google token response missing access token.")

    try:
        profile = fetch_google_profile(access_token)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Failed to fetch Google profile.") from exc

    email = (profile.get("email") or "").lower()
    name = profile.get("name") or "Pixelfit User"
    google_sub = profile.get("sub")
    avatar_url = profile.get("picture")

    if not email or not google_sub:
        raise HTTPException(status_code=400, detail="Google profile missing required fields.")

    with get_db() as conn:
        conflict = conn.execute(
            "SELECT id FROM users WHERE provider_sub = ? AND id != ?",
            (google_sub, user["id"]),
        ).fetchone()
        if conflict:
            raise HTTPException(status_code=409, detail="Google account already linked.")

        username = user["username"] or ensure_unique_username(conn, base_username_from_email(email))
        conn.execute(
            """
            UPDATE users
            SET provider = 'google',
                provider_sub = ?,
                name = ?,
                username = ?,
                avatar_url = ?
            WHERE id = ?
            """,
            (google_sub, name, username, avatar_url, user["id"]),
        )

    response = RedirectResponse(url=FRONTEND_REDIRECT_URL)
    response.set_cookie(SESSION_COOKIE_NAME, token, **cookie_settings())
    return response


@app.get("/api/me")
def me(request: Request) -> JSONResponse:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated.")

    with get_db() as conn:
        user = get_user_by_session(conn, token)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid session.")

    return JSONResponse(
        {
            "status": "ok",
            "user": {
                "id": user["id"],
                "name": user["name"],
                "username": user["username"],
                "gender": user["gender"],
                "email": user["email"],
                "provider": user["provider"],
                "avatar_url": user["avatar_url"],
            },
        }
    )


@app.post("/api/logout")
def logout(request: Request) -> JSONResponse:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token:
        with get_db() as conn:
            delete_session(conn, token)
    response = JSONResponse({"status": "ok"})
    response.delete_cookie(SESSION_COOKIE_NAME)
    return response


@app.post("/api/username")
def update_username(payload: UsernameRequest, request: Request) -> JSONResponse:
    username = payload.username.strip()
    if not username:
        raise HTTPException(status_code=400, detail="Username is required.")

    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated.")

    with get_db() as conn:
        user = get_user_by_session(conn, token)
        if not user:
            raise HTTPException(status_code=401, detail="Not authenticated.")
        if conn.execute(
            "SELECT id FROM users WHERE username = ? AND id != ?",
            (username, user["id"]),
        ).fetchone():
            raise HTTPException(status_code=400, detail="That username is already taken.")
        conn.execute("UPDATE users SET username = ? WHERE id = ?", (username, user["id"]))

    return JSONResponse({"status": "ok", "username": username})


# Run with: uvicorn App:app --reload
