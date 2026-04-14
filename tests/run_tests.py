#!/usr/bin/env python3
"""
localthink-mcp full test suite.
Measures: input chars (stock cost), output chars (tool cost), compression ratio.
Runs every tool against a realistic fixture and prints a compact results table.
"""
import sys, os, time, json, tempfile, shutil, textwrap

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'localthink_mcp'))

from server import (
    local_summarize, local_extract, local_answer,
    local_shrink_file, local_diff, local_diff_files,
    local_batch_answer, local_pipeline, local_auto,
    local_chat, local_grep_semantic, local_scan_dir,
    local_code_surface, local_classify, local_outline,
    local_audit, local_models,
    local_compress_log, local_compress_stack_trace,
    local_compress_data, local_session_compress,
    local_prompt_compress, local_symbols, local_find_impl,
    local_strip_to_skeleton, local_translate,
    local_schema_infer, local_timeline,
)

# ── Fixtures ──────────────────────────────────────────────────────────────

PY_CODE = '''\
"""User authentication module — handles registration, login, token issuance."""
import hashlib, hmac, secrets, time, json
from typing import Optional, Dict, List
from dataclasses import dataclass, field

SECRET_KEY = "change-me-in-production"
TOKEN_TTL  = 3600
MAX_ATTEMPTS = 5

@dataclass
class User:
    """Represents a registered user with hashed credentials."""
    id: int
    email: str
    password_hash: str
    created_at: float = field(default_factory=time.time)
    last_login: Optional[float] = None
    attempts: int = 0
    active: bool = True

    def check_password(self, password: str) -> bool:
        """Constant-time PBKDF2 check. Returns True if password matches."""
        salt = self.password_hash[:32]
        expected = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000)
        return hmac.compare_digest(self.password_hash[32:], expected.hex())

    def is_locked(self) -> bool:
        """Return True when failed attempts exceed MAX_ATTEMPTS."""
        return self.attempts >= MAX_ATTEMPTS

    def record_success(self) -> None:
        """Reset counter and stamp last_login on successful auth."""
        self.attempts = 0
        self.last_login = time.time()

    def record_failure(self) -> None:
        self.attempts += 1

    def to_public_dict(self) -> dict:
        """Serialise without sensitive fields."""
        return {"id": self.id, "email": self.email,
                "created_at": self.created_at, "active": self.active}


class UserStore:
    """In-memory user store keyed by id and email."""

    def __init__(self) -> None:
        self._users: Dict[int, User] = {}
        self._email_idx: Dict[str, int] = {}
        self._next_id = 1

    def create(self, email: str, password: str) -> User:
        """Hash password and persist new user. Raises ValueError on duplicate email."""
        if email in self._email_idx:
            raise ValueError(f"email already registered: {email}")
        salt = secrets.token_hex(16)
        pw_hash = salt + hashlib.pbkdf2_hmac(
            "sha256", password.encode(), salt.encode(), 100_000).hex()
        user = User(id=self._next_id, email=email, password_hash=pw_hash)
        self._users[self._next_id] = user
        self._email_idx[email] = self._next_id
        self._next_id += 1
        return user

    def by_email(self, email: str) -> Optional[User]:
        uid = self._email_idx.get(email)
        return self._users.get(uid) if uid else None

    def by_id(self, uid: int) -> Optional[User]:
        return self._users.get(uid)

    def delete(self, uid: int) -> bool:
        """Remove user by id. Returns False if not found."""
        user = self._users.pop(uid, None)
        if user:
            self._email_idx.pop(user.email, None)
            return True
        return False

    def all_users(self) -> List[User]:
        return sorted(self._users.values(), key=lambda u: u.created_at)


class TokenManager:
    """HMAC-SHA256 signed bearer tokens with revocation list."""

    def __init__(self, secret: str = SECRET_KEY, ttl: int = TOKEN_TTL) -> None:
        self._secret = secret
        self._ttl = ttl
        self._revoked: set = set()

    def issue(self, user_id: int) -> str:
        """Sign and return a new bearer token for user_id."""
        import base64
        payload = base64.urlsafe_b64encode(
            json.dumps({"uid": user_id, "exp": time.time() + self._ttl}).encode()
        ).decode()
        sig = hmac.new(self._secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
        return f"{payload}.{sig}"

    def verify(self, token: str) -> Optional[int]:
        """Return user_id if token is valid, unexpired, and not revoked. Else None."""
        import base64
        try:
            payload, sig = token.rsplit(".", 1)
            expected = hmac.new(
                self._secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(sig, expected) or token in self._revoked:
                return None
            data = json.loads(base64.urlsafe_b64decode(payload + "=="))
            return data["uid"] if data["exp"] >= time.time() else None
        except Exception:
            return None

    def revoke(self, token: str) -> None:
        self._revoked.add(token)


def login(store: UserStore, tokens: TokenManager,
          email: str, password: str) -> Optional[str]:
    """
    Authenticate user by email/password. Returns bearer token on success.
    Increments failure counter and raises RuntimeError when locked.
    """
    user = store.by_email(email)
    if not user or not user.active:
        return None
    if user.is_locked():
        raise RuntimeError(f"account locked after {MAX_ATTEMPTS} failed attempts: {email}")
    if not user.check_password(password):
        user.record_failure()
        return None
    user.record_success()
    return tokens.issue(user.id)
'''

