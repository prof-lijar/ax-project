from contextlib import contextmanager
from dataclasses import dataclass

from sqlalchemy import create_engine, delete, select, union, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.identity.models import (ADMIN_ROLE_ID, Group, GroupRole, Permission, Role,
                                 RolePermission, User, UserGroup, UserRole)
from app.identity.security import hash_password, issue_token, read_token, verify_password


class AccessError(Exception):
    def __init__(self, status: int, code: str):
        self.status, self.code = status, code


@dataclass(frozen=True)
class Account:
    user_id: str
    username: str
    display_name: str
    email: str
    permissions: tuple[str, ...]
    roles: tuple[str, ...]
    version: int


def effective_roles(user_id: str):
    return union(
        select(UserRole.role_id).where(UserRole.user_id == user_id),
        select(GroupRole.role_id).join(UserGroup, UserGroup.group_id == GroupRole.group_id)
        .where(UserGroup.user_id == user_id),
    )


def permission_keys(db, user_id: str) -> tuple[str, ...]:
    return tuple(db.scalars(select(Permission.key).join(RolePermission).where(
        RolePermission.role_id.in_(effective_roles(user_id)),
    ).distinct().order_by(Permission.key)))


class IdentityStore:
    def __init__(self, settings, engine=None):
        self.settings = settings
        self.engine = engine if engine is not None else create_engine(
            settings.database_url, pool_pre_ping=True, hide_parameters=True,
        )
        self.sessions = sessionmaker(self.engine, expire_on_commit=False)

    def ready(self):
        with self.sessions() as db:
            db.execute(select(User.username).limit(1))
            if db.get(Role, ADMIN_ROLE_ID) is None:
                raise RuntimeError("Run account database migrations before startup")

    def login(self, username: str, password: str) -> str | None:
        with self.sessions.begin() as db:
            user = db.scalar(select(User).where(User.username == username.strip().lower()).with_for_update())
            valid = verify_password(password, user.password_hash if user else None)
            if not user or not valid or not user.is_active:
                return None
            return issue_token(self.settings, user.id, user.token_version)

    def authenticate(self, token: str | None) -> Account | None:
        identity = read_token(self.settings, token)
        if identity is None:
            return None
        with self.sessions() as db:
            user = db.get(User, identity.user_id)
            if not user or not user.is_active or user.token_version != identity.version:
                return None
            return Account(user.id, user.username, user.display_name, user.email,
                           permission_keys(db, user.id),
                           tuple(db.scalars(select(Role.name).where(Role.id.in_(effective_roles(user.id))).order_by(Role.name))),
                           user.token_version)

    def logout(self, account: Account):
        with self.sessions.begin() as db:
            db.execute(update(User).where(User.id == account.user_id,
                       User.token_version == account.version).values(token_version=User.token_version + 1))

    @contextmanager
    def admin_transaction(self, actor: Account | None):
        try:
            with self.sessions.begin() as db:
                # Serialize access edits and the last-admin check using a fixed role row.
                if not db.scalar(select(Role).where(Role.id == ADMIN_ROLE_ID).with_for_update()):
                    raise AccessError(503, "migration_required")
                if actor is not None:
                    user = db.get(User, actor.user_id)
                    if not user or not user.is_active or user.token_version != actor.version:
                        raise AccessError(401, "authentication_required")
                    if "access.manage" not in permission_keys(db, user.id):
                        raise AccessError(403, "permission_denied")
                yield db
                db.flush()
                active = list(db.scalars(select(User).where(User.is_active.is_(True), User.password_hash.is_not(None))))
                if not any("access.manage" in permission_keys(db, user.id) for user in active):
                    raise AccessError(409, "last_admin_required")
        except IntegrityError as error:
            raise AccessError(409, "duplicate_or_invalid_reference") from error

    def catalog(self, actor: Account):
        with self.sessions() as db:
            user = db.get(User, actor.user_id)
            if not user or not user.is_active or user.token_version != actor.version:
                raise AccessError(401, "authentication_required")
            if "access.manage" not in permission_keys(db, actor.user_id):
                raise AccessError(403, "permission_denied")
            return {
                "users": [self.user_view(db, user) for user in db.scalars(select(User).order_by(User.username))],
                "groups": [{"id": g.id, "name": g.name, "description": g.description,
                            "role_ids": list(db.scalars(select(GroupRole.role_id).where(GroupRole.group_id == g.id)))}
                           for g in db.scalars(select(Group).order_by(Group.name))],
                "roles": [{"id": r.id, "name": r.name, "description": r.description, "is_system": r.is_system,
                           "permission_ids": list(db.scalars(select(RolePermission.permission_id).where(RolePermission.role_id == r.id)))}
                          for r in db.scalars(select(Role).order_by(Role.name))],
                "permissions": [{"id": p.id, "key": p.key, "description": p.description, "is_system": p.is_system}
                                for p in db.scalars(select(Permission).order_by(Permission.key))],
            }

    @staticmethod
    def user_view(db, user):
        return {"id": user.id, "username": user.username, "name": user.display_name, "email": user.email,
                "is_active": user.is_active, "password_set": user.password_hash is not None,
                "role_ids": list(db.scalars(select(UserRole.role_id).where(UserRole.user_id == user.id))),
                "group_ids": list(db.scalars(select(UserGroup.group_id).where(UserGroup.user_id == user.id))),
                "permissions": list(permission_keys(db, user.id))}

    @staticmethod
    def replace_links(db, model, source_column, source_id, target_column, target_model, ids):
        unique = set(ids)
        existing = set(db.scalars(select(target_model.id).where(target_model.id.in_(unique))))
        if existing != unique:
            raise AccessError(422, "unknown_assignment")
        db.execute(delete(model).where(getattr(model, source_column) == source_id))
        db.add_all([model(**{source_column: source_id, target_column: target_id}) for target_id in unique])
        db.flush()

    def create_user(self, actor, *, username, name, email, password, role_ids, group_ids):
        encoded = hash_password(password)
        with self.admin_transaction(actor) as db:
            user = User(username=username, display_name=name, email=email, password_hash=encoded)
            db.add(user)
            db.flush()
            self.assign_user(db, user.id, role_ids, group_ids)
            return self.user_view(db, user)

    def assign_user(self, db, user_id, role_ids, group_ids):
        if role_ids is not None:
            self.replace_links(db, UserRole, "user_id", user_id, "role_id", Role, role_ids)
        if group_ids is not None:
            self.replace_links(db, UserGroup, "user_id", user_id, "group_id", Group, group_ids)

    def update_user(self, actor, user_id, changes):
        with self.admin_transaction(actor) as db:
            user = db.get(User, user_id)
            if user is None:
                raise AccessError(404, "not_found")
            for field in ("display_name", "email", "is_active"):
                if field in changes:
                    if field == "is_active" and user.is_active != changes[field]:
                        user.token_version += 1
                    setattr(user, field, changes[field])
            self.assign_user(db, user.id, changes.get("role_ids"), changes.get("group_ids"))
            db.flush()
            return self.user_view(db, user)

    def reset_password(self, actor, user_id, password):
        encoded = hash_password(password)
        with self.admin_transaction(actor) as db:
            user = db.get(User, user_id)
            if user is None:
                raise AccessError(404, "not_found")
            user.password_hash = encoded
            user.token_version += 1

    def save_item(self, actor, kind, item_id, values):
        model = {"groups": Group, "roles": Role, "permissions": Permission}[kind]
        with self.admin_transaction(actor) as db:
            item = db.get(model, item_id) if item_id else model()
            if item is None:
                raise AccessError(404, "not_found")
            if item_id and getattr(item, "is_system", False):
                raise AccessError(409, "system_definition_read_only")
            for key in ("name", "key", "description"):
                if key in values:
                    setattr(item, key, values[key])
            db.add(item)
            db.flush()
            if kind == "groups":
                self.replace_links(db, GroupRole, "group_id", item.id, "role_id", Role, values["role_ids"])
            elif kind == "roles":
                self.replace_links(db, RolePermission, "role_id", item.id, "permission_id", Permission, values["permission_ids"])
            return {"id": item.id}

    def delete_item(self, actor, kind, item_id):
        model = {"groups": Group, "roles": Role, "permissions": Permission}[kind]
        with self.admin_transaction(actor) as db:
            item = db.get(model, item_id)
            if item is None:
                raise AccessError(404, "not_found")
            if getattr(item, "is_system", False):
                raise AccessError(409, "system_definition_read_only")
            db.delete(item)
