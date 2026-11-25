# Iteration 2: regression tests for '..' 400s, GitHub import validation, atomic version numbers
import concurrent.futures as cf
import pytest
from conftest import BASE_URL

API = f"{BASE_URL}/api"


def _proj(member, created, name):
    r = member.post(f"{API}/projects", json={"name": name})
    assert r.status_code == 200, r.text
    created.append(r.json()["id"])
    return r.json()["id"]


# --- path traversal returns 400 everywhere
class TestTraversal:
    def test_put_delete_asset_upload(self, member, created_projects):
        pid = _proj(member, created_projects, "TEST_trav_it2")
        r = member.put(f"{API}/projects/{pid}/files", json={"path": "a/../../x.txt", "content": "x"})
        assert r.status_code == 400 and "inválido" in r.json()["detail"]
        r = member.delete(f"{API}/projects/{pid}/files", params={"path": "../x.txt"})
        assert r.status_code == 400, r.text
        r = member.get(f"{API}/projects/{pid}/asset", params={"path": "../x.png"})
        assert r.status_code == 400, r.text
        r = member.post(f"{API}/projects/{pid}/upload", data={"directory": "../up"},
                        files=[("files", ("a.txt", b"hi", "text/plain"))])
        assert r.status_code == 400, r.text
        r = member.post(f"{API}/projects/{pid}/upload", data={"directory": ""},
                        files=[("files", ("..", b"hi", "text/plain"))])
        assert r.status_code in (400, 200), r.text  # filename '..' must not 500
        assert member.get(f"{API}/projects/{pid}").json()["files"] == [] or r.status_code == 200


# --- GitHub import validation (no PAT available)
class TestGithubImport:
    def test_member_has_no_pat(self, member):
        assert member.get(f"{API}/me").json()["github_login"] in (None, "")

    def test_import_into_empty_project_requires_pat(self, member, created_projects):
        pid = _proj(member, created_projects, "TEST_ghimp_empty")
        r = member.post(f"{API}/projects/{pid}/github/import", json={"owner": "octocat", "repo": "Hello-World", "branch": "master"})
        assert r.status_code == 400 and "Conecte o GitHub" in r.json()["detail"], r.text
        d = member.get(f"{API}/projects/{pid}").json()
        assert d["files"] == [] and d["project"]["github"] is None

    def test_import_into_project_with_files_409(self, member, created_projects):
        pid = _proj(member, created_projects, "TEST_ghimp_full")
        assert member.put(f"{API}/projects/{pid}/files", json={"path": "a.txt", "content": "x"}).status_code == 200
        r = member.post(f"{API}/projects/{pid}/github/import", json={"owner": "o", "repo": "r", "branch": "main"})
        assert r.status_code == 409, r.text
        files = member.get(f"{API}/projects/{pid}").json()["files"]
        assert [f["path"] for f in files] == ["a.txt"]

    def test_import_into_other_users_project_404(self, admin, member, created_projects):
        pid = _proj(member, created_projects, "TEST_ghimp_iso")
        r = admin.post(f"{API}/projects/{pid}/github/import", json={"owner": "o", "repo": "r", "branch": "main"})
        assert r.status_code == 404

    def test_create_import_requires_pat_and_leaves_no_project(self, member):
        before = len(member.get(f"{API}/projects").json())
        r = member.post(f"{API}/projects/import", json={"owner": "octocat", "repo": "TEST_none", "branch": "main"})
        assert r.status_code == 400 and "Conecte o GitHub" in r.json()["detail"], r.text
        projs = member.get(f"{API}/projects").json()
        assert len(projs) == before and not any(p["name"] == "TEST_none" for p in projs)

    def test_import_missing_fields_422(self, member, created_projects):
        pid = _proj(member, created_projects, "TEST_ghimp_422")
        r = member.post(f"{API}/projects/{pid}/github/import", json={"owner": "o"})
        assert r.status_code == 422


# --- version numbers are atomic and sequential
class TestVersions:
    def test_concurrent_saves_sequential(self, member, created_projects):
        pid = _proj(member, created_projects, "TEST_ver_conc")

        def save(i):
            return member.put(f"{API}/projects/{pid}/files", json={"path": f"f{i}.txt", "content": str(i)}).status_code

        with cf.ThreadPoolExecutor(8) as ex:
            codes = list(ex.map(save, range(8)))
        assert codes == [200] * 8, codes
        nums = sorted(v["number"] for v in member.get(f"{API}/projects/{pid}/versions").json())
        assert nums == list(range(1, 9)), nums

    def test_save_upload_restore_sequence(self, member, created_projects):
        pid = _proj(member, created_projects, "TEST_ver_seq")
        member.put(f"{API}/projects/{pid}/files", json={"path": "x.txt", "content": "1"})
        member.put(f"{API}/projects/{pid}/files", json={"path": "x.txt", "content": "2"})
        member.post(f"{API}/projects/{pid}/upload", files=[("files", ("y.md", b"# y", "text/markdown"))])
        vs = member.get(f"{API}/projects/{pid}/versions").json()
        assert [v["number"] for v in vs] == [3, 2, 1]
        v1 = [v for v in vs if v["number"] == 1][0]
        assert member.post(f"{API}/projects/{pid}/versions/{v1['id']}/restore").status_code == 200
        member.delete(f"{API}/projects/{pid}/files", params={"path": "x.txt"})
        vs = member.get(f"{API}/projects/{pid}/versions").json()
        assert [v["number"] for v in vs] == [5, 4, 3, 2, 1]
        assert vs[1]["source"] == "restore" and vs[0]["source"] == "manual"