LOG_DATA = "\n".join([
    *[f"2026-04-13 14:{i//60:02d}:{i%60:02d} INFO  [http] GET /api/health 200 2ms req={i}" for i in range(60)],
    *[f"2026-04-13 14:02:{i:02d} WARN  [db] pool {70+i}% full - consider scaling" for i in range(20)],
    *[f"2026-04-13 14:03:{i:02d} ERROR [db] connection refused: 10.0.0.5:5432 (attempt {(i%3)+1}/3)" for i in range(30)],
    "2026-04-13 14:04:00 ERROR [db] max retries exceeded, circuit breaker OPEN",
    "2026-04-13 14:04:01 ERROR [app] nil pointer dereference in handler.go:142",
    "2026-04-13 14:04:02 ERROR [app] panic: runtime error: index out of range [0] with length 0",
    *[f"2026-04-13 14:05:{i:02d} INFO  [http] POST /api/login 200 18ms req={i+200}" for i in range(30)],
    "2026-04-13 14:06:00 INFO  [app] SIGTERM received — draining connections",
    "2026-04-13 14:06:02 INFO  [app] shutdown complete",
])

JSON_DATA = json.dumps({
    "data": [
        {
            "id": f"usr_{i:05d}", "email": f"user{i}@example.com",
            "first_name": f"First{i}", "last_name": f"Last{i}",
            "phone": None, "avatar": None, "bio": None, "website": None,
            "role": ["user","admin","mod"][i%3],
            "active": True, "verified": i%4 != 0,
            "created_at": f"2025-{(i%12)+1:02d}-01T00:00:00Z",
            "last_login": f"2026-04-{(i%13)+1:02d}T08:00:00Z",
            "address": {"street": f"{i} Main St","city":"Springfield","state":"IL","zip":"62701","country":"US"},
            "prefs": {"theme":"dark","lang":"en","notifications":True,"newsletter":False},
            "stats": {"logins": i*5, "posts": i*2},
            "meta": {"ip": f"10.0.{i%256}.1", "ua": "Mozilla/5.0 Chrome/120"},
        }
        for i in range(30)
    ],
    "total": 30, "page": 1, "per_page": 30
}, indent=2)

