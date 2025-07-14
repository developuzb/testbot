import aiohttp
from datetime import datetime
import pytz

BASE_URL = "https://admin-panel-3cc1cb571383.herokuapp.com/api"

# 🧾 XIZMATLAR

async def fetch_services():
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{BASE_URL}/services/") as resp:
            return await resp.json()

async def fetch_service(service_id: int):
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{BASE_URL}/services/{service_id}") as resp:
            return await resp.json()

async def update_service_stats(service_id: int, cashback_given: int):
    async with aiohttp.ClientSession() as session:
        async with session.patch(f"{BASE_URL}/services/{service_id}/stats", json={
            "cashback_given": cashback_given
        }) as resp:
            return await resp.json()

# 👤 FOYDALANUVCHILAR

async def track_user(user_id: int, name: str, phone: str):
    payload = {"id": user_id, "name": name, "phone": phone}
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{BASE_URL}/users/track", json=payload) as resp:
            return await resp.json()

async def fetch_user_profile(user_id: int):
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{BASE_URL}/users/{user_id}") as resp:
            return await resp.json()

# 💰 CASHBACK

async def add_cashback_log(user_id: int, service_id: int, amount: int, direction: str):
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{BASE_URL}/cashback-log/", json={
            "user_id": user_id,
            "service_id": service_id,
            "amount": amount,
            "direction": direction
        }) as resp:
            return await resp.json()

async def delete_cashback_log(log_id: int):
    async with aiohttp.ClientSession() as session:
        async with session.delete(f"{BASE_URL}/cashback-log/{log_id}") as resp:
            return await resp.json()

# 📈 METRIKA / XABARLAR

async def send_webhook_report(event_type: str, user_id: int, service_id: int):
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{BASE_URL}/webhook/send-report", json={
            "type": event_type,
            "user_id": user_id,
            "service_id": service_id
        }) as resp:
            return await resp.json()

# 🗓 Metrika – sana bilan (ixtiyoriy, agar kerak bo‘lsa)

async def update_metrics(event: str, group: str = None):
    now = datetime.now(pytz.timezone("Asia/Tashkent")).strftime("%Y-%m-%d")
    payload = {"event": event, "date": now}
    if group:
        payload["group"] = group
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{BASE_URL}/metrics/", json=payload) as resp:
            return await resp.json()

async def update_user(telegram_id, data):
    async with aiohttp.ClientSession() as session:
        async with session.put(f"{BASE_URL}/users/{telegram_id}", json=data) as resp:
            return await resp.json()
