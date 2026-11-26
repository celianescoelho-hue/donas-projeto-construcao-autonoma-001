import asyncio, sys
sys.path.insert(0, "/app/backend")
from dotenv import load_dotenv; load_dotenv("/app/backend/.env")
from agent import Agent, ModelUnavailable


async def main():
    q = asyncio.Queue()
    a = Agent({"id": "unit-test-fallback"}, {"user_id": "unit"}, q)
    seen = []

    async def fake(client, headers, model, messages):
        seen.append(model)
        if model == "qwen/qwen3-coder-next":
            raise ModelUnavailable(429, "rate limited")
        return "Pronto, nada a alterar.", [], None, None, "stop"
    a.call_model = fake
    await a.run("oi", "qwen/qwen3-coder-next", "k", "platform", fallbacks=["qwen/qwen3-coder", "deepseek/deepseek-chat-v3-0324"])
    evs = []
    while not q.empty():
        evs.append(q.get_nowait())
    fb = [e for e in evs if isinstance(e, dict) and e.get("type") == "fallback"]
    errs = [e for e in evs if isinstance(e, dict) and e.get("type") == "error"]
    print("models tried:", seen)
    print("fallback events:", fb)
    print("final model:", a.model, "| errors:", errs)
    assert seen == ["qwen/qwen3-coder-next", "qwen/qwen3-coder"]
    assert a.model == "qwen/qwen3-coder" and len(fb) == 1 and not errs

    # all models down -> clear error, no infinite loop
    b = Agent({"id": "unit-test-fallback2"}, {"user_id": "unit"}, asyncio.Queue())
    async def down(client, headers, model, messages):
        raise ModelUnavailable(429, "down")
    b.call_model = down
    await b.run("oi", "m1", "k", "platform", fallbacks=["m2"])
    print("all-down final model:", b.model)
    assert b.model == "m2"
    print("OK")


asyncio.run(main())