DOCS = """\
# Auth API Reference

## Overview
JWT-lite bearer tokens. Base URL: https://api.example.com/v2.
All requests need Content-Type: application/json.
Authenticated requests need Authorization: Bearer <token>.

## Rate limits
- Unauthenticated: 100 req/min per IP
- Authenticated: 1000 req/min per token
Headers: X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Reset.

## POST /auth/register
Create account.
Body: { "email": "...", "password": "12+ chars", "first_name": "...", "last_name": "..." }
Rules: valid email, not taken; password min 12 chars, 1 upper/lower/digit.
201: { "id": "usr_001", "email": "...", "created_at": "..." }
400: validation error with field name. 409: email taken.

## POST /auth/login
Authenticate. Returns token.
Body: { "email": "...", "password": "..." }
200: { "token": "...", "expires_at": "...", "user": {...} }
401: bad credentials (email/password indistinguishable for security). 423: account locked.

## GET /auth/me
Requires Authorization header.
200: { "id", "email", "first_name", "last_name", "role", "created_at", "last_login" }
401: bad/expired/revoked token. 403: account deactivated.

## POST /auth/logout
Requires Authorization header. Revokes token.
204: success.

## POST /auth/refresh
Exchange valid token for new one (fresh TTL).
200: { "token": "...", "expires_at": "..." }
401: token expired or revoked.

## Error format
{ "error": "human message", "code": "MACHINE_CODE", "request_id": "req-abc" }
Codes: INVALID_CREDENTIALS, ACCOUNT_LOCKED, TOKEN_EXPIRED, TOKEN_REVOKED,
EMAIL_TAKEN, VALIDATION_ERROR, RATE_LIMITED.

## Security
- PBKDF2-HMAC-SHA256, 100k iterations, 16-byte random salt.
- Login errors are identical for unknown email vs wrong password (prevents enumeration).
- Token revocation via bloom-filter deny list (no DB lookup on every request).
- All token comparisons are constant-time (hmac.compare_digest).
""" * 2

STACK = """\
Traceback (most recent call last):
  File "/app/server.py", line 142, in handle_request
    response = router.dispatch(request)
  File "/app/router.py", line 89, in dispatch
    return self._routes[request.method][request.path](request)
  File "/app/handlers/user.py", line 67, in get_user
    user = db.query(User).filter_by(id=user_id).one()
  File "/venv/lib/python3.12/site-packages/sqlalchemy/orm/query.py", line 2667, in one
    raise NoResultFound("No row was found when one was required")
sqlalchemy.exc.NoResultFound: No row was found when one was required

During handling of the above exception, another exception occurred:

Traceback (most recent call last):
  File "/app/handlers/user.py", line 72, in get_user
    raise HTTPException(500, f"lookup failed: {e}")
app.exceptions.HTTPException: 500 Internal Server Error

Source (user.py lines 60-74):
    60:  @require_auth
    61:  def get_user(request):
    62:      user_id = int(request.path_params["id"])
    63:      try:
    64:          db = get_db_session()
    65:          user = db.query(User).filter_by(id=user_id).one()
    66:          return JSONResponse(user.to_dict())
    67:      except NoResultFound as e:
    68:          # BUG: should be 404, not 500
    69:          raise HTTPException(500, f"lookup failed: {e}")
    70:      finally:
    71:          db.close()
"""

PROMPT_BLOAT = """\
## Style Rules
- Be concise. Responses should be short.
- Keep all responses brief and to the point.
- Do not pad responses. Short is better.
- Avoid verbose language. Be direct.
- Never repeat yourself in a response.
- Prefer short answers over long ones.

## Code Rules
- Use Python 3.10+ type hints on all functions.
- Always annotate parameters and return types with type hints.
- Write type annotations. Use Python 3.10+ syntax.
- Follow PEP 8. Use 4-space indentation.
- PEP 8 style. 4 spaces for indentation.
- Two blank lines between top-level definitions.
- Put imports at the top. Use absolute imports.
- Absolute imports only, at top of file.

## Testing Rules
- Write pytest tests for all new functions.
- Every function needs a test. Use pytest.
- Tests go in tests/. Files named test_<module>.py.
- Use pytest. Tests in tests/ directory. Name: test_<module>.py.

## Git Rules
- Write descriptive commit messages in present tense.
- Commit messages: present tense, descriptive.
- One change per commit. Use feature branches.
- Never commit to main. Use PRs. One logical change per commit.

## Security Rules
- No hardcoded credentials. Use env vars for secrets.
- Validate all user input. Never trust user data.
- Secrets from environment variables only. Validate inputs always.
"""

