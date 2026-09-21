from app.identity.config import IdentitySettings
from app.identity.security import csrf_token
from app.identity.store import Account

TEST_TOKEN = "feature-test-cookie"
TEST_SETTINGS = IdentitySettings("postgresql+psycopg://unused/test", "http://testserver", "test-key" * 8, False)

class FeatureIdentityStore:
    def authenticate(self, token):
        if token != TEST_TOKEN:
            return None
        return Account("test-user", "tester", "Tester", "", (), (), 0)

def feature_app():
    from app.main import create_app
    app = create_app(identity_settings=TEST_SETTINGS, identity_store=FeatureIdentityStore())
    # Validation tests do not submit valid work. Ownership rejection never calls an upstream.
    class NoChatStore:
        def conversation(self, *_):
            from app.identity.store import AccessError
            raise AccessError(404, "not_found")
    app.state.chat_store = NoChatStore()
    return app

def authenticated_headers():
    return {"Cookie": f"{TEST_SETTINGS.cookie_name}={TEST_TOKEN}",
            "Origin": TEST_SETTINGS.public_url, "X-CSRF-Token": csrf_token(TEST_TOKEN)}
