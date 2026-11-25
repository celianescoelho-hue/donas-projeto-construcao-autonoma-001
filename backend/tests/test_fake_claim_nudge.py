import asyncio, sys
sys.path.insert(0, "/app/backend")
from dotenv import load_dotenv; load_dotenv("/app/backend/.env")
from core import db
from agent import Agent

PID = "unit-test-nudge"


async def main():
    await db.files.delete_many({"project_id": PID})
    await db.projects.update_one({"id": PID}, {"$set": {"id": PID, "user_id": "unit", "name": "unit"}}, upsert=True)
    a = Agent({"id": PID}, {"user_id": "unit"}, asyncio.Queue())
    seen = []
    script = [
        ("Arquivo criado: frontend/src/App.js\n[Alterações: frontend/src/App.js (+5/-0)]", []),
        ("", [{"id": "c1", "name": "create_file", "arguments": '{"path":"frontend/src/App.js","content":"export default function App(){return null}"}'}]),
        ("Pronto, criei o App.js.", []),
    ]

    async def fake(client, headers, model, messages):
        seen.append((a.force_tools, messages[-1]["content"][:40] if messages[-1].get("content") else messages[-1]["role"]))
        return (*script[len(seen) - 1], None, None, None)
    a.call_model = fake
    await a.run("crie o App", "x", "k", "platform")
    print("calls:", len(seen), "force_tools flags:", [s[0] for s in seen])
    print("warnings:", a.warnings)
    print("changes:", [c["path"] for c in a.change_cards])
    print("text:", a.text.strip())
    assert len(seen) == 3 and seen[1][0] is True and a.change_cards and "Arquivo criado" not in a.text
    await db.files.delete_many({"project_id": PID})
    await db.messages.delete_many({"project_id": PID})
    await db.versions.delete_many({"project_id": PID})
    await db.projects.delete_one({"id": PID})
    print("OK")


asyncio.run(main())