SESSION_TRANSCRIPT = """\
[Day 1 - Morning]
User: Build a data pipeline: CSV files arrive in S3, transform them, load into PostgreSQL.
Claude: Three modules: s3_reader.py (boto3 streaming), transformer.py, db_loader.py (psycopg2).
[writes s3_reader.py - boto3 get_object, streaming csv.reader, yields rows without full load]

User: Files can be 2GB. Must stream, no full loads.
Claude: s3_reader already streams via boto3 Body stream + csv.reader wrapper. Memory constant ~1MB.

User: Add schema validation before transform.
Claude: Added schema_validator.py with pydantic BaseModel. Invalid rows -> error.csv with row/reason.

[Day 1 - Afternoon]
User: Transformer must: normalize phone numbers (E.164), split full_name to first/last, ISO8601 dates.
Claude: transformer.py: phonenumbers lib for E.164, name split handles "First Last"/"Last, First",
       dateutil.parser for flexible date parse -> isoformat(). All in Transformer.apply_row(row).

User: Date parsing fails on ambiguous dates like 04/05/06.
Claude: Added TransformConfig.date_dayfirst=False, date_yearfirst=False. Passed to dateutil. Documented.

User: Add deduplication by record_id.
Claude: db_loader.py: INSERT ... ON CONFLICT (record_id) DO UPDATE (upsert). Reports inserted/updated.

[Day 2 - Morning]
User: Production crash after 6 hours: psycopg2.OperationalError: SSL connection closed unexpectedly
Claude: Root cause: idle connection timeout on DB side. Fix: reconnect factory with exponential backoff
       (1s, 2s, 4s, max 30s). Added TCP keepalive params to psycopg2 connection string.

User: UnicodeDecodeError: utf-8 codec can't decode byte 0x92 on some files.
Claude: Added chardet.detect() on first 4KB. Falls back to latin-1 if confidence < 0.9.
       Added --force-encoding CLI flag for manual override.

User: Write tests.
Claude: tests/: test_transformer.py (20 cases), test_validator.py (15 cases),
       test_loader.py (integration, needs real PG). All pass with pytest.

[Day 2 - Afternoon]
User: Deploy to AWS Lambda triggered by S3 events.
Claude: Lambda limits: 15min/10GB. 2GB at 10MB/s = 3.4min, OK. Cold start with psycopg2 layer 4-8s.
       Recommend Lambda + RDS Proxy for connection pooling. Added lambda_handler.py. All config via env.

User: Cost estimate? 500 files/day average, peaks 2000/day.
Claude: 500 * 3.4min * 512MB = ~$0.07/day avg, ~$0.30/day peak. Add SQS dead-letter for failed files
       and CloudWatch alarm on error.csv growth rate.

[Current state]
Files: s3_reader.py, transformer.py, schema_validator.py, db_loader.py, cli.py, lambda_handler.py.
Tests: 35 passing. Open: dead-letter queue (user undecided), RDS Proxy setup (not started).
Constraints: streaming only, latin-1 fallback, E.164 phones, upsert on record_id.
"""

# ── Test harness ──────────────────────────────────────────────────────────

PASS = "PASS"
FAIL = "FAIL"
SKIP = "SKIP"

results = []  # (tool_name, status, in_chars, out_chars, ratio, note)

def tok(n): return n // 4  # rough token estimate

def run(name, fn, in_size, correctness_check=None, *args, **kwargs):
    t0 = time.time()
    try:
        out = fn(*args, **kwargs)
        elapsed = time.time() - t0
        if out.startswith("[localthink]"):
            results.append((name, FAIL, in_size, 0, 0.0, out[:60]))
            return out
        ok = PASS
        note = ""
        if correctness_check:
            check_result = correctness_check(out)
            if check_result is not True:
                ok = FAIL
                note = f"missing: {check_result}"
        ratio = len(out) / in_size if in_size else 1.0
        results.append((name, ok, in_size, len(out), ratio, f"{elapsed:.1f}s  {note}"))
        return out
    except Exception as e:
        results.append((name, FAIL, in_size, 0, 0.0, str(e)[:60]))
        return ""

