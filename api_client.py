# api_client.py
import aiohttp

BASE_URL = "https://admin-panel-3cc1cb571383.herokuapp.com/api"

async def fetch_user(telegram_id):
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{BASE_URL}/users/{telegram_id}") as resp:
            return await resp.json() if resp.status == 200 else None

async def create_user(data):
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{BASE_URL}/users/", json=data) as resp:
            return await resp.json()

async def update_user(telegram_id, data):
    async with aiohttp.ClientSession() as session:
        async with session.put(f"{BASE_URL}/users/{telegram_id}", json=data) as resp:
            return await resp.json()

async def fetch_services():
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{BASE_URL}/services/") as resp:
            return await resp.json()

async def fetch_service(service_id):
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{BASE_URL}/services/{service_id}") as resp:
            return await resp.json() if resp.status == 200 else None

async def create_order(data):
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{BASE_URL}/orders/", json=data) as resp:
            return await resp.json()

async def get_next_order_id():
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{BASE_URL}/order_id/next") as resp:
            return await resp.json()
