import json, urllib.request, urllib.error

def test_put(url, body):
    data = json.dumps(body).encode()
    headers = {"Content-Type": "application/json", "Authorization": "Bearer local-dev-token"}
    req = urllib.request.Request(url, data=data, headers=headers, method="PUT")
    try:
        resp = urllib.request.urlopen(req, timeout=5)
        print(f"  OK {resp.status}: {resp.read().decode()[:200]}")
    except urllib.error.HTTPError as e:
        print(f"  ERROR {e.code}: {e.read().decode()[:200]}")

print("Test 1: PUT /jobs/abc/candidates/def")
test_put("http://localhost:3001/jobs/abc/candidates/def", {"shortlisted": True})

print("\nTest 2: PUT /jobs/abc/candidates/def/invite")
test_put("http://localhost:3001/jobs/abc/candidates/def/invite", {})
