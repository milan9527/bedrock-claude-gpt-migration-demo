"""Verify the deployed HTTPS path without printing the login password."""
import http.cookiejar
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    state = json.loads((ROOT / ".deploy/state.json").read_text())
    base = state["url"]
    password = (ROOT / ".deploy/login-password.txt").read_text().strip()
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

    def request(path, payload=None, authenticated=True):
        headers = {}
        data = None
        if payload is not None:
            data = json.dumps(payload).encode()
            headers["Content-Type"] = "application/json"
        with (opener.open if authenticated else urllib.request.urlopen)(urllib.request.Request(
                base + path, data=data, headers=headers), timeout=65) as response:
            body = response.read()
            return json.loads(body) if path.startswith("/api/") else body

    assert b"<html" in request("/", authenticated=False).lower()
    assert request("/api/health", authenticated=False)["status"] == "ok"
    try:
        request("/api/catalog", authenticated=False)
        raise AssertionError("Unauthenticated catalog was accepted")
    except urllib.error.HTTPError as exc:
        assert exc.code == 401, exc.code
    try:
        request('/api/login', {'username': 'admin', 'password': 'incorrect'})
        raise AssertionError('Incorrect password accepted')
    except urllib.error.HTTPError as exc:
        assert exc.code == 401
    assert request('/api/login', {'username': 'admin', 'password': password})['username'] == 'admin'
    assert len(jar) == 1
    cookie = next(iter(jar))
    assert cookie.secure and cookie.has_nonstandard_attr('HttpOnly')
    assert cookie.get_nonstandard_attr('SameSite') == 'Strict'
    assert request('/api/session')['username'] == 'admin'
    catalog = request("/api/catalog")
    print("HTTPS, health and username/password login checks passed", flush=True)
    print("Models:", len(catalog["models"]), "Scenarios:", len(catalog["scenarios"]), flush=True)
    job = request("/api/compare", {
        "source": "us.anthropic.claude-opus-4-8",
        "target": "us.openai.gpt-5.6-sol",
        "scenario": "agent_chain",
        "input": catalog["scenarios"]["agent_chain"]["input"],
        "sourceFields": {}, "targetFields": {},
    })
    deadline = time.monotonic() + 600
    while job["status"] == "running" and time.monotonic() < deadline:
        time.sleep(3)
        job = request("/api/jobs/" + job["id"])
    report_path = ROOT / ".deploy/smoke-report.json"
    report_path.write_text(json.dumps(job, ensure_ascii=False, indent=2))
    report_path.chmod(0o600)
    assert job["status"] == "completed", job.get("error", job["status"])
    assert len(job["report"]["results"]) == 3
    for result in job["report"]["results"]:
        summary = {key: result.get(key) for key in
                   ["model", "error", "stopReason", "checks"]}
        summary["roundCount"] = len(result.get("rounds", []))
        print(json.dumps(summary, ensure_ascii=False), flush=True)
        assert not result.get("error"), "Model call failed; inspect smoke-report.json"
        assert result["stopReason"] == "end_turn", summary
        assert summary["roundCount"] > 1, summary
        assert result["checks"] and all(result["checks"].values()), summary
    request('/api/logout', {})
    try:
        request('/api/session')
        raise AssertionError('Logged-out session accepted')
    except urllib.error.HTTPError as exc:
        assert exc.code == 401
    print("CloudFront → ECS → Bedrock multi-round comparison and logout passed", flush=True)


if __name__ == "__main__":
    main()
