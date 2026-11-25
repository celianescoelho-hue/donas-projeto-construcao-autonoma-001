# Iteration 6: search_in_files schema + alias unit checks (read-only on member project 90476221...)
import asyncio, sys
sys.path.insert(0, "/app/backend")
from dotenv import load_dotenv; load_dotenv("/app/backend/.env")
from agent import Agent, TOOLS, TOOL_NAMES

PID = "90476221-f03b-4fd0-b84e-113bfdfcedbc"
res = {}


def check(name, cond, info=""):
    res[name] = bool(cond)
    print(("PASS " if cond else "FAIL ") + name, str(info)[:300])


async def main():
    t = next(t["function"] for t in TOOLS if t["function"]["name"] == "search_in_files")
    p = t["parameters"]
    check("schema_required_query", p.get("required") == ["query"], p.get("required"))
    check("schema_minLength", p["properties"]["query"].get("minLength") == 1)
    check("schema_additionalProperties_false", p.get("additionalProperties") is False)
    check("schema_desc_example", "Exemplo" in t["description"] and "query" in t["description"])
    check("legacy_name_in_TOOL_NAMES", "search_files" in TOOL_NAMES)

    a = Agent({"id": PID}, {"user_id": "unit"}, asyncio.Queue())
    r = await a.run_tool("search_in_files", {})
    check("empty_args_error", r.startswith("ERRO") and "query" in r and "Exemplo" in r, r)
    r = await a.run_tool("search_in_files", {"query": "   "})
    check("blank_query_error", r.startswith("ERRO"), r)
    r = await a.run_tool("search_in_files", {"pattern": "useState"})
    check("alias_pattern", "frontend/src/pages/Home.jsx:1" in r, r)
    r = await a.run_tool("search_in_files", {"text": "Cliques"})
    check("alias_text", "frontend/src/pages/Home.jsx:2" in r, r)
    r = await a.run_tool("search_in_files", {"regex": r"use[A-Z]\w+"})
    check("alias_regex_string", "Home.jsx" in r and "resultado" in r, r)
    r = await a.run_tool("search_in_files", {"query": "useState", "path_glob": "frontend/src/"})
    check("path_glob_folder", "Home.jsx" in r, r)
    r = await a.run_tool("search_in_files", {"query": "useState", "path_glob": "frontend/src/pages"})
    check("path_glob_folder_no_slash", "Home.jsx" in r, r)
    r = await a.run_tool("search_in_files", {"query": "useState", "path": "frontend/src/assets/"})
    check("path_alias_filters_out", r == "Nenhum resultado.", r)
    r = await a.run_tool("search_in_files", {"query": "useState", "path": "frontend/src/pages/Home.jsx"})
    check("path_exact_file", "Home.jsx" in r, r)
    r = await a.run_tool("search_in_files", {"query": "Cliques", "path_glob": "frontend/src/*.jsx"})
    check("path_glob_star_jsx", "Home.jsx" in r, r)
    r = await a.run_tool("search_files", {"query": "Cliques"})
    check("legacy_search_files", "Home.jsx:2" in r, r)
    r = await a.run_tool("search_in_files", {"query": "(", "regex": True})
    check("invalid_regex_error", r.startswith("ERRO"), r)
    print("SUMMARY", sum(res.values()), "/", len(res))


asyncio.run(main())
