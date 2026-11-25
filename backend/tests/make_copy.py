# Helper: copy text files of a member project into a new TEST_ project (for UI tests that mutate data)
import sys
import requests
sys.path.insert(0, "/app/backend/tests")
from conftest import BASE_URL, _token, MEMBER_EMAIL

s = requests.Session()
s.headers["Authorization"] = "Bearer " + _token(MEMBER_EMAIL)
src = sys.argv[1]
d = s.get(f"{BASE_URL}/api/projects/{src}").json()
pid = s.post(f"{BASE_URL}/api/projects", json={"name": "TEST_copy"}).json()["id"]
for f in d["files"]:
    if f["kind"] == "text":
        s.put(f"{BASE_URL}/api/projects/{pid}/files", json={"path": f["path"], "content": f["content"]})
print(pid, [f["path"] for f in d["files"]])
