"""性能抽测脚本（B6b 验收：单机并发会话 / 首 token / 检索 P95）。

用法（需后端已启动）：
    python scripts/perf_smoke.py --base http://127.0.0.1:8000 --concurrency 50 --retrieval 30
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
import uuid

import httpx


async def login(base: str) -> str:
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"{base}/api/auth/login",
            json={"username": "admin", "password": "admin123"},
        )
        resp.raise_for_status()
        return resp.json()["data"]["access_token"]


async def pick_kb(base: str, token: str) -> str:
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"{base}/api/knowledge-bases", headers={"Authorization": f"Bearer {token}"}
        )
        kbs = resp.json()["data"]
        kb = next((k for k in kbs if k["doc_count"] > 0), kbs[0])
        return kb["id"]


async def chat_once(
    client: httpx.AsyncClient, base: str, token: str, kb_id: str
) -> tuple[bool, float | None]:
    """一次对话：返回 (成功, 首 token 耗时秒)。"""
    started = time.perf_counter()
    first_token_at = None
    try:
        async with client.stream(
            "POST",
            f"{base}/api/chat",
            headers={"Authorization": f"Bearer {token}"},
            json={"kb_ids": [kb_id], "message": "商品签收后几天可以退货？"},
        ) as resp:
            async for line in resp.aiter_lines():
                if line.startswith("data:") and '"content"' in line and first_token_at is None:
                    first_token_at = time.perf_counter() - started
        return True, first_token_at
    except Exception:  # noqa: BLE001
        return False, None


async def retrieval_once(
    client: httpx.AsyncClient, base: str, token: str, kb_id: str
) -> float | None:
    started = time.perf_counter()
    try:
        resp = await client.post(
            f"{base}/api/retrieval/test",
            headers={"Authorization": f"Bearer {token}"},
            json={"kb_ids": [kb_id], "query": "商品签收后几天可以退货？", "top_k": 3},
        )
        resp.raise_for_status()
        return time.perf_counter() - started
    except Exception:  # noqa: BLE001
        return None


def p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))]


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    parser.add_argument("--concurrency", type=int, default=50)
    parser.add_argument("--retrieval", type=int, default=30)
    args = parser.parse_args()

    token = await login(args.base)
    kb_id = await pick_kb(args.base, token)

    # 并发会话：首 token 延迟与成功率（目标：≥50 并发、首 token ≤2s）
    async with httpx.AsyncClient(timeout=120) as client:
        started = time.perf_counter()
        results = await asyncio.gather(
            *[chat_once(client, args.base, token, kb_id) for _ in range(args.concurrency)]
        )
        total_time = time.perf_counter() - started
    ok = sum(1 for s, _ in results if s)
    first_tokens = [t for _, t in results if t is not None]
    print(json.dumps({
        "chat_concurrency": args.concurrency,
        "chat_success": f"{ok}/{len(results)}",
        "chat_total_seconds": round(total_time, 2),
        "first_token_avg_ms": round(statistics.mean(first_tokens) * 1000, 1) if first_tokens else None,
        "first_token_p95_ms": round(p95(first_tokens) * 1000, 1) if first_tokens else None,
    }, ensure_ascii=False, indent=2))

    # 检索 P95（目标 ≤1s）
    async with httpx.AsyncClient(timeout=120) as client:
        durations = [d for d in await asyncio.gather(
            *[retrieval_once(client, args.base, token, kb_id) for _ in range(args.retrieval)]
        ) if d is not None]
    print(json.dumps({
        "retrieval_calls": len(durations),
        "retrieval_avg_ms": round(statistics.mean(durations) * 1000, 1) if durations else None,
        "retrieval_p95_ms": round(p95(durations) * 1000, 1) if durations else None,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
