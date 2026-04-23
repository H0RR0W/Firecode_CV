import bcrypt
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from fastapi import Request
from config import SECRET_KEY, SESSION_MAX_AGE
from database import get_user_by_id

_serializer = URLSafeTimedSerializer(SECRET_KEY)
_csrf_serializer = URLSafeTimedSerializer(SECRET_KEY, salt="csrf")


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def create_session(user_id: int, role: str) -> str:
    return _serializer.dumps({"user_id": user_id, "role": role})


def verify_session(token: str) -> dict | None:
    try:
        return _serializer.loads(token, max_age=SESSION_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None


def get_current_user(request: Request) -> dict | None:
    token = request.cookies.get("session")
    if not token:
        return None
    data = verify_session(token)
    if not data:
        return None
    return get_user_by_id(data["user_id"])


def generate_csrf_token() -> str:
    return _csrf_serializer.dumps("csrf")


def verify_csrf_token(token: str) -> bool:
    try:
        _csrf_serializer.loads(token, max_age=3600)
        return True
    except Exception:
        return False