# ── Create temp dir for file-based tools ─────────────────────────────────

tmpdir = tempfile.mkdtemp(prefix="localthink_test_")
try:
    py_file     = os.path.join(tmpdir, "auth.py")
    log_file    = os.path.join(tmpdir, "app.log")
    docs_file   = os.path.join(tmpdir, "api_docs.md")
    session_file= os.path.join(tmpdir, "session.txt")
    prompt_file = os.path.join(tmpdir, "CLAUDE.md")
    py_file_v2  = os.path.join(tmpdir, "auth_v2.py")
    extra_py    = os.path.join(tmpdir, "models.py")

    open(py_file,     "w").write(PY_CODE)
    open(log_file,    "w").write(LOG_DATA)
    open(docs_file,   "w").write(DOCS)
    open(session_file,"w", encoding="utf-8").write(SESSION_TRANSCRIPT)
    open(prompt_file, "w").write(PROMPT_BLOAT)
    open(extra_py,    "w").write("class Foo:\n    def bar(self): pass\n")
    # v2 of auth — add rate limiting
    open(py_file_v2,  "w").write(PY_CODE.replace(
        "MAX_ATTEMPTS = 5",
        "MAX_ATTEMPTS = 10\nRATE_LIMIT_WINDOW = 60  # seconds\nRATE_LIMIT_MAX = 100"
    ).replace(
        "def record_failure(self) -> None:",
        "def record_failure(self, ip: str = '') -> None:"
    ))

    # ── Run every tool ────────────────────────────────────────────────────

    print("Running 29 tools against realistic fixtures...\n")

    # ── v0.1.0 core ──────────────────────────────────────────────────────
    run("local_summarize", local_summarize,
        len(DOCS),
        lambda o: True if "POST" in o or "token" in o.lower() else "auth endpoint info",
        text=DOCS, focus="API endpoints and error codes")

    run("local_extract", local_extract,
        len(DOCS),
        lambda o: True if "rate" in o.lower() or "limit" in o.lower() else "rate limiting info",
        text=DOCS, query="rate limiting headers and limits")

    run("local_answer", local_answer,
        len(PY_CODE),
        lambda o: True if "locked" in o.lower() or "attempt" in o.lower() else "account lock info",
        file_path=py_file, question="How does account locking work and what is the limit?")

    # ── v1.1 file ops ─────────────────────────────────────────────────────
    run("local_shrink_file", local_shrink_file,
        len(PY_CODE),
        lambda o: True if "Token" in o or "User" in o or "login" in o.lower() else "class/auth info",
        file_path=py_file)

    run("local_diff", local_diff,
        len(PY_CODE) * 2,
        lambda o: True if "MAX_ATTEMPTS" in o or "10" in o or "rate" in o.lower() else "change info",
        before=PY_CODE, after=open(py_file_v2).read(), focus="config changes")

    run("local_batch_answer", local_batch_answer,
        len(PY_CODE) + len("class Foo:\n    def bar(self): pass\n"),
        lambda o: True if "auth.py" in o or "models.py" in o else "per-file answers",
        file_paths=[py_file, extra_py], question="What is the primary class defined?")

    pipeline_out = run("local_pipeline", local_pipeline,
        len(DOCS),
        lambda o: True if len(o) < len(DOCS) * 0.5 else "should be shorter than full doc",
        text=DOCS,
        steps=[{"op": "extract", "query": "authentication endpoints"},
               {"op": "summarize", "focus": "request/response format"}])

    run("local_auto", local_auto,
        len(PY_CODE),
        lambda o: True if "locked" in o.lower() or "attempt" in o.lower() else "answer about locking",
        input=py_file, question="what happens after too many failed logins?")

    # Turn 1: doc is compressed on first call (upfront cost, needed once)
    chat_r = run("local_chat_t1", local_chat,
        len(DOCS),
        lambda o: True if "token" in o.lower() or "bearer" in o.lower() else "token info in answer",
        document=DOCS, message="What header do I need to send with authenticated requests?", history="")
    # Turn 2: reuses compressed doc — stock would reload full DOCS, we use compressed version
    try:
        r1 = json.loads(chat_r) if chat_r else {}
        chat_r = run("local_chat_t2", local_chat,
            len(DOCS),  # stock cost: would reload full DOCS again
            lambda o: True if "rate" in o.lower() or "limit" in o.lower() else "rate limit info",
            document=r1.get("doc", DOCS),
            message="What are the rate limits for authenticated requests?",
            history=r1.get("history", ""))
    except Exception as e:
        results.append(("local_chat_t2", FAIL, len(DOCS), 0, 0.0, str(e)[:60]))

    run("local_grep_semantic", local_grep_semantic,
        len(PY_CODE),
        lambda o: True if "attempt" in o.lower() or "lock" in o.lower() else "lock/attempt lines",
        file_path=py_file, meaning="where failed login attempts are counted and accounts locked",
        max_results=3)

    run("local_scan_dir", local_scan_dir,
        len(PY_CODE) + len("class Foo:\n    def bar(self): pass\n"),
        lambda o: True if "auth.py" in o or "models.py" in o else "per-file summaries",
        dir_path=tmpdir, pattern="*.py")

    run("local_code_surface", local_code_surface,
        len(PY_CODE),
        lambda o: True if "def login" in o and "def check_password" in o else "login/check_password sigs",
        file_path=py_file)

    run("local_classify", local_classify,
        len(PY_CODE),
        lambda o: True if "code" in o.lower() or "python" in o.lower() else "should identify as code",
        text=PY_CODE[:2000])

    run("local_outline", local_outline,
        len(DOCS),
        lambda o: True if "Overview" in o or "register" in o.lower() or "login" in o.lower() else "section headers",
        text=DOCS)

    run("local_audit", local_audit,
        len(PY_CODE),
        lambda o: True if "PASS" in o or "FAIL" in o or "PARTIAL" in o else "audit results",
        file_path=py_file,
        checklist=["no hardcoded credentials", "password hashing present",
                   "input validation on user-supplied values", "no SQL injection risk"])

    # local_models is a utility tool (replaces `ollama list` CLI call) — not a compression tool.
    # "in_size" here represents the overhead of an equivalent shell command (~100 chars output).
    # Ratio > 1 is expected and correct: we're fetching info, not compressing it.
    run("local_models", local_models,
        100,  # stock baseline: ~100 chars from `ollama list` CLI output
        lambda o: True if "qwen" in o.lower() else "should list qwen model",
        )

    # ── v1.1 expansion ────────────────────────────────────────────────────
    run("local_compress_log", local_compress_log,
        len(LOG_DATA),
        lambda o: True if "error" in o.lower() and len(o) < len(LOG_DATA) * 0.3 else "compressed with errors",
        file_path=log_file)

    run("local_compress_stack_trace", local_compress_stack_trace,
        len(STACK),
        lambda o: True if ("404" in o or "500" in o or "NoResultFound" in o) else "error info",
        text=STACK)

    run("local_compress_data", local_compress_data,
        len(JSON_DATA),
        lambda o: True if len(o) < len(JSON_DATA) * 0.3 else "should compress significantly",
        data=JSON_DATA, question="How many users are there?")

    run("local_session_compress", local_session_compress,
        len(SESSION_TRANSCRIPT),
        lambda o: True if "cli" in o.lower() or "log" in o.lower() else "session context",
        file_path=session_file)

    run("local_prompt_compress", local_prompt_compress,
        len(PROMPT_BLOAT),
        lambda o: True if len(o) < len(PROMPT_BLOAT) * 0.6 else "should remove duplicates",
        text=PROMPT_BLOAT)

    run("local_symbols", local_symbols,
        len(PY_CODE),
        lambda o: True if "login" in o and ("42" in o or "line" in o.lower()) else "symbols with lines",
        file_path=py_file)

    run("local_find_impl", local_find_impl,
        len(PY_CODE),
        lambda o: True if "check_password" in o or "pbkdf2" in o.lower() else "password check code",
        file_path=py_file, spec="the function that verifies a user's password")

    run("local_strip_to_skeleton", local_strip_to_skeleton,
        len(PY_CODE),
        lambda o: True if "..." in o and "def login" in o else "skeleton with ellipsis",
        file_path=py_file)

    _translate_json = json.dumps({
        "server": {"host": "0.0.0.0", "port": 8080, "workers": 4, "debug": False},
        "database": {"url": "postgresql://user:pass@localhost:5432/mydb",
                     "pool_size": 10, "max_overflow": 5, "echo": False,
                     "connect_timeout": 30, "statement_timeout": 60000},
        "redis": {"url": "redis://localhost:6379/0", "ttl": 3600, "prefix": "app:"},
        "auth": {"secret_key": "change-me", "algorithm": "HS256",
                 "token_expire": 86400, "refresh_expire": 604800},
        "logging": {"level": "INFO", "format": "json", "output": "stdout", "file": None},
        "features": {"rate_limiting": True, "caching": True, "metrics": True, "tracing": False},
        "cors": {"origins": ["https://app.example.com", "https://admin.example.com"],
                 "methods": ["GET", "POST", "PUT", "DELETE"], "allow_credentials": True},
    }, indent=2)
    run("local_translate", local_translate,
        len(_translate_json),
        lambda o: True if "server:" in o or "database:" in o else "yaml output with keys",
        text=_translate_json,
        target_format="yaml")

    run("local_schema_infer", local_schema_infer,
        len(JSON_DATA),
        lambda o: True if "string" in o.lower() or "type" in o.lower() else "type info in schema",
        data=JSON_DATA[:3000])

    run("local_timeline", local_timeline,
        len(LOG_DATA),
        lambda o: True if "ERROR" in o or "shutdown" in o.lower() or "14:" in o else "events extracted",
        text=LOG_DATA)

    run("local_diff_files", local_diff_files,
        len(PY_CODE) * 2,
        lambda o: True if "MAX_ATTEMPTS" in o or "rate" in o.lower() or "10" in o else "diff details",
        path_a=py_file, path_b=py_file_v2)

