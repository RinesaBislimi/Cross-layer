
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..models.user import User
from ..services.auth_service import authenticate_user, create_access_token, decode_token, hash_password

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token", auto_error=False)

class RegisterPayload(BaseModel):
    email:     str
    password:  str
    full_name: str = ""

class LoginPayload(BaseModel):
    email:    str
    password: str

class UserOut(BaseModel):
    id:         int
    email:      str
    full_name:  str
    role:       str
    is_active:  bool
    created_at: str

class TokenResponse(BaseModel):
    access_token: str
    token_type:   str = "bearer"
    user:         UserOut

class ChangePasswordPayload(BaseModel):
    old_password: str
    new_password: str

def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    cfg = get_settings()
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = decode_token(token, cfg.JWT_SECRET, cfg.JWT_ALGORITHM)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Malformed token")
    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    return user

def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user

def _user_out(u: User) -> dict:
    return {
        "id":         u.id,
        "email":      u.email,
        "full_name":  u.full_name or "",
        "role":       u.role,
        "is_active":  u.is_active,
        "created_at": u.created_at.isoformat() if u.created_at else "",
    }

@router.post("/register", response_model=TokenResponse, status_code=201)
def register(payload: RegisterPayload, db: Session = Depends(get_db)):
    if not payload.email.strip() or "@" not in payload.email:
        raise HTTPException(status_code=422, detail="Valid email required.")
    if len(payload.password) < 6:
        raise HTTPException(status_code=422, detail="Password must be at least 6 characters.")

    if db.query(User).filter(User.email == payload.email.lower()).first():
        raise HTTPException(status_code=409, detail="Email already registered.")

    is_first = db.query(User).count() == 0
    role = "admin" if is_first else "analyst"

    user = User(
        email           = payload.email.strip().lower(),
        hashed_password = hash_password(payload.password),
        full_name       = payload.full_name.strip(),
        role            = role,
        created_at      = datetime.utcnow(),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    cfg   = get_settings()
    token = create_access_token(
        {"sub": str(user.id), "email": user.email, "role": user.role},
        expire_hours=cfg.JWT_EXPIRE_HOURS,
        secret=cfg.JWT_SECRET,
        algorithm=cfg.JWT_ALGORITHM,
    )
    logger.info("New user registered: %s (role=%s)", user.email, user.role)
    return {"access_token": token, "token_type": "bearer", "user": _user_out(user)}

@router.post("/token", response_model=TokenResponse)
def login_form(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = authenticate_user(db, form.username.lower(), form.password)
    if not user:
        raise HTTPException(status_code=401, detail="Incorrect email or password.")
    return _issue_token(user, db)

@router.post("/login", response_model=TokenResponse)
def login_json(payload: LoginPayload, db: Session = Depends(get_db)):
    user = authenticate_user(db, payload.email.strip().lower(), payload.password)
    if not user:
        raise HTTPException(status_code=401, detail="Incorrect email or password.")
    return _issue_token(user, db)

def _issue_token(user: User, db: Session) -> dict:
    user.last_login = datetime.utcnow()
    db.commit()
    cfg   = get_settings()
    token = create_access_token(
        {"sub": str(user.id), "email": user.email, "role": user.role},
        expire_hours=cfg.JWT_EXPIRE_HOURS,
        secret=cfg.JWT_SECRET,
        algorithm=cfg.JWT_ALGORITHM,
    )
    return {"access_token": token, "token_type": "bearer", "user": _user_out(user)}

@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)):
    return _user_out(current_user)

@router.post("/change-password")
def change_password(
    payload: ChangePasswordPayload,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from ..services.auth_service import verify_password, hash_password as _hash
    if not verify_password(payload.old_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Old password is incorrect.")
    if len(payload.new_password) < 6:
        raise HTTPException(status_code=422, detail="New password must be at least 6 characters.")
    current_user.hashed_password = _hash(payload.new_password)
    db.commit()
    return {"status": "ok"}

@router.get("/users", response_model=list)
def list_users(
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    users = db.query(User).order_by(User.id).all()
    return [_user_out(u) for u in users]
