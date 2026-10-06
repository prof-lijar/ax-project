from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import os
from threading import Barrier
import time
from uuid import uuid4

from alembic import command
from alembic.config import Config
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from fastapi.testclient import TestClient
import jwt
import pytest
from sqlalchemy import create_engine, event, inspect, MetaData, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.schema import BLANK_SCHEMA

from app.identity.config import IdentitySettings, load_identity_settings
from app.identity.models import ADMIN_PERMISSION_ID, ADMIN_ROLE_ID, Base, User
from app.identity.security import hash_password, passwords, read_token, verify_password
from app.identity.store import AccessError, IdentityStore
from app.main import create_app

PASSWORD = "test-pass123"
NEW_PASSWORD = "changed-456"


def migrate(url, monkeypatch, revision="head"):
    monkeypatch.setenv("NEXGENT_DATABASE_URL", url)
    command.upgrade(Config(str(Path(__file__).resolve().parents[2] / "alembic.ini")), revision)


@pytest.fixture
def database_url(tmp_path):
    maintenance = os.getenv("NEXGENT_TEST_DATABASE_URL")
    if not maintenance:
        yield f"sqlite:///{tmp_path / 'accounts.db'}"
        return
    # A dedicated temporary PostgreSQL cluster can exercise real DDL and row locks.
    name = "nexgent_test_" + uuid4().hex
    engine = create_engine(maintenance, isolation_level="AUTOCOMMIT")
    with engine.connect() as db:
        db.exec_driver_sql(f'CREATE DATABASE "{name}"')
    try:
        yield make_url(maintenance).set(database=name).render_as_string(hide_password=False)
    finally:
        with engine.connect() as db:
            db.exec_driver_sql(f'DROP DATABASE "{name}" WITH (FORCE)')
        engine.dispose()


@pytest.fixture
def stack(database_url, monkeypatch):
    url = database_url
    migrate(url, monkeypatch)
    engine = create_engine(url, connect_args={"check_same_thread": False} if url.startswith("sqlite") else {})
    if engine.dialect.name == "sqlite":
        engine = engine.execution_options(schema_translate_map={"auth": None, "chat": None, "file_storage": None})
        @event.listens_for(engine, "connect")
        def enable_foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")
    settings = IdentitySettings(url, "https://nexgent.test", "test-signing-key-that-is-at-least-48-bytes-for-tests")
    store = IdentityStore(settings, engine)
    admin = store.create_user(None, username="admin", name="Admin", email="", password=PASSWORD,
                              role_ids=[ADMIN_ROLE_ID], group_ids=[])
    member = store.create_user(None, username="member", name="Member", email="", password=PASSWORD,
                               role_ids=[], group_ids=[])
    with TestClient(create_app(identity_settings=settings, identity_store=store),
                    base_url=settings.public_url) as client:
        yield client, store, settings, admin, member


