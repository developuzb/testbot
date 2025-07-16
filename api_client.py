import aiohttp
from datetime import datetime
import pytz

BASE_URL = "https://admin-panel-3cc1cb571383.herokuapp.com/api"

# 🧾 XIZMATLAR

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
        async with session.post(f"{BASE_URL}/services/users/track", json=payload) as resp:
            return await resp.json()

async def fetch_user_profile(user_id: int):
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{BASE_URL}/services/users/{user_id}") as resp:
            data = await resp.json()
            return {
                "name": data.get("ism"),
                "phone": data.get("telefon"),
                "balance": data.get("balans"),
                "actions_count": data.get("amallar_soni"),
                "badge": data.get("badge")
            }


# 💰 CASHBACK

async def add_cashback_log(user_id: int, service_id: int, amount: int, direction: str):
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{BASE_URL}/services/cashback-log/", json={
            "user_id": user_id,
            "service_id": service_id,
            "amount": amount,
            "direction": direction
        }) as resp:
            return await resp.json()

async def delete_cashback_log(log_id: int):
    async with aiohttp.ClientSession() as session:
        async with session.delete(f"{BASE_URL}/services/cashback-log/{log_id}") as resp:
            return await resp.json()

# 📈 METRIKA / XABARLAR

async def send_webhook_report(event_type: str, user_id: int, service_id: int):
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{BASE_URL}/services/webhook/send-report", json={
            "type": event_type,
            "user_id": user_id,
            "service_id": service_id
        }) as resp:
            return await resp.json()

# 🗓 Metrika – sana bilan (ixtiyoriy, agar kerak bo‘lsa)

async def update_metrics(event: str, group: str = None):
    from datetime import datetime
    import pytz
    now = datetime.now(pytz.timezone("Asia/Tashkent")).strftime("%Y-%m-%d")
    payload = {"event": event, "date": now}
    if group:
        payload["group"] = group

    timeout = aiohttp.ClientTimeout(total=10)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(f"{BASE_URL}/metrics/", json=payload) as resp:
            return await resp.json()

async def update_user(telegram_id, data):
    async with aiohttp.ClientSession() as session:
        async with session.put(f"{BASE_URL}/users/{telegram_id}", json=data) as resp:
            return await resp.json()

async def create_order(data):
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{BASE_URL}/orders/", json=data) as resp:
            return await resp.json()

async def update_order_status(order_id, status):
    async with aiohttp.ClientSession() as session:
        async with session.put(
            f"{BASE_URL}/orders/{order_id}",
            json={"payment_status": status}
        ) as resp:
            return await resp.json() if resp.status == 200 else None

# 🚀 next order_id olish
async def get_next_order_number(service_id: int) -> int:
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{BASE_URL}/services/{service_id}") as resp:
            if resp.status != 200:
                raise Exception(f"❌ Xizmat topilmadi: status={resp.status}")
            data = await resp.json()
            last = data.get("last_order") or 173000
            return last + 1

# 🧾 last_order ni yangilash
async def update_last_order(service_id: int, new_order_id: int):
    async with aiohttp.ClientSession() as session:
        async with session.patch(f"{BASE_URL}/services/{service_id}", json={"last_order": new_order_id}) as resp:
            if resp.status not in (200, 204):
                raise Exception(f"❌ last_order yangilanmadi: status={resp.status}")

async def get_order(user_id: int, order_id: int):
    url = f"{BASE_URL}/orders/{order_id}?user_id={user_id}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                return await resp.json()
            else:
                return None
