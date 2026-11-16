import os

import uvicorn

if not os.environ.get("KAKAO_MOCK_TOKEN"):
    raise SystemExit("Set KAKAO_MOCK_TOKEN to a test bearer token first")

uvicorn.run("mock_api.server:from_env", factory=True, host="127.0.0.1", port=8000, access_log=False)
