import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


def call_api(prompt: str, options: dict, context: dict) -> dict[str, str]:
    config = options.get("config", {})
    url = os.environ.get(
        "SECURE_RAG_TARGET_URL",
        config.get("url", "http://127.0.0.1:8000/v1/query"),
    )
    parsed = urlparse(url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        return {"error": "target must use plain HTTP on loopback only"}

    token = os.environ.get("PROMPTFOO_BEARER_TOKEN")
    if not token:
        return {"error": "PROMPTFOO_BEARER_TOKEN is required"}

    request = Request(
        url,
        data=json.dumps({"question": prompt}).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=30) as response:
            return {"output": response.read().decode("utf-8")}
    except HTTPError as exc:
        return {"error": f"target returned HTTP {exc.code}"}
    except URLError:
        return {"error": "target connection failed"}


if __name__ == "__main__":
    print(call_api("test question", {}, {}))
