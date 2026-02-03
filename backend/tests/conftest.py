import pytest_asyncio
from httpx import AsyncClient

BASE_URL = "http://127.0.0.1:8000"

@pytest_asyncio.fixture
async def client():
    async with AsyncClient(base_url=BASE_URL) as c:
        yield c
