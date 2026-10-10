from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import AuthorizationError, ValidationError
from app.core.security import hash_password
from app.models import Role, User
from app.repositories.user_repository import UserRepository


class UserManagementService:
    CREATABLE_ROLES = ("ADMIN", "SUPERVISOR", "CASHIER")
    MIN_PASSWORD_LENGTH = 8

    def __init__(self, session: Session, users: UserRepository):
        self.session = session
        self.users = users

    def list_users(self, actor: User) -> list[User]:
        self._require_owner(actor)
        return self.users.list_active()

    def create_user(
        self,
        actor: User,
        *,
        username: str,
        full_name: str,
        password: str,
        role_name: str,
    ) -> User:
        self._require_owner(actor)

        username = username.strip()
        full_name = full_name.strip()
        role_name = role_name.strip().upper()

        if not username:
            raise ValidationError("Username wajib diisi.")
        if len(username) > 80:
            raise ValidationError("Username maksimal 80 karakter.")
        if not full_name:
            raise ValidationError("Nama lengkap wajib diisi.")
        if len(full_name) > 150:
            raise ValidationError("Nama lengkap maksimal 150 karakter.")
        if len(password) < self.MIN_PASSWORD_LENGTH:
            raise ValidationError(
                f"Password minimal {self.MIN_PASSWORD_LENGTH} karakter."
            )
        if role_name not in self.CREATABLE_ROLES:
            raise ValidationError("Role yang dapat dibuat tidak valid.")
        if self.users.username_exists(username):
            raise ValidationError("Username sudah digunakan.")

        role = self.session.scalar(select(Role).where(Role.name == role_name))
        if role is None:
            raise ValidationError(
                f"Role {role_name} belum tersedia. Jalankan scripts\\seed.py."
            )

        user = User(
            username=username,
            full_name=full_name,
            password_hash=hash_password(password),
            role=role,
        )
        self.session.add(user)
        try:
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise ValidationError("Username sudah digunakan.") from exc
        self.session.refresh(user)
        return user

    def delete_user(self, actor: User, user_id: int) -> None:
        self._require_owner(actor)
        user = self.session.get(User, user_id)
        if user is None or user.deleted_at is not None:
            raise ValidationError("Pengguna yang akan dihapus tidak ditemukan.")
        if user.id == actor.id or user.role.name.upper() == "OWNER":
            raise ValidationError("Akun OWNER tidak dapat dihapus.")

        user.deleted_at = datetime.now(timezone.utc)
        user.is_active = False
        try:
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

    @staticmethod
    def _require_owner(actor: User) -> None:
        if actor.role.name.upper() != "OWNER":
            raise AuthorizationError(
                "Hanya OWNER yang dapat mengelola akun pengguna."
            )
