# Iteration 7 unit checks: build_messages (HISTORY_LIMIT, archived, FAKE_LOG, done_note, TOOL_RULE),
# fake_claim() true/false cases, MAX_NUDGES exhaustion warning. Uses a scratch project id, cleaned at end.
import asyncio, sys
sys.path.insert(0, "/app/backend")
from dotenv import load_dotenv; load_dotenv("/app/backend/.env")
from core import db
from agent import Agent, fake_claim, HISTORY_LIMIT, MAX_NUDGES, TOOL_RULE

PID = "unit-test-iter7-history"
res = {}


def check(name, cond, info=""):
    res[name] = bool(cond)
    print(("PASS " if cond else "FAIL ") + name, str(info)[:300], flush=True)


async def main():
    for c in ("files", "messages", "versions"):
        await db[c].delete_many({"project_id": PID})
    await db.projects.update_one({"id": PID}, {"$set": {"id": PID, "user_id": "unit", "name": "unit"}}, upsert=True)
    try:
        # 12 messages: 2 archived oldest + 10 active
        base = "2026-01-01T00:00:%02d+00:00"
        docs = []
        for i in range(12):
            role = "user" if i % 2 == 0 else "assistant"
            d = {"id": f"m{i}", "project_id": PID, "role": role, "created_at": base % i,
                 "content": f"msg{i}" + ("\n[Alterações: frontend/src/X.js (+1/-0)]" if role == "assistant" else ""),
                 "changes": [{"path": f"frontend/src/F{i}.js", "op": "edit"}] if role == "assistant" else []}
            if i >= 10:
                d["archived"] = True  # newest 2 archived -> must be ignored
            docs.append(d)
        await db.messages.insert_many(docs)
        a = Agent({"id": PID}, {"user_id": "unit"}, asyncio.Queue())
        msgs = await a.build_messages("novo pedido")
        sysm = msgs[0]["content"]
        hist = msgs[1:]
        contents = [m["content"] for m in hist]
        print("history:", contents)
        check("history_limit_6_plus_prompt", len(hist) == HISTORY_LIMIT + 1 and HISTORY_LIMIT == 6, len(hist))
        check("archived_ignored", not any(c.startswith("msg10") or c.startswith("msg11") for c in contents))
        check("last6_nonarchived_msg4_to_msg9", [c.split("\n")[0] for c in contents[:6]] == [f"msg{i}" for i in range(4, 10)], contents[:6])
        check("fake_log_stripped", not any("[Alterações" in c for c in contents))
        check("prompt_appended_last", hist[-1] == {"role": "user", "content": "novo pedido"})
        check("tool_rule_in_system", TOOL_RULE in sysm)
        check("done_note_in_system", "ALTERAÇÕES JÁ FEITAS EM TURNOS ANTERIORES" in sysm and "frontend/src/F5.js (edit)" in sysm and "F11.js" not in sysm, sysm[-400:])

        # fake_claim
        for t in ["Claro, posso ajudar", "Olá! O que você gostaria de criar hoje?", "Vou ler o arquivo primeiro.", ""]:
            check(f"fake_claim_false:{t[:20]}", not fake_claim(t))
        for t in ["Arquivo criado: frontend/src/App.js", "[Alterações: a.js (+1/-0)]", "0 arquivo(s)", "Atualizei o componente Home", "Os arquivos foram atualizados."]:
            check(f"fake_claim_true:{t[:20]}", fake_claim(t))

        # MAX_NUDGES exhaustion
        await db.messages.delete_many({"project_id": PID})
        b = Agent({"id": PID}, {"user_id": "unit"}, asyncio.Queue())
        seen = []

        async def fake(client, headers, model, messages):
            seen.append(b.force_tools)
            return ("Arquivo criado: frontend/src/App.js", [], None, None, None)
        b.call_model = fake
        await b.run("crie o App", "x", "k", "platform")
        print("nudge flags", seen, "warnings", b.warnings, "text", b.text)
        check("max_nudges_calls", len(seen) == MAX_NUDGES + 1 and seen == [False, True, True], seen)
        check("max_nudges_final_warning", any("afirmou ter alterado arquivos, mas não chamou nenhuma ferramenta" in w for w in b.warnings), b.warnings)
        saved = await db.messages.find_one({"project_id": PID, "role": "assistant"}, {"_id": 0})
        check("saved_msg_has_warnings", saved and len(saved.get("warnings") or []) == 2, saved and saved.get("warnings"))
        print("saved content:", repr(saved and saved.get("content")))
    finally:
        for c in ("files", "messages", "versions"):
            await db[c].delete_many({"project_id": PID})
        await db.projects.delete_one({"id": PID})
    print(f"RESULT {sum(res.values())}/{len(res)}")


asyncio.run(main())
