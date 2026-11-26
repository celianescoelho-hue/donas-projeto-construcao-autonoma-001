# Helper: list DBs in the preview mongod (found via running mongod --dbpath /tmp/donas_previews/_mongo); uses admin creds (root-only file)
import subprocess
import re
from urllib.parse import quote_plus
import pymongo


def preview_mongo_port():
    out = subprocess.run(["ps", "-eo", "cmd", "--width", "1000"], capture_output=True, text=True).stdout
    for l in out.splitlines():
        if "mongod" in l and "donas_previews/_mongo" in l:
            m = re.search(r"--port (\d+)", l)
            if m:
                return int(m.group(1))
    return None


def preview_dbs():
    port = preview_mongo_port()
    if not port:
        return []
    pw = open("/tmp/donas_previews/.mongo_admin").read().strip()
    c = pymongo.MongoClient(f"mongodb://donas_admin:{quote_plus(pw)}@127.0.0.1:{port}/?authSource=admin", serverSelectionTimeoutMS=3000)
    try:
        return c.list_database_names()
    finally:
        c.close()


def preview_users():
    port = preview_mongo_port()
    pw = open("/tmp/donas_previews/.mongo_admin").read().strip()
    c = pymongo.MongoClient(f"mongodb://donas_admin:{quote_plus(pw)}@127.0.0.1:{port}/?authSource=admin", serverSelectionTimeoutMS=3000)
    try:
        return [u["user"] for u in c.admin.command("usersInfo", {"forAllDBs": True})["users"]]
    finally:
        c.close()
