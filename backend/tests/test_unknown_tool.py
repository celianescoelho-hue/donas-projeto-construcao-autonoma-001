import asyncio, sys
sys.path.insert(0, "/app/backend")
from dotenv import load_dotenv; load_dotenv("/app/backend/.env")
from agent import Agent


async def main():
    q = asyncio.Queue()
    a = Agent({"id": "unit-test-project"}, {"user_id": "unit"}, q)
    calls = {"n": 0}

    async def fake(client, headers, model, messages):
        calls["n"] += 1
        return "", [{"id": f"c{calls['n']}", "name": "run_shell_command", "arguments": '{"command":"ls"}'}], None, None, None
    a.call_model = fake
    await a.run("teste", "x", "k", "platform")
    print("model calls:", calls["n"])
    print("text:", a.text.strip()[:160])
    assert calls["n"] == 2


asyncio.run(main())
