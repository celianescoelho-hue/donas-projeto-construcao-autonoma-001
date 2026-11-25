# Helper: list DBs in the preview mongod (found via running mongod --dbpath /tmp/donas_previews/_mongo)
import subprocess
import re
import pymongo


def preview_mongo_port():
    out = subprocess.run(["ps", "-eo", "cmd"], capture_output=True, text=True).stdout
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
    c = pymongo.MongoClient(f"mongodb://127.0.0.1:{port}", serverSelectionTimeoutMS=3000)
    try:
        return c.list_database_names()
    finally:
        c.close()
