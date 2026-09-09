import json
import urllib.error
import urllib.request
import http.cookiejar

base = "http://127.0.0.1:5050"
cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))


def call(path, data=None, method=None):
    body = None
    headers = {}
    if data is not None:
        body = json.dumps(data).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(base + path, data=body, headers=headers, method=method)
    try:
        with opener.open(req, timeout=60) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


print("unauth sync", call("/api/admin/sync", {}, "POST")[0])
print("login", call("/api/admin/login", {"pin": "2026"}, "POST"))
print("sync week-1", call("/api/admin/sync", {"weekId": "week-1"}, "POST"))
print("search", call("/api/admin/espn-search?start=2026-09-04&end=2026-09-07")[0])
status, payload = call("/api/picks", {
    "playerId": "nathan",
    "picks": [{"gameId": "week-1-baylor-at-auburn", "team": "Auburn"}],
}, "POST")
print("pick", status, payload.get("saved"), payload.get("error"))
