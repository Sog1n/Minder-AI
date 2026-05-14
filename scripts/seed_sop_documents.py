import asyncio

import httpx


async def main() -> None:
    async with httpx.AsyncClient(base_url="http://127.0.0.1:8000") as client:
        response = await client.post("/api/v1/admin/seed")
        response.raise_for_status()
        print(response.json())


if __name__ == "__main__":
    asyncio.run(main())