def login(stack, username="admin", password=PASSWORD):
    client, _, settings, *_ = stack
    response = client.post("/auth/login", headers={"Origin": settings.public_url},
                           json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return client.get("/api/me").json()


def headers(stack):
    return {"Origin": stack[2].public_url, "X-CSRF-Token": stack[0].get("/api/me").json()["csrf_token"]}


def actor(stack):
    return stack[1].authenticate(stack[0].cookies.get(stack[2].cookie_name))


def user_update(user, **changes):
    return {"name": user["name"], "email": user["email"], "is_active": user["is_active"],
            "role_ids": user["role_ids"], "group_ids": user["group_ids"], **changes}


def post(stack, kind, values):
    response = stack[0].post(f"/api/admin/{kind}", headers=headers(stack), json=values)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_final_schema_matches_models(stack):
    engine = stack[1].engine
    pg = engine.dialect.name == "postgresql"
    schema = "auth" if pg else None
    expected = {
        "alembic_version", "users", "groups", "roles", "permissions",
        "user_groups", "user_roles", "group_roles", "role_permissions"}
    chat_tables = {"conversations", "messages", "runs", "attachments", "message_attachments"}
    notification_tables = {"notification_jobs", "notification_rate_gates"}
    storage_tables = {"storage_entries", "storage_blobs"}
    assert set(inspect(engine).get_table_names(schema=schema)) == (expected if pg else expected | chat_tables | notification_tables | storage_tables)
    if pg:
        assert set(inspect(engine).get_table_names(schema="chat")) == chat_tables
        assert set(inspect(engine).get_table_names(schema="notifications")) == notification_tables
        assert set(inspect(engine).get_table_names(schema="file_storage")) == storage_tables
    metadata = Base.metadata
    if pg:
        assert inspect(engine).get_table_names(schema="public") == []
        for table in ("user_groups", "user_roles", "group_roles", "role_permissions"):
            assert all(fk["referred_schema"] == "auth" for fk in inspect(engine).get_foreign_keys(table, schema="auth"))
    else:
        metadata = MetaData()
        for table in Base.metadata.sorted_tables:
            table.to_metadata(metadata, schema=None, referred_schema_fn=lambda *_: BLANK_SCHEMA)
    with engine.connect() as connection:
        options = {"include_schemas": pg, "version_table_schema": schema}
        assert compare_metadata(MigrationContext.configure(connection, opts=options), metadata) == []
        if engine.dialect.name == "sqlite":
            assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1


def historical_public_layout(engine):
    """Simulate the layout written by the earlier migration runner."""
    if engine.dialect.name == "postgresql":
        tables = inspect(engine).get_table_names(schema="auth")
        with engine.begin() as db:
            for table in tables:
                db.exec_driver_sql(f'ALTER TABLE auth."{table}" SET SCHEMA public')


def test_migration_preserves_profiles_owner_and_suspension(database_url, monkeypatch):
    url = database_url
    migrate(url, monkeypatch, "20260917_01")
    engine = create_engine(url)
    historical_public_layout(engine)
    owner, suspended = str(uuid4()), str(uuid4())
    with engine.begin() as db:
        db.execute(text("INSERT INTO companies VALUES ('company-id', 'company', 'Company')"))
        for uid, role, status in ((owner, "owner", "active"), (suspended, "member", "suspended")):
            db.execute(text("INSERT INTO users VALUES (:id, 'Original name', 'old@example.test', CURRENT_TIMESTAMP)"), {"id": uid})
            db.execute(text("INSERT INTO memberships VALUES (:id, 'company-id', :uid, :role, :status)"),
                       {"id": str(uuid4()), "uid": uid, "role": role, "status": status})
            db.execute(text("INSERT INTO identities VALUES (:id, :uid, 'https://old.test', :uid)"),
                       {"id": str(uuid4()), "uid": uid})
    migrate(url, monkeypatch)
    if engine.dialect.name == "sqlite":
        engine = engine.execution_options(schema_translate_map={"auth": None})
    store = IdentityStore(IdentitySettings(url, "https://nexgent.test", "x" * 48), engine)
    with store.sessions() as db:
        user = db.get(User, owner)
        assert user.username == "user-" + owner.replace("-", "")
        assert user.display_name == "Original name" and user.email == "old@example.test"
        assert user.password_hash is None and user.is_active
        assert not db.get(User, suspended).is_active
    assert store.login(user.username, PASSWORD) is None
    store.reset_password(None, owner, PASSWORD)
    assert store.authenticate(store.login(user.username, PASSWORD)).permissions == ("access.manage",)
    engine.dispose()


def test_closed_boundary_and_no_public_registration(stack):
    client = stack[0]
    assert client.get("/health").status_code == 200
    for path in ("/api/me", "/api/admin/access", "/api/nextcloud/files", "/docs", "/auth/register"):
        assert client.get(path).status_code == 401
    login(stack)
    for path in ("/auth/register", "/auth/callback", "/api/me/sessions", "/docs"):
        assert client.get(path).status_code == 404


def test_password_hash_cookie_and_safe_responses(stack):
    me = login(stack, " ADMIN ")
    assert me["is_admin"] and me["roles"] == ["Administrator"]
    with stack[1].sessions() as db:
        user = db.get(User, me["id"])
        assert user.password_hash.startswith("$argon2id$")
        assert verify_password(PASSWORD, user.password_hash)
        assert PASSWORD not in user.password_hash
    response = stack[0].post("/auth/login", headers={"Origin": stack[2].public_url},
                            json={"username": "admin", "password": PASSWORD})
    cookie = response.headers["set-cookie"]
    assert all(value in cookie for value in (stack[2].cookie_name + "=", "HttpOnly", "Secure", "SameSite=lax", "Path=/"))
    catalog = stack[0].get("/api/admin/access")
    assert "password_hash" not in catalog.text and PASSWORD not in catalog.text
    assert catalog.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("username,password", [("missing", PASSWORD), ("admin", "wrong"), ("admin", "")])
def test_invalid_login_never_creates_account(stack, username, password):
    response = stack[0].post("/auth/login", headers={"Origin": stack[2].public_url},
                            json={"username": username, "password": password})
    assert response.status_code in (401, 422)
    assert stack[0].get("/api/me").status_code == 401
    with stack[1].sessions() as db:
        assert len(list(db.scalars(select(User)))) == 2


def test_origin_and_csrf_are_required(stack):
    client = stack[0]
    body = {"username": "admin", "password": PASSWORD}
    assert client.post("/auth/login", json=body).status_code == 403
    assert client.post("/auth/login", headers={"Origin": "https://evil.test"}, json=body).status_code == 403
    login(stack)
    assert client.post("/auth/logout", headers={"Origin": stack[2].public_url}).status_code == 403
    assert client.post("/auth/logout", headers={**headers(stack), "Origin": "https://evil.test"}).status_code == 403
    assert client.post("/auth/logout", headers=headers(stack)).status_code == 200
    assert client.get("/api/me").status_code == 401


@pytest.mark.parametrize("claims", [
    {"exp": 1}, {"iss": "other"}, {"aud": "other"}, {"ver": "0"},
    {"ver": True}, {"ver": -1}, {"sub": 4}, {"iat": int(time.time()) + 3600},
])
def test_invalid_signed_claims_are_rejected(stack, claims):
    settings = stack[2]
    payload = {"sub": stack[3]["id"], "ver": 0, "iat": int(time.time()),
               "exp": int(time.time()) + 300, "jti": "test", "iss": "nexgent", "aud": "nexgent-web", **claims}
    assert read_token(settings, jwt.encode(payload, settings.signing_key, algorithm="HS256")) is None


def test_forged_signature_wrong_algorithm_missing_claims(stack):
    token = stack[1].login("admin", PASSWORD)
    claims = jwt.decode(token, options={"verify_signature": False})
    assert read_token(stack[2], jwt.encode(claims, "wrong" * 10, algorithm="HS256")) is None
    assert read_token(stack[2], jwt.encode(claims, stack[2].signing_key, algorithm="HS384")) is None
    del claims["jti"]
    assert read_token(stack[2], jwt.encode(claims, stack[2].signing_key, algorithm="HS256")) is None
    assert read_token(stack[2], "malformed") is None


def test_logout_invalidates_all_logins(stack):
    login(stack)
    first = stack[0].cookies.get(stack[2].cookie_name)
    second = stack[1].login("admin", PASSWORD)
    assert first != second and stack[1].authenticate(second)
    assert stack[0].post("/auth/logout", headers=headers(stack)).status_code == 200
    assert stack[1].authenticate(first) is None
    assert stack[1].authenticate(second) is None


def test_admin_creates_account_and_resets_password(stack):
    login(stack)
    uid = post(stack, "users", {"username": " NEW-USER ", "name": "New User", "password": PASSWORD})
    token = stack[1].login("new-user", PASSWORD)
    response = stack[0].put(f"/api/admin/users/{uid}/password", headers=headers(stack), json={"password": NEW_PASSWORD})
    assert response.status_code == 200
    assert stack[1].authenticate(token) is None
    assert stack[1].login("new-user", PASSWORD) is None
    assert stack[1].login("new-user", NEW_PASSWORD)
    response = stack[0].post("/api/admin/users", headers=headers(stack),
                            json={"username": "new-user", "name": "Duplicate", "password": PASSWORD})
    assert response.status_code == 409


@pytest.mark.parametrize("length", [3, 4, 12, 13])
def test_password_length_limits_for_creation_and_reset(stack, length):
    login(stack)
    password = "x" * length
    valid = 4 <= length <= 12
    if valid:
        assert verify_password(password, hash_password(password))
    else:
        with pytest.raises(ValueError, match="Passwords must contain 4 to 12 characters"):
            hash_password(password)
    response = stack[0].post("/api/admin/users", headers=headers(stack),
                            json={"username": "boundary", "name": "Boundary", "password": password})
    assert response.status_code == (201 if valid else 422)
    response = stack[0].put(f"/api/admin/users/{stack[4]['id']}/password", headers=headers(stack),
                           json={"password": password})
    assert response.status_code == (200 if valid else 422)
    if valid:
        login(stack, username="boundary", password=password)
        login(stack, username="member", password=password)
    else:
        assert stack[1].login("boundary", password) is None
        assert stack[1].login("member", PASSWORD)


def test_existing_long_password_can_still_log_in(stack):
    legacy_password = "previous-password-longer-than-12"
    with stack[1].sessions.begin() as db:
        db.get(User, stack[4]["id"]).password_hash = passwords.hash(legacy_password)
    assert login(stack, username="member", password=legacy_password)["username"] == "member"


def test_disable_and_reenable_do_not_restore_old_tokens(stack):
    login(stack)
    member = stack[4]
    token = stack[1].login("member", PASSWORD)
    for active in (False, True):
        response = stack[0].put(f"/api/admin/users/{member['id']}", headers=headers(stack),
                               json=user_update(member, is_active=active))
        assert response.status_code == 200
        assert stack[1].authenticate(token) is None
        assert bool(stack[1].login("member", PASSWORD)) == active


@pytest.mark.parametrize("method,path,body", [
    ("get", "/api/admin/access", None), ("post", "/api/admin/users", {"username": "evil", "name": "Evil", "password": PASSWORD}),
    ("post", "/api/admin/groups", {"name": "Evil"}), ("post", "/api/admin/roles", {"name": "Evil"}),
    ("post", "/api/admin/permissions", {"key": "evil.write"}),
    ("put", f"/api/admin/roles/{ADMIN_ROLE_ID}", {"name": "Changed"}),
    ("delete", f"/api/admin/permissions/{ADMIN_PERMISSION_ID}", None),
])
def test_nonadmin_cannot_manage_access(stack, method, path, body):
    me = login(stack, "member")
    assert not me["is_admin"] and me["permissions"] == []
    response = stack[0].request(method, path, headers=headers(stack), **({"json": body} if body else {}))
    assert response.status_code == 403


def test_direct_and_group_role_union_and_live_revocation(stack):
    login(stack)
    p1 = post(stack, "permissions", {"key": "tasks.read"})
    p2 = post(stack, "permissions", {"key": "tasks.write"})
    r1 = post(stack, "roles", {"name": "Reader", "permission_ids": [p1]})
    r2 = post(stack, "roles", {"name": "Writer", "permission_ids": [p1, p2]})
    group = post(stack, "groups", {"name": "Engineering", "role_ids": [r2]})
    member = stack[4]
    token = stack[1].login("member", PASSWORD)
    response = stack[0].put(f"/api/admin/users/{member['id']}", headers=headers(stack),
                           json=user_update(member, role_ids=[r1], group_ids=[group]))
    assert response.status_code == 200
    assert stack[1].authenticate(token).permissions == ("tasks.read", "tasks.write")
    assert stack[0].delete(f"/api/admin/groups/{group}", headers=headers(stack)).status_code == 200
    assert stack[1].authenticate(token).permissions == ("tasks.read",)
    assert stack[0].delete(f"/api/admin/permissions/{p1}", headers=headers(stack)).status_code == 200
    assert stack[1].authenticate(token).permissions == ()
    assert stack[0].delete(f"/api/admin/roles/{r1}", headers=headers(stack)).status_code == 200


def test_custom_role_and_group_can_grant_admin(stack):
    login(stack)
    role = post(stack, "roles", {"name": "Access managers", "permission_ids": [ADMIN_PERMISSION_ID]})
    group = post(stack, "groups", {"name": "IT", "role_ids": [role]})
    member = stack[4]
    stack[0].put(f"/api/admin/users/{member['id']}", headers=headers(stack), json=user_update(member, group_ids=[group]))
    login(stack, "member")
    assert stack[0].get("/api/admin/access").status_code == 200


@pytest.mark.parametrize("changes", [{"role_ids": []}, {"is_active": False}])
def test_last_admin_user_changes_rollback(stack, changes):
    login(stack)
    response = stack[0].put(f"/api/admin/users/{stack[3]['id']}", headers=headers(stack),
                           json=user_update(stack[3], **changes))
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "last_admin_required"
    assert stack[0].get("/api/me").json()["is_admin"]


@pytest.mark.parametrize("operation", ["delete_group", "delete_role", "empty_group", "empty_role", "remove_membership"])
def test_last_admin_protected_through_group_and_custom_role(stack, operation):
    login(stack)
    role = post(stack, "roles", {"name": "Access managers", "permission_ids": [ADMIN_PERMISSION_ID]})
    group = post(stack, "groups", {"name": "IT", "role_ids": [role]})
    user = stack[3]
    assert stack[0].put(f"/api/admin/users/{user['id']}", headers=headers(stack),
                       json=user_update(user, role_ids=[], group_ids=[group])).status_code == 200
    client, h = stack[0], headers(stack)
    if operation == "delete_group":
        response = client.delete(f"/api/admin/groups/{group}", headers=h)
    elif operation == "delete_role":
        response = client.delete(f"/api/admin/roles/{role}", headers=h)
    elif operation == "empty_group":
        response = client.put(f"/api/admin/groups/{group}", headers=h, json={"name": "IT", "role_ids": []})
    elif operation == "empty_role":
        response = client.put(f"/api/admin/roles/{role}", headers=h, json={"name": "Access managers", "permission_ids": []})
    else:
        response = client.put(f"/api/admin/users/{user['id']}", headers=h, json=user_update(user, role_ids=[], group_ids=[]))
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "last_admin_required"
    assert client.get("/api/me").json()["is_admin"]


def test_revoked_actor_cannot_reuse_previously_loaded_permissions(stack):
    login(stack)
    admin_actor = actor(stack)
    backup = stack[1].create_user(admin_actor, username="backup", name="Backup", email="", password=PASSWORD,
                                 role_ids=[ADMIN_ROLE_ID], group_ids=[])
    stack[1].update_user(admin_actor, stack[3]["id"], {"role_ids": []})
    with pytest.raises(AccessError) as error:
        stack[1].create_user(admin_actor, username="stale", name="Stale", email="", password=PASSWORD, role_ids=[], group_ids=[])
    assert error.value.status == 403
    assert stack[0].get("/api/admin/access").status_code == 403
    assert backup["permissions"] == ["access.manage"]


def test_concurrent_admin_removals_keep_one_active_admin(stack):
    store = stack[1]
    if store.engine.dialect.name != "postgresql":
        pytest.skip("Real row-lock concurrency requires NEXGENT_TEST_DATABASE_URL")
    login(stack)
    first = actor(stack)
    store.create_user(first, username="backup", name="Backup", email="", password=PASSWORD,
                      role_ids=[ADMIN_ROLE_ID], group_ids=[])
    second = store.authenticate(store.login("backup", PASSWORD))
    barrier = Barrier(2)
    def disable_self(account):
        barrier.wait(timeout=5)
        try:
            store.update_user(account, account.user_id, {"is_active": False})
            return "disabled"
        except AccessError as error:
            return error.code
    with ThreadPoolExecutor(max_workers=2) as workers:
        outcomes = list(workers.map(disable_self, [first, second]))
    assert sorted(outcomes) == ["disabled", "last_admin_required"]
    assert sum(bool(store.login(name, PASSWORD)) for name in ("admin", "backup")) == 1


@pytest.mark.parametrize("kind,uid,values", [
    ("roles", ADMIN_ROLE_ID, {"name": "Changed", "permission_ids": []}),
    ("permissions", ADMIN_PERMISSION_ID, {"key": "changed"}),
])
def test_built_in_definitions_read_only(stack, kind, uid, values):
    login(stack)
    assert stack[0].put(f"/api/admin/{kind}/{uid}", headers=headers(stack), json=values).status_code == 409
    assert stack[0].delete(f"/api/admin/{kind}/{uid}", headers=headers(stack)).status_code == 409


def test_unknown_assignments_and_secret_validation_are_safe(stack):
    login(stack)
    response = stack[0].post("/api/admin/users", headers=headers(stack),
                            json={"username": "invalid", "name": "Invalid", "password": PASSWORD, "role_ids": [str(uuid4())]})
    assert response.status_code == 422
    assert stack[1].login("invalid", PASSWORD) is None
    for values in ({"password": "abc"}, {"password": PASSWORD, "unexpected": "sensitive"}):
        response = stack[0].post("/api/admin/users", headers=headers(stack),
                                json={"username": "invalid", "name": "Invalid", **values})
        assert response.status_code == 422
        assert response.json() == {"error": {"code": "invalid_input"}}


def test_database_outage_fails_closed(stack, monkeypatch):
    def unavailable(_):
        raise RuntimeError("unavailable")
    monkeypatch.setattr(stack[1], "authenticate", unavailable)
    assert stack[0].get("/api/me").status_code == 503


def test_configuration_requires_safe_settings(monkeypatch):
    monkeypatch.delenv("NEXGENT_ALLOW_INSECURE_HTTP", raising=False)
    monkeypatch.setenv("NEXGENT_PUBLIC_URL", "http://company.test")
    with pytest.raises(ValueError, match="HTTPS"):
        load_identity_settings()
    monkeypatch.setenv("NEXGENT_PUBLIC_URL", "http://localhost:5180")
    monkeypatch.setenv("NEXGENT_ALLOW_INSECURE_HTTP", "true")
    monkeypatch.setenv("NEXGENT_DATABASE_URL", "postgresql+psycopg://user:pass@localhost/nexgent")
    monkeypatch.setenv("NEXGENT_AUTH_SIGNING_KEY", "short")
    with pytest.raises(ValueError, match="32"):
        load_identity_settings()
    monkeypatch.setenv("NEXGENT_AUTH_SIGNING_KEY", "a" * 48)
    assert not load_identity_settings().secure_cookies


def test_schema_upgrade_preserves_local_credentials_and_assignments(database_url, monkeypatch):
    migrate(database_url, monkeypatch, "20260917_02")
    engine = create_engine(database_url)
    historical_public_layout(engine)
    old = engine.execution_options(schema_translate_map={"auth": "public" if engine.dialect.name == "postgresql" else None})
    settings = IdentitySettings(database_url, "https://nexgent.test", "test-schema-migration-key" * 2)
    store = IdentityStore(settings, old)
    user = store.create_user(None, username="original", name="Original", email="", password=PASSWORD,
                             role_ids=[ADMIN_ROLE_ID], group_ids=[])
    permission = store.save_item(None, "permissions", None, {"key": "tasks.read", "description": "Read tasks"})["id"]
    role = store.save_item(None, "roles", None, {"name": "Reader", "description": "", "permission_ids": [permission]})["id"]
    group = store.save_item(None, "groups", None, {"name": "Team", "description": "", "role_ids": [role]})["id"]
    store.update_user(None, user["id"], {"group_ids": [group]})
    token = store.login("original", PASSWORD)
    with store.sessions() as db:
        original_hash = db.get(User, user["id"]).password_hash
    migrate(database_url, monkeypatch)
    current = engine if engine.dialect.name == "postgresql" else engine.execution_options(schema_translate_map={"auth": None})
    store = IdentityStore(settings, current)
    account = store.authenticate(token)
    assert account.user_id == user["id"] and account.permissions == ("access.manage", "tasks.read")
    assert store.login("original", PASSWORD)
    with store.sessions() as db:
        assert db.get(User, user["id"]).password_hash == original_hash
    assert store.catalog(account)["users"][0]["group_ids"] == [group]
    if engine.dialect.name == "postgresql":
        assert inspect(engine).get_table_names(schema="public") == []
    # A subsequent upgrade must find auth.alembic_version without rerunning DDL.
    migrate(database_url, monkeypatch)
    if engine.dialect.name == "postgresql":
        config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
        command.downgrade(config, "20260917_02")
        assert "users" in inspect(engine).get_table_names(schema="public")
        migrate(database_url, monkeypatch)
        assert store.authenticate(token).permissions == ("access.manage", "tasks.read")
    engine.dispose()


def test_fresh_auth_schema_ignores_public_user_table(database_url, monkeypatch):
    engine = create_engine(database_url)
    if engine.dialect.name != "postgresql":
        engine.dispose()
        pytest.skip("PostgreSQL schemas required")
    with engine.begin() as db:
        db.exec_driver_sql("CREATE TABLE public.users (marker text)")
        db.exec_driver_sql("INSERT INTO public.users VALUES ('unrelated')")
    migrate(database_url, monkeypatch)
    store = IdentityStore(IdentitySettings(database_url, "https://nexgent.test", "x" * 48), engine)
    store.create_user(None, username="admin", name="Admin", email="", password=PASSWORD,
                      role_ids=[ADMIN_ROLE_ID], group_ids=[])
    assert store.authenticate(store.login("admin", PASSWORD)).permissions == ("access.manage",)
    with engine.connect() as db:
        assert db.exec_driver_sql("SELECT marker FROM public.users").scalar() == "unrelated"
        assert db.exec_driver_sql("SELECT username FROM auth.users").scalar() == "admin"
        assert db.exec_driver_sql("SELECT version_num FROM auth.alembic_version").scalar() == "20260930_06"
        assert db.exec_driver_sql("SELECT to_regclass('public.alembic_version')").scalar() is None
    command.check(Config(str(Path(__file__).resolve().parents[2] / "alembic.ini")))
    engine.dispose()


def test_real_login_protects_feature_routes_and_mutations(stack):
    client = stack[0]
    assert client.post('/api/rag/chat/stream', json={}).status_code == 401
    login(stack, 'member')
    assert client.post('/api/rag/chat/stream', json={}).status_code == 403
    # An ordinary signed-in user can reach feature validation with valid CSRF.
    assert client.post('/api/rag/chat/stream', json={}, headers=headers(stack)).status_code == 422