finally:
    shutil.rmtree(tmpdir, ignore_errors=True)

# ── Print results ─────────────────────────────────────────────────────────

W = 26
print(f"\n{'Tool':<{W}} {'Status':<6} {'In':>6} {'Out':>6} {'Ratio':>6}  {'Time / Note'}")
print("-" * 78)
total_in = total_out = pass_count = fail_count = 0
for name, status, in_chars, out_chars, ratio, note in results:
    star = " <-- WORSE" if ratio > 1.0 else ""
    ratio_s = f"{ratio:.2f}x" if ratio > 0 else "  N/A"
    in_tok  = f"~{tok(in_chars)}t" if in_chars else "   -"
    out_tok = f"~{tok(out_chars)}t" if out_chars else "   -"
    print(f"{name:<{W}} {status:<6} {in_tok:>6} {out_tok:>6} {ratio_s:>6}  {note}{star}")
    total_in  += in_chars
    total_out += out_chars
    pass_count += status == PASS
    fail_count += status == FAIL

print("-" * 78)
overall_ratio = total_out / total_in if total_in else 0
print(f"\nPASS: {pass_count}/{len(results)}   FAIL: {fail_count}/{len(results)}")
print(f"Aggregate  in: ~{tok(total_in):,}t  out: ~{tok(total_out):,}t  ratio: {overall_ratio:.2f}x")
print(f"Tokens saved across all tests: ~{tok(total_in - total_out):,}")
