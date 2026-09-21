"""Check the running Nexgent login and protected API boundary; credentials are optional and read privately."""
import argparse
from getpass import getpass
from http.cookiejar import CookieJar
import json
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--login", action="store_true", help="Also check an existing admin login and logout")
parser.add_argument("--origin", default="http://localhost:5173")
args = parser.parse_args()
origin = args.origin.rstrip("/")
opener = build_opener(HTTPCookieProcessor(CookieJar()))


def request(path, expected, method="GET", data=None, csrf=None):
    headers = {"Origin": origin}
    if data is not None:
        headers["Content-Type"] = "application/json"
    if csrf:
        headers["X-CSRF-Token"] = csrf
    req = Request(origin + path, method=method, headers=headers,
                  data=json.dumps(data).encode() if data is not None else None)
    try:
        response = opener.open(req, timeout=15)
    except HTTPError as error:
        response = error
    with response:
        body = response.read()
        assert response.code == expected, f"{path}: expected {expected}, got {response.code}"
        return json.loads(body) if body and response.headers.get_content_type() == "application/json" else None


request("/", 200)
request("/api/me", 401)
request("/api/admin/access", 401)
request("/api/nextcloud/files", 401)
request("/agent-server/ok", 401)
request("/scout-api/v1/scout/runs", 401)
request("/scout-scheduler-api/v1/scout/schedules", 401)
request("/rag-api/rag/v1/data/stats", 401)
request("/weekly-report-bulk-api/health/ready", 401)
request("/auth/login", 401, "POST", {"username": "nonexistent-smoke-user", "password": "invalid"})
if args.login:
    username = input("Existing administrator username: ")
    password = getpass("Password: ")
    request("/auth/login", 200, "POST", {"username": username, "password": password})
    del password
    account = request("/api/me", 200)
    request("/api/admin/access", 200)
    request("/auth/logout", 200, "POST", {}, account["csrf_token"])
    request("/api/me", 401)
print("PASS: account boundary checks" + (" and administrator login/logout." if args.login else "."))
