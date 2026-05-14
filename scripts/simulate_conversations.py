import asyncio

import httpx


SCENARIOS = [
    {
        "worker_id": "maria",
        "transcript": (
            "The AI keeps telling me to use the standard cycle for Hotel A polyester. "
            "That's completely wrong. Hotel A polyester always shrinks when mixed with cotton. "
            "You MUST separate them or you'll ruin the batch."
        ),
    },
    {
        "worker_id": "carlos",
        "transcript": (
            "Station 3 always overheats after lunch on Tuesdays. "
            "I drop the current by 5% every time. The AI told me 3% but that is not enough."
        ),
    },
    {
        "worker_id": "worker_a",
        "transcript": "The dryer at station 2 should run at 80 degrees Celsius.",
    },
    {
        "worker_id": "worker_b",
        "transcript": "No, the dryer at station 2 runs at 75 degrees. I checked this morning.",
    },
    {
        "worker_id": "new_hire",
        "transcript": "Haha I bet this machine runs on hopes and dreams. Also maybe 90 degrees, just guessing lol.",
    },
]


async def main() -> None:
    async with httpx.AsyncClient(base_url="http://127.0.0.1:8000", timeout=10) as client:
        await client.post("/api/v1/admin/seed")
        for scenario in SCENARIOS:
            response = await client.post("/api/v1/conversations/ingest", json=scenario)
            response.raise_for_status()
            conversation_id = response.json()["conversation_id"]
            await asyncio.sleep(0.5)
            status = await client.get(f"/api/v1/conversations/{conversation_id}/status")
            print(conversation_id, status.json())
        metrics = await client.get("/api/v1/metrics/dashboard")
        print(metrics.json())


if __name__ == "__main__":
    asyncio.run(main())

