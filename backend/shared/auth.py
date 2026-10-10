"""
CitySync ΓÇö Role-based access control via Python decorators.
Replaces OPA for hackathon ΓÇö readable, zero setup.
"""
import functools
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from shared.config import settings
from passlib.context import CryptContext

security = HTTPBearer(auto_error=False)
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)


# ── Role hierarchy ──────────────────────────────────────────────────────────────
ROLE_HIERARCHY = {
    "citizen": 0,
    "field_worker": 1,
    "officer": 2,
    "supervisor": 3,
    "admin": 4,
    "commissioner": 5,
}

# Category → municipal department code (must match seed_data.CATEGORY_DEPARTMENT_MAP)
CATEGORY_TO_DEPT = {
    "Pothole": "ROADS",
    "Flooding": "SWD",
    "Drainage": "SWD",
    "Street Light": "LIGHTS",
    "Garbage": "SWM",
    "Water Supply": "HYD",
    "Building Hazard": "BLDG",
    "Live Wire": "ELEC_EMG",
    "Noise": "ROADS",
    "Fire Hazard": "FIRE",
    "Smoke": "FIRE",
    "Gas Leak": "FIRE",
    "Other": "ROADS",
}


def categories_for_department(dept_code: str) -> list[str]:
    """Return complaint categories visible to a department-scoped officer."""
    return [c for c, d in CATEGORY_TO_DEPT.items() if d == dept_code]


def department_categories_filter(user: dict) -> list[str] | None:
    """
    If the JWT carries dept_code, return allowed categories for that department.
    None means no extra filter (global admin / citizen).
    """
    role = user.get("role", "public")
    code = user.get("dept_code")
    
    # If no department code is provided, global roles see everything
    if not code:
        return None
        
    # Citizens can't be restricted by department (they report everything)
    if role == "citizen":
        return None
        
    # Officers and specific Department Admins are restricted
    cats = categories_for_department(code)
    return cats if cats else None


# ── Token creation ──────────────────────────────────────────────────────────────
def create_token(subject: str, role: str = "citizen", extra: dict | None = None) -> str:
    """Create a JWT token for a user."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expire_minutes),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


# ── Token parsing ──────────────────────────────────────────────────────────────
def decode_token(token: str) -> dict:
    """Decode and validate a JWT. Raises HTTPException on failure."""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        return payload
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired token: {e}",
        )


# ── FastAPI dependencies ───────────────────────────────────────────────────────
async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> dict:
    """
    FastAPI dependency — extracts caller identity.
    Returns a dict with 'sub' (user_id) and 'role'.
    Allows unauthenticated access but marks role as 'public'.
    """
    if not credentials:
        return {"sub": "anonymous", "role": "public"}
    
    payload = decode_token(credentials.credentials)
    
    # Optional: We could fetch the full User object here and return it
    # For now, we return the payload dict to maintain compatibility with decorators
    return payload


def require_role(minimum_role: str):
    """
    Decorator factory — enforces minimum role on a FastAPI route.
    """
    min_level = ROLE_HIERARCHY.get(minimum_role, 99)

    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            user = kwargs.get("user") or kwargs.get("current_user")
            if not user or user.get("role") == "public":
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication required",
                )
            caller_role = user.get("role", "public")
            caller_level = ROLE_HIERARCHY.get(caller_role, -1)
            if caller_level < min_level:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Role '{minimum_role}' or higher required",
                )
            return await func(*args, **kwargs)
        return wrapper
    return decorator


# ── Field-level response filtering ──────────────────────────────────────────────
def filter_ticket_fields(ticket_dict: dict, role: str) -> dict:
    from shared.privacy import fuzz_for_role
    filtered = dict(ticket_dict)
    filtered.pop("citizen_token", None)

    raw_lat = filtered.pop("raw_lat", None)
    raw_lng = filtered.pop("raw_lng", None)

    if raw_lat and raw_lng:
        fuzzed_lat, fuzzed_lng = fuzz_for_role(raw_lat, raw_lng, role)
        filtered["location"] = {
            "lat": round(fuzzed_lat, 5),
            "lng": round(fuzzed_lng, 5),
            "fuzz_level": role,
        }

    if role == "public":
        filtered.pop("description", None)
        filtered.pop("image_key", None)
        filtered.pop("assigned_worker_id", None)
        filtered.pop("assigned_worker_label", None)

    return filtered


# ── Demo Infrastructure (Cleanup Pending) ──────────────────────────────────────
# Note: Production should use the /api/auth/signup/login endpoints.
# These remain to support existing demo frontend logic during migration.
DEMO_TOKENS = {
    "officer": create_token(
        "officer_demo_001", role="officer", extra={"name": "Officer Smith", "dept_code": "GENERAL"}
    ),
    "admin": create_token(
        "admin_demo_001", role="admin", extra={"name": "Admin Root"}
    ),
    "dept_swd": create_token(
        "dept_officer_swd_demo", role="officer", extra={"dept_code": "SWD", "dept_name": "Stormwater Dept"}
    ),
    "dept_roads": create_token(
        "dept_officer_roads_demo", role="officer", extra={"dept_code": "ROADS", "dept_name": "Roads & Infrastructure"}
    ),
    "dept_fire": create_token(
        "dept_officer_fire_demo", role="officer", extra={"dept_code": "FIRE", "dept_name": "Fire Department"}
    ),
}

# Dispatch roster ΓÇö `worker_id` matches JWT `sub` for each demo field worker token
FIELD_WORKERS = [
    {"worker_id": "crew_fire_1", "display_name": "Fire Crew 1 - Fort Station"},
    {"worker_id": "crew_swd_1", "display_name": "SWD Drainage Crew Alpha"},
    {"worker_id": "crew_roads_1", "display_name": "Roads Asphalt Crew"},
    {"worker_id": "crew_sanitation_1", "display_name": "Sanitation Cleanup Crew"},
    {"worker_id": "crew_police_1", "display_name": "Police Patrol Unit 7"},
    {"worker_id": "crew_general_1", "display_name": "General Field Crew Beta"},
]


def field_worker_label(worker_id: str | None) -> str | None:
    if not worker_id:
        return None
    for w in FIELD_WORKERS:
        if w["worker_id"] == worker_id:
            return w["display_name"]
    return worker_id
