import os
from uuid import uuid4
import json
import re
import pytz
import random
import telegram.error
from datetime import datetime, time
from telegram.ext import ContextTypes
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton, InlineQuery
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, ConversationHandler, MessageHandler, filters
import logging
from PIL import Image, ImageDraw, ImageFont
import io
import qrcode
from PIL import Image, ImageDraw, ImageFont, ImageOps
import math
import uuid
import aiofiles
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
executor = ThreadPoolExecutor(max_workers=2)
import json
import aiohttp
from aiogram import types
from api_client import track_user, create_order, update_order_status, fetch_user_profile, get_next_order_number, update_last_order, fetch_service
assert os.path.exists("api_client.py"), "❌ api_client.py topilmadi"


API_URL = "https://admin-panel-3cc1cb571383.herokuapp.com/api/services/"
DEFAULT_IMAGE = "https://i.ibb.co/4w8mVTyH/Chat-GPT-Image-Jul-9-2025-04-30-59-AM.png"
 
logger = logging.getLogger(__name__)

def load_services_to_cache(context):
    services = get_services(admin=True)
    context.bot_data['services'] = services
    return services

def get_services(admin=False, context=None):
    if context and 'services' in context.bot_data:
        return [s for s in context.bot_data['services'] if s.get('active', True) or admin]
    return load_services_to_cache(context)

def create_stats_graph(orders):
    img = Image.new('RGB', (400, 300), color='white')
    draw = ImageDraw.Draw(img)
    last_update = context.bot_data.get('stats_graph_last_update')
    if last_update and (datetime.now() - datetime.fromisoformat(last_update)).seconds < 3600:
        return context.bot_data['stats_graph']
    img = Image.new('RGB', (400, 300), color='white')
    
    try:
        font = ImageFont.truetype("arial.ttf", 14)
    except IOError:
        font = ImageFont.load_default()

    counts = Counter(o['timestamp'].split()[0] for o in orders)
    days = sorted(counts.keys())[-7:]
    values = [counts.get(day, 0) for day in days]

    max_count = max(values, default=1)
    for i, (day, count) in enumerate(zip(days, values)):
        y = 250 - (count / max_count * 200)
        draw.rectangle((50 + i * 50, y, 80 + i * 50, 250), fill='blue')
        draw.text((50 + i * 50, 270), day[-5:], font=font, fill='black')

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    context.bot_data['stats_graph'] = buffer
    context.bot_data['stats_graph_last_update'] = datetime.now().isoformat()
    return buffer


def is_working_hours():
    now = datetime.now(pytz.timezone('Asia/Tashkent')).time()
    return time(8, 30) <= now <= time(19, 30)

def get_admin_main_buttons():
    return [
        [InlineKeyboardButton("📦 Xizmatlar", callback_data="admin_services"),
         InlineKeyboardButton("📋 Buyurtmalar", callback_data="admin_orders")],
        [InlineKeyboardButton("💸 To‘lovlar", callback_data="admin_payments"),
         InlineKeyboardButton("👥 Foydalanuvchilar", callback_data="admin_users")],
        [InlineKeyboardButton("📊 Statistika", callback_data="admin_stats"),
         InlineKeyboardButton("⚙️ Sozlamalar", callback_data="admin_settings")]
    ]

def get_admin_services_buttons():
    return [
        [InlineKeyboardButton("➕ Yangi xizmat", callback_data="add_service"),
         InlineKeyboardButton("📋 Ro‘yxat", callback_data="list_services")],
        [InlineKeyboardButton("✏️ Tahrirlash", callback_data="edit_service"),
         InlineKeyboardButton("🗑 O‘chirish", callback_data="delete_service")],
        [InlineKeyboardButton("🔍 Qidirish", callback_data="search_service"),
         InlineKeyboardButton("📦 Toifalar", callback_data="group_by_category")],
        [InlineKeyboardButton("🔄 Faollik", callback_data="toggle_service_visibility"),
         InlineKeyboardButton("⬅️ Bosh sahifa", callback_data="admin_main")]
    ]

def get_admin_orders_buttons():
    return [
        [InlineKeyboardButton("🆕 Yangi", callback_data="orders_new"),
         InlineKeyboardButton("✅ Bajarilgan", callback_data="orders_done")],
        [InlineKeyboardButton("❌ Bekor qilingan", callback_data="orders_cancelled"),
         InlineKeyboardButton("🔍 Qidirish", callback_data="orders_search")],
        [InlineKeyboardButton("⬅️ Bosh sahifaga", callback_data="admin_main")]
    ]

def get_admin_payments_buttons():
    return [
        [InlineKeyboardButton("🧾 Kelgan cheklar", callback_data="payments_checks"),
         InlineKeyboardButton("✅ Tasdiqlangan", callback_data="payments_approved")],
        [InlineKeyboardButton("❌ Rad etilgan", callback_data="payments_rejected"),
         InlineKeyboardButton("⬅️ Bosh sahifaga", callback_data="admin_main")]
    ]

def get_admin_users_buttons():
    return [
        [InlineKeyboardButton("📋 Ro‘yxat", callback_data="users_list"),
         InlineKeyboardButton("🔍 Qidirish", callback_data="users_search")],
        [InlineKeyboardButton("⬅️ Bosh sahifaga", callback_data="admin_main")]
    ]

def get_admin_stats_buttons():
    return [
        [InlineKeyboardButton("📈 Bugungi soni", callback_data="stats_today"),
         InlineKeyboardButton("🔝 Eng mashhur xizmat", callback_data="stats_top")],
        [InlineKeyboardButton("📆 7 kunlik graf", callback_data="stats_week"),
         InlineKeyboardButton("⬅️ Bosh sahifaga", callback_data="admin_main")]
    ]

def get_admin_settings_buttons():
    return [
        [InlineKeyboardButton("💳 To‘lov kartasi", callback_data="settings_card"),
         InlineKeyboardButton("🕒 Ish vaqti", callback_data="settings_hours")],
        [InlineKeyboardButton("📢 Kanal havolasi", callback_data="settings_channel"),
         InlineKeyboardButton("👑 Admin ID", callback_data="settings_admin")],
        [InlineKeyboardButton("⬅️ Bosh sahifaga", callback_data="admin_main")]
    ]
    

async def fetch_user(telegram_id: int):
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{BASE_URL}/users/{telegram_id}") as resp:
            if resp.status == 200:
                data = await resp.json()
                # Defaultlar bilan to‘ldirish (agar kerak bo‘lsa)
                data.setdefault('phone', None)
                data.setdefault('orders', [])
                data.setdefault('rated_identifiers', [])
                return data
            else:
                return None
import qrcode
from PIL import Image, ImageDraw, ImageFont, ImageOps
import io
import math

def create_invoice_image(order, amount):
    # Rasm o‘lchamlari
    width, height = 600, 850  # QR-kod uchun balandlik
    img = Image.new('RGB', (width, height), color='#FFFFFF')  # Oq fon
    draw = ImageDraw.Draw(img)

    # Shrift sozlamalari (kattaroq matnlar)
    try:
        font_title = ImageFont.truetype("cour.ttf", 24)  # Kattaroq sarlavha
        font_body = ImageFont.truetype("cour.ttf", 20)   # Kattaroq asosiy matn
        font_small = ImageFont.truetype("cour.ttf", 14)  # Kattaroq pastki yozuv
    except IOError:
        font_title = ImageFont.load_default()
        font_body = ImageFont.load_default()
        font_small = ImageFont.load_default()

    # Logo qo‘shish (faqat chekda bo‘ladi, bu yerda ishlamaydi)
    y = 40

    # Terminal uslubidagi sarlavha
    header = "TEXNOSET XIZMATLARI"
    header_bbox = draw.textbbox((0, 0), header, font=font_title)
    header_width = header_bbox[2] - header_bbox[0]
    draw.text(((width - header_width) // 2, y), header, font=font_title, fill='#000000')
    y += 40
    draw.text((50, y), "-" * 40, font=font_body, fill='#000000')
    y += 20

    # Invoys sarlavhasi
    title = "TO‘LOV INVOYSI"
    title_bbox = draw.textbbox((0, 0), title, font=font_title)
    title_width = title_bbox[2] - title_bbox[0]
    draw.text(((width - title_width) // 2, y), title, font=font_title, fill='#000000')
    y += 50

    # Buyurtma ma‘lumotlari
    details = [
        f"Buyurtma: #{order['order_id']}",
        f"Xizmat: {order['service_name']}",
        f"Narxi: {amount} so‘m",
        f"Vaqt: {order['timestamp']}"
    ]
    for line in details:
        draw.text((50, y), line, font=font_body, fill='#000000')
        y += 30

    # Ajratgich
    y += 10
    draw.text((50, y), "=" * 40, font=font_body, fill='#000000')
    y += 20

    # To‘lov ma‘lumotlari
    draw.text((50, y), "To‘lov Ma‘lumotlari:", font=font_body, fill='#000000')
    y += 30
    draw.text((50, y), "Karta: 8600 3104 7319 9081", font=font_body, fill='#000000')
    y += 30
    draw.text((50, y), f"Summa: {amount} so‘m", font=font_body, fill='#000000')
    y += 40

    # Ajratgich
    draw.text((50, y), "-" * 40, font=font_body, fill='#000000')
    y += 20

    # Pastki yozuv
    footer = "Texnoset – Ishonchli Xizmat!"
    footer_bbox = draw.textbbox((0, 0), footer, font=font_small)
    footer_width = footer_bbox[2] - footer_bbox[0]
    draw.text(((width - footer_width) // 2, y), footer, font=font_small, fill='#000000')
    y += 20
    contact = "Aloqa: +998 77 009 71 71"
    contact_bbox = draw.textbbox((0, 0), contact, font=font_small)
    contact_width = contact_bbox[2] - contact_bbox[0]
    draw.text(((width - contact_width) // 2, y), contact, font=font_small, fill='#000000')
    y += 30

    # QR-kod qo‘shish
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=4,
        border=2,
    )
    qr.add_data("https://t.me/texnosetUZ")
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white").convert('RGB')
    qr_img = qr_img.resize((100, 100), Image.Resampling.LANCZOS)
    qr_x = (width - 100) // 2
    img.paste(qr_img, (qr_x, y))
    y += 110
    qr_label = "Kanalimizga obuna bo‘ling!"
    qr_label_bbox = draw.textbbox((0, 0), qr_label, font=font_small)
    qr_label_width = qr_label_bbox[2] - qr_label_bbox[0]
    draw.text(((width - qr_label_width) // 2, y), qr_label, font=font_small, fill='#000000')

    # Rasmni saqlash
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer

def create_receipt_image(order, amount, confirmation_time):
    # Rasm o‘lchamlari
    width, height = 600, 900
    img = Image.new('RGB', (width, height), color='#FFFFFF')  # Oq fon
    draw = ImageDraw.Draw(img)

    # Shrift sozlamalari
    try:
        font_title = ImageFont.truetype("cour.ttf", 24)
        font_body = ImageFont.truetype("cour.ttf", 20)
        font_small = ImageFont.truetype("cour.ttf", 14)
        font_stamp = ImageFont.truetype("cour.ttf", 18)  # Kichikroq muhr shrifti
    except IOError:
        font_title = ImageFont.load_default()
        font_body = ImageFont.load_default()
        font_small = ImageFont.load_default()
        font_stamp = ImageFont.load_default()

    # Logo qo‘shish (yuqorida, markazda)
    try:
        logo = Image.open("logo.png")
        logo_width, logo_height = logo.size
        scale = min(200 / logo_width, 200 / logo_height)
        new_size = (int(logo_width * scale), int(logo_height * scale))
        logo = logo.resize(new_size, Image.Resampling.LANCZOS)
        logo_x = (width - new_size[0]) // 2
        img.paste(logo, (logo_x, 20), logo if logo.mode == 'RGBA' else None)
        y = 20 + new_size[1] + 20
    except FileNotFoundError:
        y = 40

    # Terminal uslubidagi sarlavha
    header = "TEXNOSET XIZMATLARI"
    header_bbox = draw.textbbox((0, 0), header, font=font_title)
    header_width = header_bbox[2] - header_bbox[0]
    draw.text(((width - header_width) // 2, y), header, font=font_title, fill='#000000')
    y += 40
    draw.text((50, y), "-" * 40, font=font_body, fill='#000000')
    y += 20

    # Chek sarlavhasi
    title = "TO‘LOV CHEKI"
    title_bbox = draw.textbbox((0, 0), title, font=font_title)
    title_width = title_bbox[2] - title_bbox[0]
    draw.text(((width - title_width) // 2, y), title, font=font_title, fill='#000000')
    y += 50

    # Buyurtma ma‘lumotlari
    details = [
        f"Buyurtma: #{order['order_id']}",
        f"Xizmat: {order['service_name']}",
        f"Summa: {amount} so‘m",
        f"Vaqt: {order['timestamp']}",
        f"Tasdiq: {confirmation_time}"
    ]
    for line in details:
        draw.text((50, y), line, font=font_body, fill='#000000')
        y += 30

    # Ajratgich
    y += 10
    draw.text((50, y), "=" * 40, font=font_body, fill='#000000')
    y += 20

    # To‘lov ma‘lumotlari
    draw.text((50, y), "To‘lov Ma‘lumotlari:", font=font_body, fill='#000000')
    y += 30
    draw.text((50, y), "Karta: 8600 3104 7319 9081", font=font_body, fill='#000000')
    y += 30
    draw.text((50, y), "Holati: To‘landi", font=font_body, fill='#000000')
    y += 40

    # Realistik to‘rtburchak muhr (kichikroq)
    stamp_x, stamp_y = 350, y
    stamp_text = "TO‘LANDI"
    stamp_img = Image.new('RGBA', (150, 100), (0, 0, 0, 0))  # Kichikroq hajm
    stamp_draw = ImageDraw.Draw(stamp_img)
    stamp_draw.rectangle((10, 10, 140, 90), outline='#000080', width=2)  # To‘rtburchak, qalin chet
    stamp_bbox = stamp_draw.textbbox((0, 0), stamp_text, font=font_stamp)
    stamp_width = stamp_bbox[2] - stamp_bbox[0]
    stamp_height = stamp_bbox[3] - stamp_bbox[1]
    # Soya effekti
    stamp_draw.text((30 + 2, 40 + 2), stamp_text, font=font_stamp, fill=(0, 0, 128, 100))
    # Asosiy matn
    stamp_draw.text((30, 40), stamp_text, font=font_stamp, fill='#000080')
    # Engil burish
    stamp_img = stamp_img.rotate(5, expand=True, resample=Image.Resampling.BICUBIC)
    img.paste(stamp_img, (stamp_x - 25, stamp_y - 25), stamp_img)
    y += 100

    # Ajratgich
    draw.text((50, y), "-" * 40, font=font_body, fill='#000000')
    y += 20

    # Pastki yozuv
    footer = "Texnoset – Ishonchli Xizmat!"
    footer_bbox = draw.textbbox((0, 0), footer, font=font_small)
    footer_width = footer_bbox[2] - footer_bbox[0]
    draw.text(((width - footer_width) // 2, y), footer, font=font_small, fill='#000000')
    y += 20
    contact = "Aloqa: +998 77 009 71 71"
    contact_bbox = draw.textbbox((0, 0), contact, font=font_small)
    contact_width = contact_bbox[2] - contact_bbox[0]
    draw.text(((width - contact_width) // 2, y), contact, font=font_small, fill='#000000')
    y += 30

    # QR-kod qo‘shish
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=4,
        border=2,
    )
    qr.add_data("https://t.me/texnosetUZ")
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white").convert('RGB')
    qr_img = qr_img.resize((100, 100), Image.Resampling.LANCZOS)
    qr_x = (width - 100) // 2
    img.paste(qr_img, (qr_x, y))
    y += 110
    qr_label = "Kanalimizga obuna bo‘ling!"
    qr_label_bbox = draw.textbbox((0, 0), qr_label, font=font_small)
    qr_label_width = qr_label_bbox[2] - qr_label_bbox[0]
    draw.text(((width - qr_label_width) // 2, y), qr_label, font=font_small, fill='#000000')

    # Rasmni saqlash
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer    
      


import logging
import pytz
import asyncio
import re
import random
from telegram.ext import filters as tg_filters
from datetime import datetime, time
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime, time
from uuid import uuid4
def is_working_hours():
    now = datetime.now(pytz.timezone('Asia/Tashkent')).time()
    return time(8, 30) <= now <= time(19, 30)


yumshoq_startlar = [
    "😊 Endi bemalol xizmatni tanlashingiz mumkin.\nBuyurtma berish juda oson va atigi 1 daqiqa!",
    "🔎 Qidiruv tugmasini bosing yoki xizmat nomini yozing — biz yordam beramiz!",
    "💼 Xizmatni tanlang — biz sifatli xizmat bilan xizmatdamiz!",
    "🚀 Hammasi tayyor! Endi buyurtma berish uchun atigi bir necha bosqich kifoya.",
    "✅ Buyurtma berish qulay, tez va ishonchli! Qani boshlaymizmi?"
]

def work_time_string():
    return "🕒 Ish vaqti: har kuni 08:30 dan 19:30 gacha."

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup,
    ReplyKeyboardRemove, KeyboardButton, InputTextMessageContent, InlineQueryResultArticle
)
from telegram.ext import (
    Application, ApplicationBuilder, ContextTypes, CommandHandler,
    MessageHandler, filters, ConversationHandler, CallbackQueryHandler, InlineQueryHandler
)
from telegram.constants import ParseMode
import difflib

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)
TOKEN = os.getenv("BOT_TOKEN")

try:
    ADMIN_ID = int(os.getenv("ADMIN_ID"))
    GROUP_ID = int(os.getenv("GROUP_ID"))
except (TypeError, ValueError) as e:
    logger.critical(f".env faylida xato: ADMIN_ID yoki GROUP_ID noto'g'ri. {e}")
    raise SystemExit("Bot ishga tushmadi: .env faylini tekshiring.")

# Buyurtma uchun xabar andozasi (API asosida ishlatiladi)
ORDER_MESSAGE_TEMPLATE = (
    "📦 <b>Yangi buyurtma!</b>\n\n"
    "🧾 Buyurtma raqami: <b>#{order_id}</b>\n"
    "🆔 Xizmat ID: <code>{service_id}</code>\n"
    "📌 Nomi: <b>{service_name}</b>\n"
    "📞 Raqam: <code>{phone}</code>\n"
    "📱 Aloqa usuli: <i>{contact_method}</i>\n"
    "⏰ Aloqa vaqti: <i>{contact_time}</i>"
)

# States
(ASK_ACTION, ASK_DELETE_ID, ADD_SERVICE_ID, ADD_SERVICE_NAME, ADD_SERVICE_PRICE,
 ADD_SERVICE_PAYMENTS, ADD_SERVICE_IMAGE, ADD_SERVICE_CATEGORY, WAIT_PHONE,
 WAIT_CONTACT_METHOD, WAIT_MANUAL_CONTACT_METHOD, WAIT_CONTACT_TIME, ASKING_NAME,
 EDIT_SERVICE_ID, EDIT_SERVICE_FIELD, EDIT_SERVICE_NAME, EDIT_SERVICE_PRICE,
 EDIT_SERVICE_PAYMENTS, EDIT_SERVICE_IMAGE, EDIT_SERVICE_CATEGORY, DELETE_SERVICE_ID,
 SEARCH_SERVICE, TOGGLE_VISIBILITY_ID, GROUP_BY_CATEGORY, SETTINGS_ADMIN) = range(25)  # SETTINGS_ADMIN qo'shildi 

def get_services(admin=False):
    try:
        with open(DATA_FILE, encoding='utf-8') as f:
            services = json.load(f)
        if not admin:
            services = [s for s in services if s.get('active', True)]
        return services
    except FileNotFoundError:
        logger.info("ℹ services.json fayli topilmadi, yangi yaratiladi")
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump([], f)
        return []
    except Exception as e:
        logger.error(f"❌ services.json faylini o‘qishda xato: {e}")
        return []


def save_services(services):
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(services, f, ensure_ascii=False, indent=2)
        logger.info("✅ services.json fayliga saqlandi")
    except Exception as e:
        logger.error(f"❌ services.json faylini saqlashda xato: {e}")

def migrate_services():
    services = get_services(admin=True)
    for s in services:
        if 'category' not in s:
            s['category'] = 'Belgilanmagan'
        if 'active' not in s:
            s['active'] = True
    save_services(services)
        

def create_click_url(order_id, amount):
    return f"https://my.click.uz/pay/?service_id=999999999&merchant_id=398062629&amount={amount}&transaction_param={order_id}"

# Transliteration function
def transliterate(text, to_latin=True):
    replacements = {
        'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'yo', 'ж': 'j',
        'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm', 'н': 'n', 'о': 'o',
        'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u', 'ф': 'f', 'х': 'x', 'ц': 'ts',
        'ч': 'ch', 'ш': 'sh', 'щ': 'sh', 'ъ': '', 'ы': 'i', 'ь': '', 'э': 'e',
        'ю': 'yu', 'я': 'ya', 'қ': 'q', 'ҳ': 'h', 'ғ': 'g‘', 'ў': 'o‘',
        'А': 'A', 'Б': 'B', 'В': 'V', 'Г': 'G', 'Д': 'D', 'Е': 'E', 'Ё': 'Yo', 'Ж': 'J',
        'З': 'Z', 'И': 'I', 'Й': 'Y', 'К': 'K', 'Л': 'L', 'М': 'M', 'Н': 'N', 'О': 'O',
        'П': 'P', 'Р': 'R', 'С': 'S', 'Т': 'T', 'У': 'U', 'Ф': 'F', 'Х': 'X', 'Ц': 'Ts',
        'Ч': 'Ch', 'Ш': 'Sh', 'Щ': 'Sh', 'Ъ': '', 'Ы': 'I', 'Ь': '', 'Э': 'E',
        'Ю': 'Yu', 'Я': 'Ya', 'Қ': 'Q', 'Ҳ': 'H', 'Ғ': 'G‘', 'Ў': 'O‘'
    }
    if not to_latin:
        replacements = {v: k for k, v in replacements.items() if v}
    return ''.join(replacements.get(c, c) for c in text)

def is_match(query, name):
    query_l = query.lower()
    name_l = name.lower()
    if query_l in name_l or transliterate(query_l) in name_l or query_l in transliterate(name_l, False):
        return True
    return bool(difflib.get_close_matches(query_l, [name_l], cutoff=0.7))

async def update_metrics(event: str, group: str = None):
    now = datetime.now(pytz.timezone("Asia/Tashkent")).strftime("%Y-%m-%d")
    payload = {
        "event": event,
        "date": now
    }
    if group:
        payload["group"] = group

    async with aiohttp.ClientSession() as session:
        async with session.post(f"{BASE_URL}/services/metrics/", json=payload) as resp:
            if resp.status != 200:
                raise Exception(f"Metrics update failed: {resp.status}")
            return await resp.json()

# Start funksiyasi
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    logger.info(f"/start buyrug‘i keldi. ID: {user_id}")

    now_str = datetime.now(pytz.timezone("Asia/Tashkent")).strftime('%Y-%m-%d %H:%M:%S')
    user_data = await fetch_user_profile(user_id)

    if not user_data or not user_data.get("ism"):
        # 🆕 Yangi foydalanuvchi
        test_group = random.choice(["A", "B"])
        await track_user(user_id, name=None, phone=None)

        welcome_quotes = [
            "😊 Assalomu alaykum! Xush kelibsiz.\nBu yerda xizmat tanlash oson va xavfsiz.",
            "🕒 Atigi bir necha soniyada buyurtma berishingiz mumkin.\nSiz xohlagan xizmatni yozing — biz tayyormiz.",
            "🔐 Sizdan faqat kerakli ma’lumotlar olinadi.\nHech qanday keraksiz savollar yo‘q.",
            "📲 Buyurtma jarayoni silliq va ishonchli. Boshlaymizmi?",
            "🤝 Bu yerda siz doim e’tibordasiz. Xizmat tanlang — biz qolganini hal qilamiz."
        ]
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("📩 Buyurtma berish", switch_inline_query_current_chat=""),
             InlineKeyboardButton("🆘 Yordam kerak", callback_data="help_request")]
        ])
        vaqt = work_time_string()
        await update.message.reply_text(
            f"👋 Hurmatli mijoz!\n\n<i><b>{random.choice(welcome_quotes)}</b></i>\n\n{vaqt}",
            parse_mode=ParseMode.HTML,
            reply_markup=markup
        )
        return ConversationHandler.END

    name = user_data.get("name", "Hurmatli mijoz")
    test_group = user_data.get("test_group", "A")
    is_loyal = user_data.get("is_loyal", False)
    orders = user_data.get("orders", [])

    context.user_data["name"] = name

    # 🎯 Sodiq mijozga aylanishi
    if len(orders) >= 3 and not is_loyal:
        await track_user(user_id, name=name, phone=user_data.get("phone"))
        is_loyal = True

    vaqt = work_time_string()
    salom = f"Hurmatli mijoz, {name}!"

    # 💬 Matnlar A/B yoki sodiqlikka qarab
    if is_loyal:
        quotes = [
            f"🌟 {name}, siz bizning qadrlangan mijozimizsiz.\nBugun siz uchun xizmatlar tayyor.",
            "🎁 Sodiq mijoz sifatida sizga ustuvor xizmat ko‘rsatamiz.",
            "💼 Siz tanlagan har bir xizmat — biz uchun sharaf."
        ]
    elif test_group == "B":
        quotes = [
            "💡 Siz uchun buyurtma jarayoni maksimal soddalashtirilgan.",
            "🚀 Buyurtmani 60 soniyada yakunlash mumkin. Sinab ko‘ring!",
            "🔒 Maxfiylik va qulaylik — bizning asosiy tamoyillarimiz."
        ]
    else:
        quotes = [
            f"😊 Xush kelibsiz, {name}!\nSiz uchun xizmatlar silliq va ishonchli.",
            "📲 Xizmat tanlang — qolganini biz bajaramiz.",
            "🕒 Vaqtingizni tejang, biz sizga moslashamiz."
        ]

    # ⌨️ Tugmalar
    markup_buttons = [
        [InlineKeyboardButton("📩 Buyurtma berish", switch_inline_query_current_chat="")],
        [InlineKeyboardButton("🆘 Yordam kerak", callback_data="help_request")],
        [InlineKeyboardButton("📜 Buyurtmalar tarixi", callback_data="show_history")],
        [InlineKeyboardButton("🎁 Sodiqlik dasturi", callback_data="bonus_services")]
    ]
    if is_loyal:
        markup_buttons.append([InlineKeyboardButton("🎁 Mening bonusim", callback_data="bonus_services")])

    markup = InlineKeyboardMarkup(markup_buttons)

    await update.message.reply_text(
        f"{salom}\n\n<i><b>{random.choice(quotes)}</b></i>\n\n{vaqt}\n\n👇 Xizmat tanlash yoki yordam so‘rash uchun tugmalardan foydalaning.",
        parse_mode=ParseMode.HTML,
        reply_markup=markup
    )

    name = update.effective_user.full_name or f"@{update.effective_user.username}" or "Foydalanuvchi"


    return ConversationHandler.END



async def bonus_services_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    await query.message.reply_text(
        "🎁 Bu yerda bizning sodiq mijozlarimiz uchun maxsus bonuslar ishga tushadi!\n\n"
        "1. 🛠 Bepul xizmat ko'rsatish\n"
        "2. 🚚 Hamkorlardan sovg'alar\n"
        "3. 🎫 Maxfiy chegirma kodi\n\n"
        "Yaqin orada ushbu bonuslar aynan siz uchun faollashadi 😉"
    )

    
async def asking_name_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_id_str = str(user_id)
    name = update.message.text.strip()

    await update_user(user_id, {"name": name})
    context.user_data["name"] = name
    # Tanishuv xabari
    await update.message.reply_text(
        f"🌟 Tanishganimdan xursandman, {name}!",
        parse_mode=ParseMode.HTML
    )

    # Avtomatik start menyusiga qaytadi (takroriy foydalanuvchi sifatida)
    await start(update, context)
    return ConversationHandler.END

    
async def save_services(services):
    async with aiofiles.open(DATA_FILE, 'w', encoding='utf-8') as f:
        await f.write(json.dumps(services, ensure_ascii=False, indent=2))

async def add_service_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if update.effective_user.id != ADMIN_ID:
        await query.message.reply_text("❌ Bu funksiya faqat adminlar uchun!")
        logger.warning(f"❌ Noto‘g‘ri admin kirish urinishi: user_id={update.effective_user.id}")
        return ConversationHandler.END

    context.user_data['service_action'] = 'add'
    await query.message.reply_text(
        "➕ <b>Yangi xizmat qo‘shish</b>\n\n1/6: Xizmat ID raqamini yozing (masalan, 123):",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardRemove()
    )
    logger.info(f"✅ Yangi xizmat qo‘shish boshlandi: user_id={query.from_user.id}")
    return ADD_SERVICE_ID

async def settings_admin_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if update.effective_user.id != ADMIN_ID:
        await query.message.reply_text("❌ Faqat joriy admin yangi admin tayinlashi mumkin!")
        logger.warning(f"❌ Noto‘g‘ri admin kirish urinishi: user_id={update.effective_user.id}")
        return ConversationHandler.END
    
    context.user_data['setting_action'] = 'admin'
    await query.message.edit_text(
        "👑 Yangi admin ID raqamini kiriting (Telegram foydalanuvchi ID si, masalan, 123456789):",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Orqaga", callback_data="admin_settings")]
        ])
    )
    logger.info(f"✅ Yangi admin tayinlash boshlandi: user_id={query.from_user.id}")
    return SETTINGS_ADMIN

async def save_admin_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        new_admin_id = int(update.message.text.strip())
        # Telegram foydalanuvchisini tekshirish (ixtiyoriy, xavfsizlik uchun)
        try:
            await context.bot.get_chat(new_admin_id)
        except telegram.error.BadRequest:
            await update.message.reply_text(
                "❌ Bu ID Telegram foydalanuvchisiga tegishli emas. Qayta kiriting:",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⬅️ Orqaga", callback_data="admin_settings")]
                ])
            )
            return SETTINGS_ADMIN

        # Yangi admin ID ni saqlash
        context.bot_data['settings'] = context.bot_data.get('settings', {})
        context.bot_data['settings']['admin_id'] = new_admin_id
        save_bot_data(context)
        
        # ADMIN_ID ni yangilash (global o'zgaruvchi)
        global ADMIN_ID
        ADMIN_ID = new_admin_id
        
        await update.message.reply_text(
            f"✅ Yangi admin tayinlandi: ID {new_admin_id}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Sozlamalarga", callback_data="admin_settings")]
            ])
        )
        logger.info(f"✅ Yangi admin tayinlandi: user_id={update.effective_user.id}, new_admin_id={new_admin_id}")
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text(
            "❌ Faqat raqam kiriting (masalan, 123456789). Qayta kiriting:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Orqaga", callback_data="admin_settings")]
            ])
        )
        logger.error(f"❌ Noto‘g‘ri ID formati: user_id={update.effective_user.id}, input={update.message.text}")
        return SETTINGS_ADMIN
        
    
async def get_service_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        service_id = int(update.message.text.strip())
        services = get_services()
        if any(s['id'] == service_id for s in services):
            await update.message.reply_text("❌ Bu ID allaqachon mavjud. Boshqa ID kiriting:")
            logger.warning(f"❌ Dublikat ID kiritildi: user_id={update.effective_user.id}, id={service_id}")
            return ADD_SERVICE_ID
        context.user_data['id'] = service_id
        await update.message.reply_text("2/6: Xizmat nomini kiriting:")
        logger.info(f"✅ Xizmat ID kiritildi: user_id={update.effective_user.id}, id={service_id}")
        return ADD_SERVICE_NAME
    except ValueError:
        await update.message.reply_text("❌ Faqat raqam kiriting (masalan, 123). Qayta urining:")
        logger.error(f"❌ Noto‘g‘ri ID formati: user_id={update.effective_user.id}, input={update.message.text}")
        return ADD_SERVICE_ID

async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    if not name:
        await update.message.reply_text("❌ Xizmat nomi bo‘sh bo‘lmasligi kerak. Qayta kiriting:")
        return ADD_SERVICE_NAME
    context.user_data['name'] = name
    await update.message.reply_text("3/6: Narxini so‘mda kiriting (masalan, 10000):")
    logger.info(f"✅ Xizmat nomi kiritildi: user_id={update.effective_user.id}, name={name}")
    return ADD_SERVICE_PRICE

async def get_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        price = int(update.message.text.strip())
        if price <= 0:
            await update.message.reply_text("❌ Narx musbat bo‘lishi kerak. Qayta kiriting:")
            return ADD_SERVICE_PRICE
        context.user_data['price'] = price
        keyboard = [["Click", "Payme"], ["Karta bilan"], ["Tugatish"]]
        markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        context.user_data['payment_methods'] = []
        await update.message.reply_text(
            "4/6: To‘lov usullarini tanlang. 'Tugatish' bosilgach rasm so‘raladi:",
            reply_markup=markup
        )
        logger.info(f"✅ Xizmat narxi kiritildi: user_id={update.effective_user.id}, price={price}")
        return ADD_SERVICE_PAYMENTS
    except ValueError:
        await update.message.reply_text("❌ Faqat raqam kiriting (masalan, 10000). Qayta urining:")
        logger.error(f"❌ Noto‘g‘ri narx formati: user_id={update.effective_user.id}, input={update.message.text}")
        return ADD_SERVICE_PRICE

async def get_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text.lower() == "tugatish":
        if not context.user_data['payment_methods']:
            await update.message.reply_text("❌ Kamida bitta to‘lov usuli tanlanishi kerak. Qayta tanlang:")
            return ADD_SERVICE_PAYMENTS
        await update.message.reply_text(
            "5/6: Xizmat rasmini yuboring yoki 'Rasm yo‘q' deb yozing:",
            reply_markup=ReplyKeyboardRemove()
        )
        logger.info(f"✅ To‘lov usullari tanlandi: user_id={update.effective_user.id}, methods={context.user_data['payment_methods']}")
        return ADD_SERVICE_IMAGE
    context.user_data['payment_methods'].append(text)
    logger.info(f"✅ To‘lov usuli qo‘shildi: user_id={update.effective_user.id}, method={text}")
    return ADD_SERVICE_PAYMENTS

async def get_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text and update.message.text.lower() in ["yo‘q", "yoq", "rasm yo‘q"]:
        context.user_data['image'] = None
        logger.info(f"✅ Rasm yo‘q deb tanlandi: user_id={update.effective_user.id}")
    elif update.message.photo:
        context.user_data['image'] = update.message.photo[-1].file_id
        logger.info(f"✅ Rasm kiritildi: user_id={update.effective_user.id}, file_id={context.user_data['image']}")
    else:
        await update.message.reply_text("❌ Iltimos, rasm yuboring yoki 'Rasm yo‘q' deb yozing.")
        return ADD_SERVICE_IMAGE

    await update.message.reply_text("6/6: Xizmat toifasini kiriting (masalan, Print, Foto):")
    return ADD_SERVICE_CATEGORY

async def get_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    category = update.message.text.strip()
    if not category:
        await update.message.reply_text("❌ Toifa bo‘sh bo‘lmasligi kerak. Qayta kiriting:")
        return ADD_SERVICE_CATEGORY
    context.user_data['category'] = category

    services = get_services()
    new_service = {
        'id': context.user_data['id'],
        'name': context.user_data['name'],
        'price': context.user_data['price'],
        'payment_methods': context.user_data['payment_methods'],
        'image': context.user_data['image'],
        'category': context.user_data['category'],
        'active': True
    }
    services.append(new_service)
    save_services(services)
    context.bot_data['services'] = services  # Cache update

    await update.message.reply_text(
        f"✅ Yangi xizmat qo‘shildi: {new_service['name']} ({new_service['category']})",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Xizmatlar menyusiga", callback_data="admin_services")]
        ])
    )
    logger.info(f"✅ Yangi xizmat saqlandi: user_id={update.effective_user.id}, id={new_service['id']}, name={new_service['name']}")
    context.user_data.clear()
    return ConversationHandler.END
    
async def fetch_services():
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(API_URL) as response:
                if response.status == 200:
                    return await response.json()
    except Exception as e:
        print(f"❌ Xizmatlarni olishda xato: {e}")
    return []


async def inline_query_handler(update: InlineQuery, context: ContextTypes.DEFAULT_TYPE):
    query = update.inline_query.query.lower().strip()
    services = await fetch_services()
    results = []

    for service in services:
        name = service.get("name", "").lower()
        service_id = service.get("id")

        if query in name or query == "":
            duration = service.get("duration", "—")
            cashback = service.get("cashback", 0)
            image_url = service.get("image_url") or DEFAULT_IMAGE

            message_text = f"#XIZMAT#{service_id}"

            result = InlineQueryResultArticle(
                id=str(uuid4()),
                title=service["name"], 
                description=f"⏱ {duration} daqiqa | 💸 Cashback: {cashback}%",
                input_message_content=InputTextMessageContent(
                    message_text=message_text
                ),
                thumbnail_url=image_url
            )

            results.append(result)
# okey
    await update.inline_query.answer(results[:50], is_personal=True, cache_time=0)

print("✅ trigger_inline_handler test print")
        
        
async def roziman_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    logger.info("✅ Roziman tugmasi bosildi")

    # SAQLAB QOLINGAN ma’lumotlarni vaqtincha o‘zgaruvchilarga olib oling
    selected_service = context.user_data.get('selected_service')
    
    order_id = context.user_data.get('order_id')
    user_id = update.effective_user.id

    # ESKI MA'LUMOTLARNI SAQLAB QOLISHI UCHUN clear()ni O‘CHIRAMIZ
    context.user_data['step'] = 'waiting_for_phone'
    context.user_data['selected_service'] = selected_service
    context.user_data['order_id'] = order_id
    context.user_data['user_id'] = user_id

    markup = ReplyKeyboardMarkup(
        [[KeyboardButton("📱 Telefon raqamni yuborish", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True
    )

    await context.bot.send_message(
        chat_id=query.from_user.id,
        text="📞 Telefon raqamingizni yuboring:",
        reply_markup=markup
    )
    return WAIT_PHONE

async def trigger_inline_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        text = update.message.text.strip()
        if text.lower() in ("/info", "info"):
            btn = InlineKeyboardMarkup([
                [InlineKeyboardButton("📲 Obuna bo‘lish", url="https://t.me/texnosetUZ")]
            ])
            await update.message.reply_text("📢 Bizni Telegramda kuzating!", reply_markup=btn)
            return

        service_id = int(update.message.text.replace("#XIZMAT#", ""))
        logger.info(f"Xizmat tanlandi, ID: {service_id}")
    except ValueError:
        await update.message.reply_text("❌ Xizmat topilmadi.")
        return ConversationHandler.END

    try:
        service = await fetch_service(service_id)
    except Exception as e:
        logger.error(f"APIdan xizmatni olishda xatolik: {e}")
        await update.message.reply_text("❌ Xizmat haqida ma'lumot olishda xatolik.")
        return ConversationHandler.END

    try:
        order_id = await get_next_order_number(service_id)
        await update_last_order(service_id, order_id)
    except Exception as e:
        logger.error(f"Buyurtma raqami olishda yoki yangilashda xato: {e}")
        await update.message.reply_text("❌ Buyurtma raqami yaratilishda xatolik.")
        return ConversationHandler.END

    # Saqlash
    context.user_data.update({
        'selected_service': service_id,
        'order_id': order_id,
        'user_id': update.effective_user.id,
        'step': 'waiting_for_phone'
    })

    # Xizmat tafsilotlari
    name = service.get("name", "—")
    price = service.get("price", 0)
    original = service.get("original_price", price)
    cashback = service.get("cashback", 0)
    duration = service.get("duration", "—")
    tolov = service.get("payment_methods", "Naqd / Click / Payme")
    image = service.get("image")
    description = service.get("description", "—")

    cashback_sum = int(price * cashback / 100)
    jami_foyda = (original - price) + cashback_sum

    caption = (
        f"📌 <b>{name}</b> — ayni hozir buyurtma bering!\n\n"
        f"📝 <b>Tafsilot:</b>\n<pre>{description}</pre>\n"
        f"⏱ <b>Bajarilish muddati:</b> {duration} daqiqa\n\n"
        f"💰 <b>Avvalgi narx:</b> <b><s>{original:,} so‘m</s></b>\n"
        f"💥 <b>Aksiya narxi:</b> <b>{price:,} so‘m</b>\n"
        f"🎁 <b>Cashback:</b> {cashback_sum:,} so‘m ({cashback}%)\n\n"
        f"💸 <b>Foyda:</b> {original - price:,} + {cashback_sum:,} = <u>{jami_foyda:,} so‘m</u>\n\n"
        f"⏳ <b>Aksiya muddati cheklangan!</b>\n"
        f"👇 <b>Buyurtma berish uchun “Roziman”ni bosing</b>\n\n"
        f"#Buyurtma: <code>#{order_id}</code>"
    )

    markup = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📂 Boshqa xizmat tanlash", callback_data="restart"),
            InlineKeyboardButton("🆘 Yordam kerak", callback_data="help_request")
        ],
        [InlineKeyboardButton("✅ Roziman", callback_data="confirm_service")]
    ])

    try:
        if image:
            image_url = f"https://admin-panel-3cc1cb571383.herokuapp.com/static/images/{image}"
            await context.bot.send_photo(
                chat_id=update.effective_user.id,
                photo=image_url,
                caption=caption,
                reply_markup=markup,
                parse_mode=ParseMode.HTML
            )
        else:
            await update.message.reply_text(
                text=caption,
                reply_markup=markup,
                parse_mode=ParseMode.HTML
            )
    except Exception as e:
        logger.error(f"Xizmat xabarini yuborishda xato: {e}")
        await update.message.reply_text("❌ Xizmat haqida ma'lumot yuborilmadi.")

    return WAIT_PHONE

async def info_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("ℹ️ /info komandasi ishladi")

    if update.message and update.message.text == "🚀 Xizmat izlash boshlandi...":
        try:
            await update.message.reply_text(
                "ℹ️ Xizmat nomini yozing. Masalan: skaner, printer, dizayn, tarjima...\n"
                "👇 Quyida kerakli xizmatni tanlang yoki yozib qidiring.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📢 Kanalimizga obuna bo‘ling!", url="https://t.me/texnosetUZ")]
                ])
            )
        except Exception as e:
            logger.error(f"/info komandasi ishlamay qoldi: {e}")
        return


async def fallback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Foydalanuvchi noto‘g‘ri yoki kutilmagan xabar yuborganida ishlaydi.
    Foydalanuvchiga do‘stona xabar va tugmalar bilan yo‘l ko‘rsatadi.
    """
    user_id = update.effective_user.id
    step = context.user_data.get("step")
    name = context.bot_data.get(f"user_{user_id}", {}).get("name", "Hurmatli mijoz")
    logger.info(f"Fallback ishga tushdi: user_id={user_id}, step={step}")

    # Do‘stona va ishonchli xabar
    text = (
        f"🤗 {name}, siz noto‘g‘ri xabar yuborganga o‘xshaysiz.\n"
        "Xavotir olmang, biz sizga yordam beramiz! 😊\n\n"
        "Quyidagi variantlardan birini tanlang:"
    )

    # Tugmalar
    markup = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔁 Qayta boshlash", callback_data="restart"),
            InlineKeyboardButton("▶️ Davom etish", callback_data="continue")
        ],
        [InlineKeyboardButton("🆘 Yordam so‘rash", callback_data="help_request")]
    ])

    await update.message.reply_text(
        text=text,
        parse_mode=ParseMode.HTML,
        reply_markup=markup
    )
    logger.info(f"Fallback xabari yuborildi: user_id={user_id}")
    return ConversationHandler.END

async def restart_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data.clear()

    # start_handler ni callback orqali sun'iy chaqirish
    update.message = query.message
    await start_handler(update, context)

async def continue_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Foydalanuvchi jarayonni davom ettirishni xohlaganda step asosida to‘g‘ri bosqichga qaytaradi.
    """
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    step = context.user_data.get("step")
    logger.info(f"Davom etish so‘raldi: user_id={user_id}, step={step}")

    # Step bo‘yicha to‘g‘ri xabarni yuborish
    if step == "waiting_for_phone":
        text = (
            "📞 Telefon raqamingizni yuboring:\n"
            "Masalan, +998901234567 yoki telefon tugmasini bosing."
        )
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("📱 Telefon raqamni yuborish", request_contact=True)],
            [InlineKeyboardButton("🔁 Qayta boshlash", callback_data="restart")]
        ])
    elif step == "waiting_for_contact_method":
        text = "📲 Qanday usulda bog‘lanishimizni xohlaysiz?"
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("📱 Shu bot orqali", callback_data="contact_bot")],
            [InlineKeyboardButton("☎️ Qo‘ng‘iroq orqali", callback_data="contact_call")],
            [InlineKeyboardButton("📩 SMS orqali", callback_data="contact_sms")],
            [InlineKeyboardButton("🔄 Boshqa usul", callback_data="contact_other")]
        ])
    elif step == "waiting_for_time":
        text = (
            "🕒 Siz bilan qachon bog‘lanishimizni xohlaysiz?\n"
            "Masalan: Bugun 15:00, Ertaga 09:00, istalgan vaqtda."
        )
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔁 Qayta boshlash", callback_data="restart")]
        ])
    elif step == "waiting_for_help_question":
        text = "❓ Qanday yordam kerak? Savolingizni yozing:"
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔁 Qayta boshlash", callback_data="restart")]
        ])
    else:
        text = (
            "🤔 Hozirda davom ettiriladigan jarayon topilmadi.\n"
            "Iltimos, qayta boshlang yoki yordam so‘rang:"
        )
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔁 Qayta boshlash", callback_data="restart"),
             InlineKeyboardButton("🆘 Yordam so‘rash", callback_data="help_request")]
        ])

    await query.message.edit_text(
        text=text,
        parse_mode=ParseMode.HTML,
        reply_markup=markup
    )
    logger.info(f"Davom etish xabari yuborildi: user_id={user_id}, step={step}")
    return ConversationHandler.END

async def help_request_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Foydalanuvchi yordam so‘raganda operator bilan bog‘laydi yoki yangi forum topic ochadi.
    """
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    # Foydalanuvchi ismini aniqlash
    name = context.bot_data.get(f"user_{user_id}", {}).get("ism") or "Hurmatli mijoz"
    name = str(name)[:50]
    logger.info(f"🆘 Yordam so‘rovi boshlandi: user_id={user_id}, name={name}")

    # GROUP_ID mavjudligini tekshirish
    if not GROUP_ID:
        logger.error("❌ GROUP_ID belgilanmagan. Forum topic ochib bo‘lmadi.")
        return ConversationHandler.END

    # Mavjud chat topic borligini tekshiramiz
    user_data = context.bot_data.get(f"user_{user_id}", {})
    if user_data.get("thread_id") and user_data.get("is_operator_started"):
        thread_id = user_data["thread_id"]
        text = (
            "🆘 Operator bilan suhbat allaqachon ochiq!\n"
            "Savolingizni yozing, operator tez orada javob beradi."
        )
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔁 Bosh sahifaga qaytish", callback_data="restart")]
        ])
        if query.message:
            await query.message.edit_text(text=text, parse_mode=ParseMode.HTML, reply_markup=markup)
        else:
            await context.bot.send_message(chat_id=user_id, text=text, parse_mode=ParseMode.HTML, reply_markup=markup)

        context.user_data["step"] = "waiting_for_help_question"
        logger.info(f"↪️ Mavjud yordam mavzusi mavjud: thread_id={thread_id}")
        return ConversationHandler.END

    # Yangi topic ochamiz
    try:
        topic = await context.bot.create_forum_topic(
            chat_id=GROUP_ID,
            name=f"🦸 Yordam — {name}"
        )

        # Guruhga xabar yuboramiz
        await context.bot.send_message(
            chat_id=GROUP_ID,
            message_thread_id=topic.message_thread_id,
            text=(
                f"🦸 <b>Yordam so‘rovi</b>\n\n"
                f"👤 Mijoz: {name}\n"
                f"📌 Iltimos, savolni kuting yoki qabul qiling."
            ),
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Qabul qilish", callback_data=f"accept_help_{user_id}")]
            ])
        )

        # Bot ma'lumotlarini yangilaymiz
        context.bot_data[f"user_{user_id}"] = {
            "thread_id": topic.message_thread_id,
            "help_question": True,
            "is_operator_started": False
        }
        context.bot_data[f"thread_{topic.message_thread_id}"] = {
            "user_id": user_id,
            "order_id": None
        }
        save_bot_data(context)
        logger.info(f"✅ Yordam so‘rovi guruhga yuborildi: thread_id={topic.message_thread_id}")

        # Foydalanuvchiga javob
        text = (
            "✅ Yordam so‘rovingiz qabul qilindi!\n"
            "❓ Iltimos, savolingizni yozing. Operatorimiz tez orada javob beradi."
        )
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔁 Qayta boshlash", callback_data="restart")]
        ])
        if query.message:
            await query.message.edit_text(text=text, parse_mode=ParseMode.HTML, reply_markup=markup)
        else:
            await context.bot.send_message(chat_id=user_id, text=text, parse_mode=ParseMode.HTML, reply_markup=markup)

        context.user_data["step"] = "waiting_for_help_question"

    except Exception as e:
        logger.error(f"❌ Yordam mavzusi yaratishda xato: user_id={user_id}, xato={e}")
        fallback_text = (
            "❌ Yordam so‘rovini yuborishda texnik xatolik yuz berdi.\n"
            "Iltimos, keyinroq urinib ko‘ring."
        )
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔁 Qayta boshlash", callback_data="restart")]
        ])
        if query.message:
            await query.message.edit_text(text=fallback_text, parse_mode=ParseMode.HTML, reply_markup=markup)
        else:
            await context.bot.send_message(chat_id=user_id, text=fallback_text, parse_mode=ParseMode.HTML, reply_markup=markup)

    return ConversationHandler.END
    
async def phone_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    step = context.user_data.get('step')
    if step != 'waiting_for_phone':
        logger.warning("❌ phone_handler: step noto‘g‘ri")
        return

    phone = None
    if update.message.contact:
        phone = update.message.contact.phone_number
        logger.info(f"📲 Kontakt orqali telefon: {phone}")
    elif update.message.text:
        cleaned = re.sub(r'\D', '', update.message.text.strip())
        if len(cleaned) >= 9:
            phone = cleaned
            logger.info(f"📝 Matn orqali telefon: {phone}")
        else:
            await update.message.reply_text("❌ Telefon raqam noto‘g‘ri formatda.")
            return WAIT_PHONE
    else:
        await update.message.reply_text("❌ Telefon raqam yuborilmadi.")
        return WAIT_PHONE

    context.user_data['phone'] = phone
    context.user_data['step'] = 'waiting_for_contact_method'

    user_id = update.effective_user.id
    await update_user(user_id, {"phone": phone})

    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("📱 Shu bot orqali", callback_data="contact_bot")],
        [InlineKeyboardButton("☎️ Qo‘ng‘iroq orqali", callback_data="contact_call")],
        [InlineKeyboardButton("📩 SMS orqali", callback_data="contact_sms")],
        [InlineKeyboardButton("🔄 Boshqa usul orqali", callback_data="contact_other")]
    ])

    await update.message.reply_text(
        f"📞 Telefon raqamingiz: {phone}\nQanday usulda bog‘lanishimizni xohlaysiz?",
        reply_markup=markup
    )

    return WAIT_CONTACT_METHOD


async def contact_method_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    step = context.user_data.get('step')
    logger.info(f"📲 Aloqa usuli tanlandi, user_id: {user_id}, step: {step}")

    if step != 'waiting_for_contact_method':
        await query.edit_message_text("❌ Bu bosqichda bog‘lanish usuli kutilmayapti.")
        return ConversationHandler.END

    # Mapping tugmalar bilan
    method_map = {
        "contact_bot": "📱 Shu bot orqali",
        "contact_call": "☎️ Qo‘ng‘iroq orqali",
        "contact_sms": "📩 SMS orqali",
        "contact_other": "🔄 Boshqa usul"
    }

    selected = method_map.get(query.data)
    if not selected:
        await query.edit_message_text("❌ Noma'lum aloqa usuli tanlandi.")
        return ConversationHandler.END

    context.user_data['contact_method'] = selected
    context.user_data['step'] = 'waiting_for_time'

    await query.edit_message_text(f"✅ Bog‘lanish usuli tanlandi: {selected}")

    await context.bot.send_message(
        chat_id=query.from_user.id,
        text="🕒 Siz bilan qachon bog‘lanishimizni xohlaysiz?\nMasalan: Bugun 15:00, Ertaga 09:00, istalgan vaqtda va h.k."
    )

    return WAIT_CONTACT_TIME

async def contact_time_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    step = context.user_data.get('step')
    if step != 'waiting_for_time':
        logger.warning(f"contact_time_handler: noto‘g‘ri step={step}")
        await update.message.reply_text("⚠️ Jarayon noto‘g‘ri ketdi. Iltimos, /start buyrug‘i bilan qaytadan urinib ko‘ring.")
        return

    contact_time = update.message.text.strip()
    context.user_data['contact_time'] = contact_time
    logger.info(f"🕒 Aloqa vaqti: {contact_time}")

    service = context.user_data.get('selected_service')
    phone = context.user_data.get('phone')
    contact_method = context.user_data.get('contact_method')
    order_id = context.user_data.get('order_id')
    user_id = context.user_data.get('user_id')
    user_name = update.effective_user.full_name or f"@{update.effective_user.username}" or "Foydalanuvchi"

    

    if not all([service, phone, contact_method, order_id, user_id, user_name]):
        logger.error(f"❌ Ma'lumotlar to‘liq emas: service={service}, phone={phone}, contact_method={contact_method}, order_id={order_id}, user_id={user_id}, name={user_name}")
        await update.message.reply_text("❌ Afsuski, ba'zi ma'lumotlar yetarli emas. Jarayonni /start orqali qayta boshlang.")
        context.user_data.clear()
        return

    # 1. Foydalanuvchini API orqali ro'yxatga olish / yangilash
    await track_user(user_id, user_name, phone)

    # 2. Buyurtmani API orqali yaratish
    now = datetime.now(pytz.timezone("Asia/Tashkent")).strftime("%Y-%m-%d %H:%M:%S")
    await create_order({
        "order_id": order_id,
        "user_id": user_id,
        "service_id": service["id"],
        "service_name": service["name"],
        "contact_method": contact_method,
        "contact_time": contact_time,
        "status": "pending",
        "timestamp": now
    })

    # 3. Guruhga yuboriladigan xabar
    text = ORDER_MESSAGE_TEMPLATE.format(
        order_id=order_id,
        service_id=service['id'],
        service_name=service['name'],
        phone=phone,
        contact_method=contact_method,
        contact_time=contact_time
    )

    try:
        topic = await context.bot.create_forum_topic(
            chat_id=GROUP_ID,
            name=f"#{order_id} - {service['name'][:50]}"
        )

        await send_order_to_group(
            context=context,
            order_id=order_id,
            service=service,
            phone=phone,
            contact_method=contact_method,
            contact_time=contact_time,
            text=text,
            thread_id=topic.message_thread_id,
            user_id=user_id
        )

        context.bot_data[f"user_{user_id}"] = {
            'order_id': order_id,
            'thread_id': topic.message_thread_id,
            'is_operator_started': False
        }

        context.bot_data[f"thread_{topic.message_thread_id}"] = {
            'user_id': user_id,
            'order_id': order_id
        }

        logger.info(f"✅ Buyurtma yuborildi: order_id={order_id}, thread_id={topic.message_thread_id}")

    except Exception as e:
        logger.error(f"⚠️ Buyurtma yuborishda xato: user_id={user_id}, xato={e}")
        await update.message.reply_text("⚠️ Buyurtmani yuborishda muammo yuz berdi. Iltimos, keyinroq urinib ko‘ring.")
        context.user_data.clear()
        return ConversationHandler.END

    # 4. Mijozga tasdiq va tabrik
    await update.message.reply_text(
        "✅ Buyurtmangiz qabul qilindi!\n\n"
        "Siz bilan belgilangan vaqtda bog‘lanamiz.\n"
        "Yaxshi kayfiyatda bo‘lishingiz biz uchun muhim 😊",
        reply_markup=ReplyKeyboardRemove()
    )

    await update.message.reply_text(
        "📞 Aloqa raqamimiz: <b>+998 77 009 71 71</b>\n"
        "Har qanday savol bo‘lsa, bemalol bog‘lanishingiz mumkin.\n\n"
        "🔔 Eslatma: Biz bilan muloqot doim ochiq va samimiy.",
        parse_mode=ParseMode.HTML
    )

    context.user_data.clear()
    return ConversationHandler.END

async def handle_help_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("step") != "waiting_for_help_question":
        logger.warning(f"handle_help_question: noto‘g‘ri step, joriy step: {context.user_data.get('step')}")
        return

    user_id = str(update.effective_user.id)
    name = USERS.get(user_id, {}).get('name', update.effective_user.full_name or "Foydalanuvchi")
    question = update.message.text.strip()
    logger.info(f"Yordam so‘rovi: user_id={user_id}, savol={question}")

    # Eski yordam so‘rovi ma'lumotlarini tozalash
    if f"user_{user_id}" in context.bot_data and context.bot_data[f"user_{user_id}"].get("help_question"):
        old_thread_id = context.bot_data[f"user_{user_id}"].get("thread_id")
        context.bot_data.pop(f"user_{user_id}", None)
        context.bot_data.pop(f"thread_{old_thread_id}", None)
        logger.info(f"✅ Eski yordam so‘rovi tozalandi: user_id={user_id}, thread_id={old_thread_id}")

    try:
        await update.message.reply_text(
            "✅ Savolingiz operatorlarga yuborildi. Iltimos, 15 daqiqa ichida kuting."
        )

        topic = await context.bot.create_forum_topic(
            chat_id=GROUP_ID,
            name=f"🦸 Yordam — {name[:50]}"
        )
        msg = await context.bot.send_message(
            chat_id=GROUP_ID,
            message_thread_id=topic.message_thread_id,
            text=f"🦸 Yordam so‘rovi:\n👤 {name}\n\n❓ {question}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Qabul qilish", callback_data=f"accept_help_{user_id}")]
            ])
        )

        # context.bot_data ga to‘g‘ri saqlash
        context.bot_data[f"user_{user_id}"] = {
            "thread_id": topic.message_thread_id,
            "help_question": question,
            "message_id": msg.message_id,
            "is_operator_started": False
        }
        context.bot_data[f"thread_{topic.message_thread_id}"] = {
            "user_id": user_id,
            "order_id": None
        }
        logger.info(f"✅ Yordam so‘rovi guruhga yuborildi: user_id={user_id}, thread_id={topic.message_thread_id}")
        save_bot_data(context)
        context.user_data.pop("step", None)
    except Exception as e:
        logger.error(f"❌ Yordam so‘rovini guruhga yuborishda xato: user_id={user_id}, xato={e}")
        await update.message.reply_text("❌ Savolni yuborishda xato yuz berdi. Keyinroq urinib ko‘ring.")
        return
        
async def send_order_to_group(context, order_id, service, phone, contact_method, contact_time, text, thread_id, user_id):
    buttons = [[
        InlineKeyboardButton("✅ Qabul qilindi", callback_data=f"group_accept_{order_id}"),
        InlineKeyboardButton("❌ Bekor qilindi", callback_data=f"group_cancel_{order_id}")
    ]]
    reply_markup = InlineKeyboardMarkup(buttons)

    try:
        msg = await context.bot.send_message(
            chat_id=GROUP_ID,
            message_thread_id=thread_id,
            text=(
                f"📥 <b>Yangi buyurtma qabul qilindi!</b>\n\n"
                f"{text}\n"
                f"📌 <b>Buyurtmani qabul qilish yoki bekor qilish uchun tugmalardan foydalaning.</b>"
            ),
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML
        )

        logger.info(f"✅ Guruhga xabar yuborildi: message_id={msg.message_id}, user_id={user_id}, thread_id={thread_id}")
        context.bot_data[f"msg_{msg.message_id}"] = {
            'user_id': user_id,
            'order_id': order_id,
            'thread_id': thread_id
        }
        context.bot_data[f"user_{user_id}"] = {
            'order_id': order_id,
            'thread_id': thread_id,
            'is_operator_started': False
        }
        context.bot_data[f"thread_{thread_id}"] = {
            'user_id': user_id,
            'order_id': order_id
        }
        logger.info(f"✅ send_order_to_group: context.bot_data yangilandi: user_id={user_id}, data={context.bot_data[f'user_{user_id}']}")
    except Exception as e:
        logger.error(f"❌ Guruhga buyurtma yuborishda xato: user_id={user_id}, thread_id={thread_id}, xato={e}")
        raise

async def remind_if_no_action(context: ContextTypes.DEFAULT_TYPE):
    user_id = context.job.data['user_id']
    step = context.job.data.get('step')
    if not step:
        return

    await context.bot.send_message(
        chat_id=user_id,
        text="⏳ Siz hali davom ettirmadingiz. Qanday davom etamiz?",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("▶️ Davom etish", callback_data="continue")],
            [InlineKeyboardButton("🔁 Qayta boshlash", callback_data="restart")]
        ])
    )

async def send_rating_request(user_id: int, identifier: str, context: ContextTypes.DEFAULT_TYPE, is_help_request: bool = False):
    try:
        rating_keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("1 😞", callback_data=f"rate_{identifier}_1"),
                InlineKeyboardButton("2 😕", callback_data=f"rate_{identifier}_2"),
                InlineKeyboardButton("3 😐", callback_data=f"rate_{identifier}_3"),
                InlineKeyboardButton("4 🙂", callback_data=f"rate_{identifier}_4"),
                InlineKeyboardButton("5 🤩", callback_data=f"rate_{identifier}_5"),
            ]
        ])
        text = f"📝 {'Yordam so‘rovingiz' if is_help_request else f'Buyurtma #{identifier}'} uchun xizmat sifatini baholang:"

        await context.bot.send_message(
            chat_id=user_id,
            text=text,
            reply_markup=rating_keyboard
        )
        logger.info(f"✅ Baholash so‘rovi yuborildi: user_id={user_id}, identifier={identifier}, is_help_request={is_help_request}")

    except telegram.error.BadRequest as e:
        if "chat not found" in str(e).lower():
            logger.error(f"❌ Baholash so‘rovi yuborilmadi — chat topilmadi: user_id={user_id}")
        else:
            logger.error(f"❌ Baholash so‘rovi yuborishda BadRequest: user_id={user_id}, error={e}")
    except Exception as e:
        logger.error(f"❌ Baholash so‘rovi yuborishda umumiy xato: user_id={user_id}, error={e}")

async def group_order_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try:
        await query.answer()
    except Exception as e:
        logger.error(f"❌ Query javobida xato: query_id={query.id}, xato={e}")
        return

    msg_id = str(query.message.message_id)
    info = context.bot_data.get(f"msg_{msg_id}")

    if not info:
        logger.error(f"❌ Buyurtma ma'lumotlari topilmadi, message_id={msg_id}, bot_data={context.bot_data}")
        await query.message.reply_text("❗ Buyurtma ma‘lumotlari topilmadi. Iltimos, admin bilan bog‘laning.")
        return

    user_id = info['user_id']
    order_id = info['order_id']
    data = query.data
    logger.info(f"✅ Guruh tugmasi bosildi: order_id={order_id}, data={data}, user_id={user_id}")

    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception as e:
        logger.error(f"❌ Tugmalarni o‘chirishda xato: message_id={msg_id}, xato={e}")

    if data.startswith("group_accept_"):
        await query.message.reply_text("✅ Buyurtma qabul qilindi.")
        if user_id:
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"✅ Buyurtmangiz #{order_id} qabul qilindi va ko‘rib chiqilmoqda."
                )
                await context.bot.send_message(
                    chat_id=user_id,
                    text="📬 Operator bilan suhbat ochildi. Savollaringizni yozishingiz mumkin!"
                )
                # Operator suhbatni boshlagan deb belgilash
                if f"user_{user_id}" in context.bot_data:
                    context.bot_data[f"user_{user_id}"]['is_operator_started'] = True
                    logger.info(f"✅ Operator suhbatni boshladi: user_id={user_id}, bot_data={context.bot_data[f'user_{user_id}']}")
                    save_bot_data(context)  # Qo‘shish
            except telegram.error.BadRequest as e:
                logger.error(f"❌ Foydalanuvchiga xabar yuborishda xato: user_id={user_id}, xato={e}")
                await query.message.reply_text(f"❌ Foydalanuvchiga xabar yuborib bo‘lmadi: {e}")
    elif data.startswith("group_cancel_"):
        await query.message.reply_text("❌ Buyurtma bekor qilindi.")
        if user_id:
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"❌ Buyurtmangiz #{order_id} bekor qilindi."
                )
            except telegram.error.BadRequest as e:
                logger.error(f"❌ Foydalanuvchiga bekor qilish xabari yuborishda xato: user_id={user_id}, xato={e}")
                
async def accept_help_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    msg_id = query.message.message_id
    data = query.data

    if not data.startswith("accept_help_"):
        logger.warning(f"❌ Noto‘g‘ri callback data: {data}")
        return

    user_id = int(data.replace("accept_help_", ""))
    user_id_str = str(user_id)
    name = USERS.get(user_id_str, {}).get('name', query.from_user.full_name or "Foydalanuvchi")

    # Tugmani olib tashlaymiz
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception as e:
        logger.error(f"❌ Tugmalarni o‘chirishda xato: message_id={msg_id}, xato={e}")

    await query.message.reply_text("✅ Operator so‘rovni qabul qildi.")

    # Mijozga xabar
    try:
        await context.bot.send_message(
            chat_id=user_id,
            text="👨‍💻 Operator ulandi. Savolingizni bu yerda yozishingiz mumkin."
        )
        # context.bot_data ni yangilash
        if f"user_{user_id}" in context.bot_data:
            context.bot_data[f"user_{user_id}"]['is_operator_started'] = True
            logger.info(f"✅ Operator suhbatni boshladi: user_id={user_id}, bot_data={context.bot_data[f'user_{user_id}']}")
            save_bot_data(context)  # Saqlash
    except telegram.error.BadRequest as e:
        logger.error(f"❌ Operator ulanayotganda mijozga xabar yuborilmadi: user_id={user_id}, xato={e}")
        await query.message.reply_text(f"❌ Foydalanuvchiga xabar yuborib bo‘lmadi: {e}")
        
async def user_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    message = update.message
    name = USERS.get(user_id, {}).get('name') or update.effective_user.full_name or "Mijoz"

    info = context.bot_data.get(f"user_{user_id}")
    if not info or "thread_id" not in info:
        logger.error(f"❌ Mijoz topilmadi yoki thread_id yo‘q: user_id={user_id}, bot_data={context.bot_data}")
        await message.reply_text(
            "🛠 Hozirda sizning so‘rovingiz faol emas. Iltimos, qayta buyurtma berish uchun /start buyrug‘ini bosing."
        )
        return

    thread_id = info["thread_id"]
    is_operator_started = info.get("is_operator_started", False)

    if not is_operator_started:
        logger.info(f"⏳ Operator hali yozmagan: user_id={user_id}, thread_id={thread_id}")
        await message.reply_text(
            "🕓 Operatorimiz hali sizga yozmagan. Iltimos, biroz kuting — tez orada siz bilan aloqaga chiqamiz!"
        )
        return

    try:
        chat = await context.bot.get_chat(GROUP_ID)
        if chat.type != "supergroup":
            logger.error(f"❌ GROUP_ID={GROUP_ID} supergroup emas")
            await message.reply_text("⚠️ Xizmatdagi texnik nosozlik. Iltimos, birozdan so‘ng urinib ko‘ring.")
            return
    except Exception as e:
        logger.error(f"❌ Guruhni tekshirishda xato: GROUP_ID={GROUP_ID}, xato={e}")
        await message.reply_text("⚙️ Guruhga ulanishda muammo yuz berdi. Iltimos, keyinroq urinib ko‘ring.")
        return

    try:
        if message.text:
            text = f"👤 <b>{name}:</b>\n{message.text}"
            await context.bot.send_message(
                chat_id=GROUP_ID,
                message_thread_id=thread_id,
                text=text,
                parse_mode=ParseMode.HTML
            )
        else:
            caption = message.caption or ""
            caption = f"👤 <b>{name}:</b>\n{caption}"
            await message.copy(
                chat_id=GROUP_ID,
                message_thread_id=thread_id,
                caption=caption,
                parse_mode=ParseMode.HTML
            )

        logger.info(f"✅ Mijozdan xabar yuborildi: user_id={user_id}, thread_id={thread_id}, bot_data={context.bot_data.get(f'user_{user_id}')}")
    except Exception as e:
        logger.error(f"❌ Mijozdan xabarni yuborishda xato: user_id={user_id}, thread_id={thread_id}, xato={e}")
        await message.reply_text("⚠️ Xabar yuborilmadi. Iltimos, birozdan so‘ng qayta urinib ko‘ring.")

async def relay_from_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message or not message.message_thread_id:
        logger.warning("❌ relay_from_group: Xabar yoki thread_id topilmadi.")
        return

    if message.forum_topic_created:
        logger.info("📌 Forum mavzusi yaratildi — o‘tkazib yuborildi.")
        return

    if message.text and message.text.startswith(("/bajarildi", "/bekor")):
        logger.info(f"🔄 Buyruq aniqlangan: {message.text}, relay_from_group bajarilmadi.")
        return

    thread_id = message.message_thread_id
    info = context.bot_data.get(f"thread_{thread_id}")
    if not info:
        logger.error(f"❌ user_id topilmadi: thread_id={thread_id}, bot_data={context.bot_data}")
        await context.bot.send_message(
            chat_id=GROUP_ID,
            message_thread_id=thread_id,
            text="⚠️ Buyurtma bilan bog‘liq foydalanuvchi topilmadi. Iltimos, admin tekshiruv o‘tkazsin."
        )
        return

    user_id = info.get("user_id")
    if not user_id:
        logger.error(f"❌ user_id topilmadi: thread_id={thread_id}")
        await context.bot.send_message(
            chat_id=GROUP_ID,
            message_thread_id=thread_id,
            text="⚠️ Foydalanuvchi ID topilmadi. Iltimos, admin tekshiruv o‘tkazsin."
        )
        return

    try:
        chat = await context.bot.get_chat(user_id)
        if chat.type != "private":
            logger.error(f"❌ Xatolik: user_id={user_id} xususiy chat emas, turi: {chat.type}")
            await context.bot.send_message(
                chat_id=GROUP_ID,
                message_thread_id=thread_id,
                text=f"⚠️ Foydalanuvchi bilan aloqada muammo: chat turi xususiy emas: {chat.type}."
            )
            return
    except telegram.error.BadRequest as e:
        logger.error(f"❌ Chatni olishda xatolik: user_id={user_id}, xato={e}, bot_data={context.bot_data.get(f'user_{user_id}')}")
        await context.bot.send_message(
            chat_id=GROUP_ID,
            message_thread_id=thread_id,
            text="❌ Foydalanuvchiga yozib bo‘lmadi. Ehtimol, u botni tark etgan yoki bloklagan."
        )
        return

    if f"user_{user_id}" in context.bot_data:
        context.bot_data[f"user_{user_id}"]['is_operator_started'] = True
        logger.info(f"✅ Operator suhbatni boshladi: user_id={user_id}, thread_id={thread_id}, bot_data={context.bot_data[f'user_{user_id}']}")

    try:
        from_name = update.effective_user.full_name or "Operator"
        prefix = f"👨‍💼 Operator <b>{from_name}:</b>\n"

        if message.text:
            await context.bot.send_message(
                chat_id=user_id,
                text=prefix + message.text,
                parse_mode=ParseMode.HTML
            )
            logger.info(f"📤 Matnli javob yuborildi: user_id={user_id}")
        elif message.photo:
            await context.bot.send_photo(
                chat_id=user_id,
                photo=message.photo[-1].file_id,
                caption=prefix + (message.caption or ""),
                parse_mode=ParseMode.HTML
            )
            logger.info(f"📸 Rasm yuborildi: user_id={user_id}")
        elif message.document:
            await context.bot.send_document(
                chat_id=user_id,
                document=message.document.file_id,
                caption=prefix + (message.caption or ""),
                parse_mode=ParseMode.HTML
            )
            logger.info(f"📄 Hujjat yuborildi: user_id={user_id}")
        elif message.video:
            await context.bot.send_video(
                chat_id=user_id,
                video=message.video.file_id,
                caption=prefix + (message.caption or ""),
                parse_mode=ParseMode.HTML
            )
            logger.info(f"🎥 Video yuborildi: user_id={user_id}")
        elif message.voice:
            await context.bot.send_voice(
                chat_id=user_id,
                voice=message.voice.file_id,
                caption=prefix + (message.caption or ""),
                parse_mode=ParseMode.HTML
            )
            logger.info(f"🎙 Ovozli xabar yuborildi: user_id={user_id}")
        else:
            logger.warning("⚠️ Noma’lum xabar turi.")
            await context.bot.send_message(
                chat_id=GROUP_ID,
                message_thread_id=thread_id,
                text="❌ Bu turdagi xabar foydalanuvchiga uzatib bo‘lmaydi."
            )
            return
    except telegram.error.BadRequest as e:
        logger.error(f"❌ relay_from_group: Xabarni yuborishda xato: user_id={user_id}, xato={e}")
        await context.bot.send_message(
            chat_id=GROUP_ID,
            message_thread_id=thread_id,
            text="❌ Xabarni foydalanuvchiga uzatishda xatolik yuz berdi. Iltimos, boshqa turdagi xabar yuboring."
        )

async def universal_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Foydalanuvchi tomonidan yuborilgan har qanday xabarni qayta ishlash.
    Matnli xabarlar, buyurtma holatlari va operator bilan muloqotni boshqaradi.
    
    Args:
        update: Telegram Update obyekti
        context: Telegram Context obyekti
    """
    user_id = update.effective_user.id
    step = context.user_data.get('step')
    message = update.message.text.strip() if update.message and update.message.text else None
    logger.info(f"universal_router: user_id={user_id}, step={step}, message={message}")

    # Mode ni tozalash (agar order_id yo‘q bo‘lsa)
    if context.user_data.get('mode') == 'payment' and not context.user_data.get('order_id'):
        context.user_data.pop('mode', None)
        logger.info(f"✅ Mode tozalandi: user_id={user_id}")

    # Operator bilan suhbat holatini tekshirish
    user_data = context.bot_data.get(f"user_{user_id}")
    if not user_data or 'thread_id' not in user_data:
        await update.message.reply_text(
            "❌ Faol suhbat topilmadi. Buyurtma berish uchun /start buyrug‘ini ishlatining.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📩 Buyurtma berish", switch_inline_query_current_chat="")]
            ])
        )
        logger.warning(f"❌ thread_id topilmadi yoki user_data yo‘q: user_id={user_id}")
        return

    thread_id = user_data['thread_id']
    is_operator_started = user_data.get('is_operator_started', False)

    # Operator hali suhbatni boshlamagan bo‘lsa
    if not is_operator_started:
        await update.message.reply_text("⏳ Operator hali suhbatni boshlamadi. Iltimos, kuting.")
        logger.info(f"⏳ Operator hali yozmagan: user_id={user_id}, thread_id={thread_id}")
        return

    # Foydalanuvchi ma’lumotlarini tekshirish
    user_name = USERS.get(str(user_id), {}).get('name', 'Noma’lum foydalanuvchi')
    if not user_name:
        user_name = f"ID {user_id} foydalanuvchisi"

    # Matnli xabar yoki media bilan ishlash
    if message:
        # Matn uzunligini cheklash
        if len(message) > 4096:
            message = message[:4093] + "..."
            logger.warning(f"✅ Matn uzunligi qisqartirildi: user_id={user_id}, uzunlik={len(message)}")

        try:
            await context.bot.send_message(
                chat_id=GROUP_ID,
                message_thread_id=thread_id,
                text=f"📩 {user_name}: {message}",
                parse_mode=ParseMode.HTML
            )
            await update.message.reply_text("✅ Xabaringiz operatorga yuborildi.")
            logger.info(f"📤 Matnli xabar yuborildi: user_id={user_id}, thread_id={thread_id}")
        except Exception as e:
            await update.message.reply_text("❌ Xabar yuborishda xato yuz berdi. Qayta urinib ko‘ring.")
            logger.error(f"❌ Matnli xabar yuborishda xato: user_id={user_id}, thread_id={thread_id}, xato={e}")
    elif update.message.photo or update.message.document:
        # Media (rasm yoki fayl) yuborilgan bo‘lsa
        media = update.message.photo[-1] if update.message.photo else update.message.document
        try:
            await context.bot.send_photo(
                chat_id=GROUP_ID,
                message_thread_id=thread_id,
                photo=media.file_id,
                caption=f"📷 {user_name} tomonidan yuborilgan fayl",
                parse_mode=ParseMode.HTML
            )
            await update.message.reply_text("✅ Faylingiz operatorga yuborildi.")
            logger.info(f"📤 Media xabar yuborildi: user_id={user_id}, thread_id={thread_id}")
        except Exception as e:
            await update.message.reply_text("❌ Fayl yuborishda xato yuz berdi. Qayta urinib ko‘ring.")
            logger.error(f"❌ Media yuborishda xato: user_id={user_id}, thread_id={thread_id}, xato={e}")
    else:
        await update.message.reply_text("❌ Iltimos, matnli xabar yuboring yoki fayl yuklang.")
        logger.warning(f"❌ To‘g‘ri formatdagi xabar topilmadi: user_id={user_id}")

    return ConversationHandler.END
    
async def rating_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    parts = data.split('_')
    if len(parts) != 3 or parts[0] != "rate":
        logger.warning(f"❌ Noto‘g‘ri callback data: {data}")
        return

    identifier = parts[1][:50]
    rating = int(parts[2])
    user_id = query.from_user.id
    name = (query.from_user.full_name or "Foydalanuvchi")[:100]

    # API orqali bahoni yuboramiz
    try:
        await update_user_feedback(user_id, identifier, rating)
        logger.info(f"✅ Baho saqlandi (API orqali): user_id={user_id}, id={identifier}, rating={rating}")
    except Exception as e:
        logger.error(f"❌ Baho saqlanmadi: user_id={user_id}, xato={e}")
        await query.message.reply_text("❌ Baho saqlanmadi. Keyinroq urinib ko‘ring.")
        return

    is_help_request = not identifier.isdigit()
    text = f"⭐️ {'Yordam so‘rovi' if is_help_request else 'Buyurtma'} #{identifier} — {name} tomonidan {rating} baho."

    try:
        await context.bot.send_message(chat_id=GROUP_ID, text=text[:4096])
    except telegram.error.BadRequest as e:
        logger.error(f"❌ Guruhga xabar yuborishda xato: {e}")
        if "Message is too long" in str(e).lower():
            short_text = f"⭐️ {'Yordam' if is_help_request else 'Buyurtma'} #{identifier[:50]} — Baho: {rating}"
            await context.bot.send_message(chat_id=GROUP_ID, text=short_text)

    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception as e:
        logger.error(f"❌ Tugmalarni o‘chirishda xato: {e}")

    if rating <= 3:
        await context.bot.send_message(
            chat_id=user_id,
            text=f"😔 Hey {name}, {rating} baho uchun rahmat. Xizmatimizda nima kamchilik bor? 3 ta xabar bilan yozing, generalga yuboramiz."
        )
        context.user_data['waiting_for_feedback'] = {
            'identifier': identifier,
            'name': name,
            'is_help_request': is_help_request,
            'feedback_count': 0,
            'feedback_messages': []
        }
    else:
        await context.bot.send_message(
            chat_id=user_id,
            text=f"🌟 {name}, {rating} baho uchun tashakkur! Qaytib keling!"
        )
                
async def rating_feedback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message.text
    user_id = update.effective_user.id
    feedback_data = context.user_data.get('waiting_for_feedback')

    if not feedback_data:
        logger.warning(f"❌ Feedback jarayoni topilmadi: user_id={user_id}")
        return

    feedback_data['feedback_count'] += 1
    feedback_data['feedback_messages'].append(message[:1000])

    logger.debug(f"Feedback qo'shildi: user_id={user_id}, count={feedback_data['feedback_count']}")

    if feedback_data['feedback_count'] < 3:
        await update.message.reply_text(f"👍 {feedback_data['feedback_count']}/3 xabar qo'shildi. Davom eting!")
    else:
        text = f"📝 {'Yordam so‘rovi' if feedback_data['is_help_request'] else 'Buyurtma'} #{feedback_data['identifier']} — {feedback_data['name']} fikri:\n\n" + "\n".join(feedback_data['feedback_messages'])
        try:
            await context.bot.send_message(chat_id=GROUP_ID, text=text)
            logger.info(f"✅ Feedback yuborildi: user_id={user_id}")
        except telegram.error.BadRequest as e:
            logger.error(f"❌ Feedback yuborishda xato: user_id={user_id}, xato={e}")
            short_text = f"📝 {'Yordam' if feedback_data['is_help_request'] else 'Buyurtma'} #{feedback_data['identifier'][:50]} — Fikr: {text[:200]}..."
            await context.bot.send_message(chat_id=GROUP_ID, text=short_text)
            logger.info(f"✅ Qisqartirilgan feedback yuborildi: user_id={user_id}")

        await update.message.reply_text("✅ Fikrlaringiz generalga yuborildi! Rahmat!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔁 Qayta boshlash", callback_data="restart")]]))
        context.user_data.pop('waiting_for_feedback')
        return ConversationHandler.END
        
from api_client import update_order_status

async def command_in_topic_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message or not message.message_thread_id:
        logger.warning("❌ Xabar yoki thread_id topilmadi")
        return

    thread_id = message.message_thread_id
    info = context.bot_data.get(f"thread_{thread_id}")
    if not info:
        logger.error(f"❌ user_id topilmadi, thread_id={thread_id}")
        await message.reply_text("❌ Foydalanuvchi topilmadi.")
        return

    user_id = info.get("user_id")
    order_id = info.get("order_id")

    # 🔁 Buyurtma holatini API orqali yangilaymiz
    if message.text.startswith("/bekor"):
        reason = message.text.replace("/bekor", "").strip() or "Sababsiz bekor qilindi"
        try:
            if order_id:
                await update_order_status(order_id, "cancelled")
            await context.bot.send_message(
                chat_id=user_id,
                text=f"❌ {'Buyurtmangiz #' + str(order_id) if order_id else 'Yordam so‘rovingiz'} bekor qilindi.\n📄 Sabab: {reason}"
            )
            logger.info(f"✅ Buyurtma bekor qilindi: user_id={user_id}, order_id={order_id}")
        except Exception as e:
            logger.error(f"❌ Bekor qilish xabari yuborilmadi: {e}")
            await message.reply_text("❌ Foydalanuvchiga xabar yuborishda xato yuz berdi.")

    elif message.text.startswith("/bajarildi"):
        try:
            if order_id:
                await update_order_status(order_id, "completed")
            await context.bot.send_message(
                chat_id=user_id,
                text=f"✅ {'Buyurtmangiz #' + str(order_id) if order_id else 'Yordam so‘rovingiz'} muvaffaqiyatli bajarildi!\nSizga xizmat ko‘rsatganimizdan mamnunmiz 😊"
            )
            logger.info(f"✅ Buyurtma bajarildi: user_id={user_id}, order_id={order_id}")
        except Exception as e:
            logger.error(f"❌ Bajarildi xabari yuborilmadi: {e}")
            await message.reply_text("❌ Foydalanuvchiga xabar yuborishda xato yuz berdi.")

    # ⭐ Baholash chaqiruv
    try:
        identifier = str(order_id if order_id else thread_id)
        await send_rating_request(user_id, identifier, context, is_help_request=not order_id)
        logger.info(f"✅ Baholash yuborildi: user_id={user_id}, id={identifier}")
    except Exception as e:
        logger.error(f"❌ Baholash yuborishda xato: {e}")
        await message.reply_text("✅ Topic yopildi, lekin baholash yuborilmadi.")

    # 🧹 Topicni yopamiz
    try:
        await context.bot.delete_forum_topic(chat_id=GROUP_ID, message_thread_id=thread_id)
        logger.info(f"✅ Topic yopildi: thread_id={thread_id}")
    except Exception as e:
        logger.error(f"❌ Topicni o‘chirishda xato: {e}")
        await message.reply_text("❌ Topicni yopishda xato yuz berdi.")

    # 🧽 context.bot_data tozalash
    try:
        context.bot_data.pop(f"user_{user_id}", None)
        context.bot_data.pop(f"thread_{thread_id}", None)
        for key in list(context.bot_data.keys()):
            if key.startswith("msg_") and context.bot_data[key].get("thread_id") == thread_id:
                context.bot_data.pop(key, None)
        logger.info(f"✅ Bot data tozalandi: user_id={user_id}, thread_id={thread_id}")
    except Exception as e:
        logger.error(f"❌ Bot data tozalashda xato: {e}")

async def user_file_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    mode = context.user_data.get('mode')
    logger.info(f"📎 Fayl qabul qilindi: user_id={user_id}, mode={mode}")

    file_id = None
    file_type = None
    if update.message.photo:
        file_id = update.message.photo[-1].file_id
        file_type = 'photo'
    elif update.message.document:
        file_id = update.message.document.file_id
        file_type = 'document'
    else:
        await update.message.reply_text("❌ Faqat rasm yoki hujjat yuboring.")
        logger.warning(f"❌ Noto‘g‘ri fayl turi: user_id={user_id}")
        return

    if mode == 'payment':
        logger.info(f"✅ To‘lov cheki sifatida qayta ishlash: user_id={user_id}, file_type={file_type}")
        order_id = context.user_data.get('order_id')
        if not order_id:
            await update.message.reply_text("❌ To‘lov buyurtmasi topilmadi. /start bilan qaytadan boshlang.")
            logger.error(f"❌ order_id topilmadi: user_id={user_id}")
            context.user_data.pop('mode', None)
            return

        payment_info = context.bot_data.get(f"payment_{order_id}")
        if not payment_info:
            await update.message.reply_text("❌ To‘lov ma’lumotlari topilmadi.")
            logger.error(f"❌ payment_info topilmadi: user_id={user_id}, order_id={order_id}")
            context.user_data.pop('mode', None)
            return

        # ✅ API orqali buyurtma va foydalanuvchi ma'lumotlarini olish
        order = await get_order(user_id, order_id)
        user = await get_user(user_id)

        if not order or not user:
            await update.message.reply_text("❌ Buyurtma yoki foydalanuvchi topilmadi.")
            logger.error(f"❌ get_order yoki get_user natijasiz: user_id={user_id}, order_id={order_id}")
            context.user_data.pop('mode', None)
            return

        receipt_text = (
            f"🧾 <b>Yangi to‘lov cheki</b>\n\n"
            f"🧾 Buyurtma raqami: #{order_id}\n"
            f"📌 Xizmat: {order['service_name']}\n"
            f"💰 Summa: {payment_info['amount']} so‘m\n"
            f"👤 Mijoz: {user['name']}\n"
            f"🕒 Sana: {order['timestamp']}\n\n"
            f"📎 Quyida chek ilova qilingan."
        )

        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Mijozga tasdiq yuborish", callback_data=f"confirm_payment_{order_id}")]
        ])

        try:
            if file_type == 'photo':
                await context.bot.send_photo(
                    chat_id=GROUP_ID,
                    photo=file_id,
                    caption=receipt_text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=markup
                )
            elif file_type == 'document':
                await context.bot.send_document(
                    chat_id=GROUP_ID,
                    document=file_id,
                    caption=receipt_text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=markup
                )

            await update_order_status(order_id, "awaiting_confirmation")
            await update.message.reply_text("✅ To‘lov chekingiz qabul qilindi va tekshiruvga yuborildi.")
            logger.info(f"✅ Chek guruhga yuborildi: user_id={user_id}, order_id={order_id}")

        except Exception as e:
            await update.message.reply_text("❌ Chek yuborishda xato yuz berdi. Qayta urinib ko‘ring.")
            logger.error(f"❌ Chek yuborishda xato: {e}")

        context.user_data.pop('mode', None)
        context.user_data.pop('order_id', None)
        return

    # 💬 Operator chat rejimi (fayl yuborish)
    logger.info(f"✅ Fayl chat sifatida yuboriladi: user_id={user_id}, file_type={file_type}")
    user_data = context.bot_data.get(f"user_{user_id}")
    if not user_data or not user_data.get('thread_id'):
        await update.message.reply_text("❌ Faol suhbat topilmadi. Operator bilan bog‘lanish uchun buyurtma bering.")
        return

    thread_id = user_data['thread_id']
    is_operator_started = user_data.get('is_operator_started', False)
    if not is_operator_started:
        await update.message.reply_text("⏳ Operator hali suhbatni boshlamadi. Iltimos, kuting.")
        return

    # 👤 Foydalanuvchi ismini API orqali olish
    user = await get_user(user_id)
    if not user:
        await update.message.reply_text("❌ Foydalanuvchi topilmadi.")
        return

    caption = f"📎 Foydalanuvchi ({user['name']}) dan rasm" if file_type == 'photo' else f"📎 Foydalanuvchi ({user['name']}) dan hujjat"

    try:
        if file_type == 'photo':
            await context.bot.send_photo(
                chat_id=GROUP_ID,
                message_thread_id=thread_id,
                photo=file_id,
                caption=caption
            )
        elif file_type == 'document':
            await context.bot.send_document(
                chat_id=GROUP_ID,
                message_thread_id=thread_id,
                document=file_id,
                caption=caption
            )
        await update.message.reply_text("✅ Faylingiz operatorga yuborildi.")
        logger.info(f"✅ Fayl chatga yuborildi: user_id={user_id}, thread_id={thread_id}")
    except Exception as e:
        await update.message.reply_text("❌ Fayl yuborishda xato yuz berdi. Qayta urinib ko‘ring.")
        logger.error(f"❌ Fayl yuborishda xato: user_id={user_id}, xato={e}")
                
async def start_order_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    logger.info(f"📩 Buyurtma berish tugmasi bosildi. User: {user_id}")

    services = get_services()  # allaqachon mavjud funksiya

    if not services:
        await query.message.reply_text("🚫 Hozircha hech qanday xizmat mavjud emas.")
        return

    text = "📋 <b>Xizmatlar ro‘yxati:</b>\n\n"
    for s in services:
        text += f"🔹 <b>{s['name']}</b> – {s['price']} so‘m\n"
        text += f"<i>Xizmat ID: #{s['id']}</i>\n\n"

    text += "Xizmat ID raqamini yuboring yoki tanlash uchun pastdagi qidiruv tugmasidan foydalaning."

    await query.message.reply_text(text, parse_mode="HTML")

    
async def show_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = str(query.from_user.id)
    if user_id not in USERS or not USERS[user_id].get('orders'):
        await query.message.reply_text("📭 Sizda hali buyurtmalar yo‘q.")
        return

    # Joriy sahifani olish yoki 0 dan boshlash
    current_page = context.user_data.get('history_page', 0)
    orders_per_page = 2
    orders = USERS[user_id]['orders']
    total_orders = len(orders)
    total_pages = (total_orders + orders_per_page - 1) // orders_per_page

    # Sahifa chegaralarini tekshirish
    if current_page < 0:
        current_page = 0
    elif current_page >= total_pages:
        current_page = total_pages - 1
    context.user_data['history_page'] = current_page

    # Buyurtmalarni sahifalash
    start_idx = current_page * orders_per_page
    end_idx = min(start_idx + orders_per_page, total_orders)
    page_orders = orders[start_idx:end_idx]

    # To‘lov holati uchun ikonka
    status_icons = {
        'pending': '⏳ Tasdiqlanishi kutilmoqda',
        'awaiting_confirmation': '⏳ Tasdiqlanishi kutilmoqda',
        'confirmed': '✅ To‘landi',
        'rejected': '❌ Tasdiqlanmagan'
    }

    # Xabar matnini shakllantirish
    text = f"📜 <b>Buyurtmalar tarixi</b>\n\nSiz jami {total_orders} ta xizmatdan foydalandingiz.\n\n"
    for order in page_orders:
        payment_status = order.get('payment_status', 'pending')
        text += (
            f"🧾 Buyurtma raqami: <b>#{order['order_id']}</b>\n"
            f"📌 Xizmat: {order['service_name']}\n"
            f"⏰ Aloqa vaqti: {order['contact_time']}\n"
            f"📱 Aloqa usuli: {order['contact_method']}\n"
            f"🔄 Holati: {order['status']}\n"
            f"💳 To‘lov holati: {status_icons.get(payment_status, '⏳ Tasdiqlanishi kutilmoqda')}\n"
            f"🕒 Vaqt: {order['timestamp']}\n\n"
        )

    # Tugmalar
    buttons = []
    if current_page > 0:
        buttons.append(InlineKeyboardButton("⬅️ Oldingi", callback_data=f"history_prev_{current_page-1}"))
    if current_page < total_pages - 1:
        buttons.append(InlineKeyboardButton("Keyingi ➡️", callback_data=f"history_next_{current_page+1}"))

    markup = InlineKeyboardMarkup([buttons] if buttons else [])

    # Xabarni yangilash yoki yuborish
    try:
        await query.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)
    except telegram.error.BadRequest as e:
        if "Message is not modified" not in str(e):
            await query.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)
            
async def history_pagination_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    if data.startswith("history_prev_") or data.startswith("history_next_"):
        try:
            page = int(data.split("_")[-1])
            context.user_data['history_page'] = page
            await show_history(update, context)
        except ValueError:
            logger.error(f"❌ Pagination callback data xato: {data}")

async def pay_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message or not message.message_thread_id:
        logger.warning("❌ Xabar yoki thread_id topilmadi")
        return

    thread_id = message.message_thread_id
    info = context.bot_data.get(f"thread_{thread_id}")
    if not info:
        logger.error(f"❌ user_id topilmadi, thread_id={thread_id}")
        await message.reply_text("❌ Foydalanuvchi topilmadi.")
        return

    user_id = info.get("user_id")
    order_id = info.get("order_id")
    if not order_id or not user_id:
        logger.error(f"❌ order_id yoki user_id yo‘q: thread_id={thread_id}")
        await message.reply_text("❌ Buyurtma yoki foydalanuvchi ma'lumotlari topilmadi.")
        return

    # ✅ Buyurtmani va xizmatni API orqali olish
    order = await get_order(user_id, order_id)
    if not order:
        logger.error(f"❌ Buyurtma topilmadi: order_id={order_id}")
        await message.reply_text("❌ Buyurtma ma'lumotlari topilmadi.")
        return

    service = await get_service(order["service_id"])
    if not service:
        logger.error(f"❌ Xizmat topilmadi: service_id={order['service_id']}")
        await message.reply_text("❌ Xizmat aniqlanmadi.")
        return

    amount = service["price"]

    # 💳 Invoys matni
    invoice_text = (
        f"👋 <b>Hurmatli mijoz,</b>\n\n"
        f"Quyidagi xizmat uchun to‘lovni amalga oshirishingizni so‘raymiz:\n\n"
        f"🧾 <b>Buyurtma raqami:</b> #{order_id}\n"
        f"📌 <b>Xizmat turi:</b> {order['service_name']}\n"
        f"💰 <b>Narxi:</b> {amount} so‘m\n"
        f"🕒 <b>Boshlangan vaqti:</b> {order['timestamp']}\n\n"
        f"💳 <b>To‘lov ma'lumotlari:</b>\n"
        f"  Karta raqami: <code>8600 3104 7319 9081</code>\n"
        f"  Summa: <code>{amount} so‘m</code>\n\n"
        f"✅ To‘lovingizni o‘z vaqtida tasdiqlasangiz, xizmat ko‘rsatish tezroq boshlanadi.\n"
        f"💬 Ishonchli xizmat – qulay narxda!\n"
        f"⏱ To‘lov muddati: iloji boricha tezroq (bugun kechqurun soat 20:00 gacha).\n\n"
        f"📎 To‘lovni amalga oshirgandan so‘ng, chekni yuborish uchun pastdagi tugmani bosing."
    )

    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("📤 Chekni yuborish", callback_data=f"send_receipt_{order_id}")]
    ])

    # 🖼 Grafik invoys (agar bor bo‘lsa)
    try:
        invoice_image = create_invoice_image(order, amount)  # bu funksiyangiz mavjud bo‘lsa
        await context.bot.send_photo(
            chat_id=user_id,
            photo=invoice_image,
            caption=invoice_text,
            parse_mode=ParseMode.HTML,
            reply_markup=markup
        )
    except Exception as e:
        logger.warning(f"📄 Fallback to text-only: {e}")
        await context.bot.send_message(
            chat_id=user_id,
            text=invoice_text,
            parse_mode=ParseMode.HTML,
            reply_markup=markup
        )

    # 🔁 API orqali to‘lov holatini yangilash
    await update_order_status(order_id, "pending")

    # Botda vaqtincha saqlash (chek kelganda tekshirish uchun)
    context.bot_data[f"payment_{order_id}"] = {
        'user_id': user_id,
        'amount': amount,
        'order_id': order_id,
        'thread_id': thread_id,
        'status': 'pending'
    }

    logger.info(f"✅ Invoys yuborildi: user_id={user_id}, order_id={order_id}, amount={amount}")
    await message.reply_text("✅ Invoys mijozga yuborildi.")

async def send_receipt_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Foydalanuvchidan to‘lov chekini so‘rash va mode=‘payment’ o‘rnatish.
    """
    query = update.callback_query
    await query.answer()

    order_id = int(query.data.replace("send_receipt_", ""))
    context.user_data['order_id'] = order_id
    context.user_data['mode'] = 'payment'  # To‘lov rejimini faollashtirish
    await query.message.reply_text("📎 Iltimos, to‘lov chekingizni rasm yoki hujjat sifatida yuboring.")
    logger.info(f"✅ To‘lov cheki so‘raldi: user_id={query.from_user.id}, order_id={order_id}")
    
    
async def receipt_file_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    user_id = update.effective_user.id
    order_id = context.user_data.get('waiting_for_receipt')

    if not order_id:
        logger.warning(f"❌ Chek kutilmagan: user_id={user_id}")
        await message.reply_text("❌ Chek yuborish uchun avval invoysdagi tugmani bosing.")
        return

    # 📎 Chek faylini aniqlash
    file_id = None
    if message.photo:
        file_id = message.photo[-1].file_id
    elif message.document:
        file_id = message.document.file_id
    else:
        await message.reply_text("❌ Iltimos, chekni rasm yoki fayl sifatida yuboring.")
        return

    await message.reply_text(
        "🧾 Chekingiz qabul qilindi. Moliya bo‘limi tasdiqlashini kuting...\n"
        "⏳ Holat: Ko‘rib chiqishga qabul qilindi."
    )

    # 🧾 To‘lov ma'lumotlari
    payment_info = context.bot_data.get(f"payment_{order_id}")
    if not payment_info:
        logger.error(f"❌ To‘lov ma'lumotlari topilmadi: order_id={order_id}")
        await message.reply_text("❌ To‘lov ma'lumotlari topilmadi. Admin bilan bog‘laning.")
        return

    # 📡 API orqali foydalanuvchi va buyurtmani olish
    order = await get_order(user_id, order_id)
    user = await get_user(user_id)

    if not order or not user:
        logger.error(f"❌ Buyurtma yoki foydalanuvchi topilmadi: user_id={user_id}, order_id={order_id}")
        await message.reply_text("❌ Buyurtma yoki foydalanuvchi topilmadi.")
        return

    receipt_text = (
        f"💸 <b>To‘lov tasdiqlanishi kutilmoqda</b>\n\n"
        f"🧾 Buyurtma raqami: #{order_id}\n"
        f"📌 Xizmat turi: {order['service_name']}\n"
        f"💰 Summa: {payment_info['amount']} so‘m\n"
        f"👤 Mijoz: {user['name']}\n"
        f"🕒 Sana: {order['timestamp']}\n\n"
        f"📎 Quyida chek ilova qilingan."
    )

    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Mijozga tasdiq yuborish", callback_data=f"confirm_payment_{order_id}")]
    ])

    try:
        if message.photo:
            await context.bot.send_photo(
                chat_id=GROUP_ID,
                photo=file_id,
                caption=receipt_text,
                parse_mode=ParseMode.HTML,
                reply_markup=markup
            )
        elif message.document:
            await context.bot.send_document(
                chat_id=GROUP_ID,
                document=file_id,
                caption=receipt_text,
                parse_mode=ParseMode.HTML,
                reply_markup=markup
            )

        # 🟡 API orqali statusni yangilash
        await update_order_status(order_id, "awaiting_confirmation")
        payment_info['status'] = 'awaiting_confirmation'

        logger.info(f"✅ Chek guruhga yuborildi: user_id={user_id}, order_id={order_id}")
        context.user_data.pop('waiting_for_receipt', None)

    except Exception as e:
        logger.error(f"❌ Chek yuborishda xato: user_id={user_id}, xato={e}")
        await message.reply_text("❌ Chek yuborishda xato yuz berdi. Qayta urinib ko‘ring.")
                
async def confirm_payment_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    if not data.startswith("confirm_payment_"):
        logger.warning(f"❌ Noto‘g‘ri callback data: {data}")
        return

    order_id = int(data.replace("confirm_payment_", ""))
    payment_info = context.bot_data.get(f"payment_{order_id}")
    if not payment_info:
        logger.error(f"❌ To‘lov ma'lumotlari topilmadi: order_id={order_id}")
        await query.message.reply_text("❌ To‘lov ma'lumotlari topilmadi.")
        return

    user_id = payment_info.get('user_id')

    # 🔎 Buyurtma ma’lumotini API orqali olish
    order = await get_order(user_id, order_id)
    if not order:
        logger.error(f"❌ Buyurtma topilmadi: user_id={user_id}, order_id={order_id}")
        await query.message.reply_text("❌ Buyurtma topilmadi.")
        return

    # 📅 Tasdiqlangan vaqt
    confirmation_time = datetime.now(pytz.timezone('Asia/Tashkent')).strftime('%Y-%m-%d %H:%M:%S')

    # 🔄 API orqali to‘lov holatini yangilash
    await update_order_status(order_id, "confirmed")

    # Bot xotirasida holatni yangilaymiz
    payment_info['status'] = 'confirmed'
    payment_info['confirmation_time'] = confirmation_time

    # 🖼 Chek rasmi (agar kerak bo‘lsa)
    try:
        receipt_image = create_receipt_image(order, payment_info['amount'], confirmation_time)
    except Exception as e:
        logger.warning(f"❌ Chek rasmi yaratilmagan: {e}")
        receipt_image = None

    # 📤 Mijozga tasdiq xabari
    text = (
        f"✅ <b>To‘lovingiz tasdiqlandi!</b>\n\n"
        f"🧾 Buyurtma raqami: #{order_id}\n"
        f"📌 Xizmat: {order['service_name']}\n"
        f"💰 Summa: {payment_info['amount']} so‘m\n"
        f"🕒 Tasdiqlangan vaqti: {confirmation_time}\n\n"
        f"🙏 Xizmatimizdan foydalanganingiz uchun rahmat!\n"
        f"📄 Quyida rasmiy to‘lov cheki ilova qilingan."
    )

    try:
        if receipt_image:
            await context.bot.send_photo(
                chat_id=user_id,
                photo=receipt_image,
                caption=text,
                parse_mode=ParseMode.HTML
            )
        else:
            await context.bot.send_message(
                chat_id=user_id,
                text=text,
                parse_mode=ParseMode.HTML
            )
    except Exception as e:
        logger.error(f"❌ Mijozga xabar yuborishda xato: {e}")
        await query.message.reply_text("❌ Mijozga xabar yuborilmadi.")

    # ✅ Operatorga tugma olib tashlash va xabar
    try:
        await query.message.edit_reply_markup(reply_markup=None)
        await query.message.reply_text(f"✅ To‘lov tasdiqlandi: buyurtma #{order_id}")
    except Exception as e:
        logger.error(f"❌ Operator xabari yangilanmadi: {e}")

    logger.info(f"✅ To‘lov tasdiqlandi va xabar yuborildi: user_id={user_id}, order_id={order_id}")
    
async def admin_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    secret_key = os.getenv("SECRET_KEY", "default_secret")
    logger.debug(f"Admin tekshiruvi boshlandi: user_id={user_id}, ADMIN_ID={ADMIN_ID}, secret_key={secret_key}")
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ Sizda admin huquqi yo‘q!")
        logger.warning(f"❌ Noto‘g‘ri admin kirish urinishi: user_id={user_id}")
        return

    if context.user_data.get("admin_secret") != secret_key:
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔑 Kirish", callback_data=f"verify_secret_{secret_key}")]])
        await update.message.reply_text(
            "🔐 Admin paneliga kirish uchun tasdiqlang:",
            reply_markup=markup
        )
        logger.info(f"✅ Admin autentifikatsiyasi so‘raldi: user_id={user_id}, secret_key={secret_key}")
        return

    markup = InlineKeyboardMarkup(get_admin_main_buttons())
    await update.message.reply_text(
        "👋 <b>Admin panel</b>\n\nSifatli xizmat – oson boshqaruv!\nQuyidagi bo‘limlardan birini tanlang:",
        parse_mode=ParseMode.HTML,
        reply_markup=markup
    )
    logger.info(f"✅ Admin panel bosh menyusi ochildi: user_id={user_id}")

async def verify_inline_secret(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    secret_key = os.getenv("SECRET_KEY", "default_secret")
    received_key = query.data.replace("verify_secret_", "")
    logger.debug(f"Maxfiy kalit tekshiruvi: received_key={received_key}, secret_key={secret_key}, callback_data={query.data}")
    if received_key == secret_key:
        context.user_data["admin_secret"] = secret_key
        markup = InlineKeyboardMarkup(get_admin_main_buttons())
        await query.edit_message_text(
            "✅ Maxfiy kalit tasdiqlandi! Admin panelga xush kelibsiz.",
            reply_markup=markup
        )
        logger.info(f"✅ Admin maxfiy kaliti tasdiqlandi: user_id={query.from_user.id}")
    else:
        await query.edit_message_text("❌ Noto‘g‘ri maxfiy kalit! Iltimos, qayta urining.")
        logger.error(f"❌ Noto‘g‘ri maxfiy kalit urinishi: user_id={query.from_user.id}, received={received_key}, expected={secret_key}")
    return ConversationHandler.END
    
async def admin_services_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data.clear()

    markup = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("➕ Yangi xizmat", callback_data="add_service"),
            InlineKeyboardButton("📋 Ro‘yxat", callback_data="list_services")
        ],
        [
            InlineKeyboardButton("✏️ Tahrirlash", callback_data="edit_service"),
            InlineKeyboardButton("🗑 O‘chirish", callback_data="delete_service")
        ],
        [
            InlineKeyboardButton("🔍 Qidirish", callback_data="search_service"),
            InlineKeyboardButton("📦 Toifalar", callback_data="group_by_category")
        ],
        [
            InlineKeyboardButton("🔄 Faollik", callback_data="toggle_service_visibility"),
            InlineKeyboardButton("⬅️ Bosh sahifa", callback_data="admin_main")
        ]
    ])

    await query.edit_message_text(
        "📦 <b>Xizmatlar bo‘limi</b>\n\nTez va sifatli xizmatlarni boshqaring:",
        parse_mode=ParseMode.HTML,
        reply_markup=markup
    )
    logger.info(f"✅ Xizmatlar menyusi ochildi: user_id={query.from_user.id}")
    
async def admin_orders_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    markup = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🆕 Yangi", callback_data="orders_new"),
            InlineKeyboardButton("✅ Bajarilgan", callback_data="orders_done")
        ],
        [
            InlineKeyboardButton("❌ Bekor qilingan", callback_data="orders_cancelled"),
            InlineKeyboardButton("🔍 Qidirish", callback_data="orders_search")
        ],
        [
            InlineKeyboardButton("⬅️ Bosh sahifaga", callback_data="admin_main")
        ]
    ])

    await query.edit_message_text(
        "📋 <b>Buyurtmalar bo‘limi</b>\n\nBuyurtmalarni samarali boshqaring:",
        parse_mode=ParseMode.HTML,
        reply_markup=markup
    )
    logger.info(f"✅ Buyurtmalar menyusi ochildi: user_id={query.from_user.id}")

async def list_services_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    services = get_services()
    messages = []
    for s in services:
        status = "✅ Faol" if s.get('active', True) else "❌ NoFaol"
        text = (
            f"🆔 ID: {s['id']}\n"
            f"📌 Nomi: {s['name']}\n"
            f"💰 Narxi: {s['price']} so‘m\n"
            f"💳 To‘lov: {', '.join(s['payment_methods'])}\n"
            f"📦 Toifa: {s.get('category', 'Belgilanmagan')}\n"
            f"🔄 Holati: {status}\n"
        )
        markup = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✏️ Tahrirlash", callback_data=f"edit_service_{s['id']}"),
                InlineKeyboardButton("🗑 O‘chirish", callback_data=f"delete_service_{s['id']}")
            ]
        ])
        messages.append(query.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=markup))
    await asyncio.gather(*messages)
    await query.message.reply_text(
        "⬆️ Yuqoridagi xizmatlar ro‘yxati.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Xizmatlar menyusiga", callback_data="admin_services")]
        ])
    )
    
async def edit_service_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    if data.startswith("edit_service_") and data != "edit_service":
        service_id = int(data.replace("edit_service_", ""))
        context.user_data['edit_service_id'] = service_id
        return await select_edit_field(update, context)

    context.user_data['service_action'] = 'edit'
    await query.edit_message_text(
        "✏️ <b>Xizmatni tahrirlash</b>\n\nTahrir qilmoqchi bo‘lgan xizmat ID raqamini yozing:",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Xizmatlar menyusiga", callback_data="admin_services")]
        ])
    )
    logger.info(f"✅ Xizmat tahrirlash boshlandi: user_id={query.from_user.id}")
    return EDIT_SERVICE_ID

async def get_edit_service_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        service_id = int(update.message.text.strip())
        services = get_services()
        service = next((s for s in services if s['id'] == service_id), None)
        if not service:
            await update.message.reply_text(
                "❌ Bunday ID topilmadi. Qayta kiriting:",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⬅️ Xizmatlar menyusiga", callback_data="admin_services")]
                ])
            )
            logger.error(f"❌ Xizmat topilmadi: user_id={update.effective_user.id}, service_id={service_id}")
            return EDIT_SERVICE_ID
        context.user_data['edit_service_id'] = service_id
        return await select_edit_field(update, context)
    except ValueError:
        await update.message.reply_text(
            "❌ Faqat raqam kiriting (masalan, 123). Qayta urining:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Xizmatlar menyusiga", callback_data="admin_services")]
            ])
        )
        logger.error(f"❌ Noto‘g‘ri ID formati: user_id={update.effective_user.id}, input={update.message.text}")
        return EDIT_SERVICE_ID

async def select_edit_field(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query if update.callback_query else None
    service_id = context.user_data['edit_service_id']
    services = get_services()
    service = next((s for s in services if s['id'] == service_id), None)
    
    if not service:
        await (query.message.reply_text if query else update.message.reply_text)(
            "❌ Xizmat topilmadi. Qaytadan boshlang.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Xizmatlar menyusiga", callback_data="admin_services")]
            ])
        )
        context.user_data.clear()
        return ConversationHandler.END

    markup = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📌 Nomi", callback_data="edit_name"),
            InlineKeyboardButton("💰 Narxi", callback_data="edit_price")
        ],
        [
            InlineKeyboardButton("💳 To‘lov usullari", callback_data="edit_payments"),
            InlineKeyboardButton("📎 Rasm", callback_data="edit_image")
        ],
        [
            InlineKeyboardButton("📦 Toifa", callback_data="edit_category"),
            InlineKeyboardButton("⬅️ Xizmatlar menyusiga", callback_data="admin_services")
        ]
    ])

    text = (
        f"✅ Xizmat topildi: {service['name']}\n\n"
        f"Nimalarni tahrir qilmoqchisiz?"
    )
    if query:
        await query.edit_message_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=markup
        )
    else:
        await update.message.reply_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=markup
        )
    logger.info(f"✅ Tahrirlash maydonlari ko‘rsatildi: user_id={update.effective_user.id}, service_id={service_id}")
    return EDIT_SERVICE_FIELD

async def edit_service_field(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    field = query.data
    context.user_data['edit_field'] = field
    field_names = {
        "edit_name": "xizmat nomini",
        "edit_price": "narxini",
        "edit_payments": "to‘lov usullarini (vergul bilan ajrating, masalan: Click, Payme)",
        "edit_image": "rasmni",
        "edit_category": "toifani"
    }
    await query.edit_message_text(
        f"✏️ Yangi {field_names[field]} kiriting:",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Orqaga", callback_data="select_edit_field")]
        ])
    )
    logger.info(f"✅ Tahrirlash uchun maydon tanlandi: user_id={query.from_user.id}, field={field}")
    return {
        "edit_name": EDIT_SERVICE_NAME,
        "edit_price": EDIT_SERVICE_PRICE,
        "edit_payments": EDIT_SERVICE_PAYMENTS,
        "edit_image": EDIT_SERVICE_IMAGE,
        "edit_category": EDIT_SERVICE_CATEGORY
    }[field]

async def edit_service_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    if not name:
        await update.message.reply_text("❌ Nomi bo‘sh bo‘lmasligi kerak. Qayta kiriting:")
        return EDIT_SERVICE_NAME
    return await save_edited_field(update, context, 'name', name)

async def edit_service_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        price = int(update.message.text.strip())
        if price <= 0:
            await update.message.reply_text("❌ Narx musbat bo‘lishi kerak. Qayta kiriting:")
            return EDIT_SERVICE_PRICE
        return await save_edited_field(update, context, 'price', price)
    except ValueError:
        await update.message.reply_text("❌ Faqat raqam kiriting (masalan, 10000). Qayta kiriting:")
        return EDIT_SERVICE_PRICE

async def edit_service_payments(update: Update, context: ContextTypes.DEFAULT_TYPE):
    payments = [p.strip() for p in update.message.text.strip().split(',') if p.strip()]
    if not payments:
        await update.message.reply_text("❌ Kamida bitta to‘lov usuli kiritilishi kerak. Qayta kiriting:")
        return EDIT_SERVICE_PAYMENTS
    return await save_edited_field(update, context, 'payment_methods', payments)

async def edit_service_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text and update.message.text.lower() in ["yo‘q", "yoq", "rasm yo‘q"]:
        value = None
    elif update.message.photo:
        value = update.message.photo[-1].file_id
    else:
        await update.message.reply_text("❌ Iltimos, rasm yuboring yoki 'Rasm yo‘q' deb yozing.")
        return EDIT_SERVICE_IMAGE
    return await save_edited_field(update, context, 'image', value)

async def edit_service_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    category = update.message.text.strip()
    if not category:
        await update.message.reply_text("❌ Toifa bo‘sh bo‘lmasligi kerak. Qayta kiriting:")
        return EDIT_SERVICE_CATEGORY
    return await save_edited_field(update, context, 'category', category)

async def save_edited_field(update: Update, context: ContextTypes.DEFAULT_TYPE, field, value):
    service_id = context.user_data['edit_service_id']
    services = get_services()
    service = next((s for s in services if s['id'] == service_id), None)
    
    if not service:
        await update.message.reply_text(
            "❌ Xizmat topilmadi. Qaytadan boshlang.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Xizmatlar menyusiga", callback_data="admin_services")]
            ])
        )
        context.user_data.clear()
        return ConversationHandler.END

    service[field] = value
    save_services(services)
    context.bot_data['services'] = services

    await update.message.reply_text(
        f"✅ Xizmatning {field} maydoni yangilandi: {service['name']}",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✏️ Yana tahrirlash", callback_data="select_edit_field"),
             InlineKeyboardButton("⬅️ Xizmatlar menyusiga", callback_data="admin_services")]
        ])
    )
    logger.info(f"✅ Xizmat tahrirlandi: user_id={update.effective_user.id}, service_id={service_id}, field={field}")
    return EDIT_SERVICE_FIELD
    
async def delete_service_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    logger.debug(f"Delete service handler: callback_data={data}")  # Debag qo‘shish
    if data.startswith("delete_service_") and data != "delete_service":
        service_id = int(data.replace("delete_service_", ""))
        context.user_data['delete_service_id'] = service_id
        services = get_services()
        service = next((s for s in services if s['id'] == service_id), None)
        if not service:
            await query.edit_message_text(
                "❌ Xizmat topilmadi. Qaytadan boshlang.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⬅️ Xizmatlar menyusiga", callback_data="admin_services")]
                ])
            )
            return
        markup = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"confirm_delete_{service_id}"),
                InlineKeyboardButton("❌ Bekor qilish", callback_data="admin_services")
            ]
        ])
        await query.edit_message_text(
            f"🗑 <b>Xizmatni o‘chirish</b>\n\nO‘chirmoqchi bo‘lgan xizmat: {service['name']} (ID: {service_id})\nTasdiqlaysizmi?",
            parse_mode=ParseMode.HTML,
            reply_markup=markup
        )
        logger.info(f"✅ Xizmat o‘chirish tasdiqlash so‘raldi: user_id={query.from_user.id}, service_id={service_id}")
        return DELETE_SERVICE_ID

    context.user_data['service_action'] = 'delete'
    await query.edit_message_text(
        "🗑 <b>Xizmatni o‘chirish</b>\n\nO‘chirmoqchi bo‘lgan xizmat ID raqamini yozing:",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Xizmatlar menyusiga", callback_data="admin_services")]
        ])
    )
    logger.info(f"✅ Xizmat o‘chirish boshlandi: user_id={query.from_user.id}")
    return DELETE_SERVICE_ID
    
async def confirm_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query if update.callback_query else None
    if query:
        await query.answer()
        data = query.data
        if not data.startswith("confirm_delete_"):
            await query.edit_message_text(
                "❌ Noto‘g‘ri tasdiqlash amali.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⬅️ Xizmatlar menyusiga", callback_data="admin_services")]
                ])
            )
            return
        service_id = int(data.replace("confirm_delete_", ""))
    else:
        try:
            service_id = int(update.message.text.strip())
        except ValueError:
            await update.message.reply_text(
                "❌ Faqat raqam kiriting (masalan, 123). Qayta urining:",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⬅️ Xizmatlar menyusiga", callback_data="admin_services")]
                ])
            )
            logger.error(f"❌ Noto‘g‘ri ID formati: user_id={update.effective_user.id}, input={update.message.text}")
            return DELETE_SERVICE_ID

    services = get_services()
    service = next((s for s in services if s['id'] == service_id), None)
    if not service:
        text = "❌ Bunday ID topilmadi."
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Xizmatlar menyusiga", callback_data="admin_services")]
        ])
        if query:
            await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)
        else:
            await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)
        logger.error(f"❌ Xizmat topilmadi: user_id={update.effective_user.id}, service_id={service_id}")
        return ConversationHandler.END if query else DELETE_SERVICE_ID

    services = [s for s in services if s['id'] != service_id]
    save_services(services)
    context.bot_data['services'] = services
    context.user_data.clear()

    text = f"✅ Xizmat o‘chirildi: {service['name']} (ID: {service_id})"
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Xizmatlar menyusiga", callback_data="admin_services")]
    ])
    if query:
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)
    else:
        await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)
    logger.info(f"✅ Xizmat o‘chirildi: user_id={update.effective_user.id}, service_id={service_id}")
    return ConversationHandler.END
async def search_service_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    context.user_data['service_action'] = 'search'
    await query.edit_message_text(
        "🔍 <b>Xizmat qidirish</b>\n\nXizmat nomining bir qismini yozing:",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Xizmatlar menyusiga", callback_data="admin_services")]
        ])
    )
    logger.info(f"✅ Xizmat qidirish boshlandi: user_id={query.from_user.id}")
    return SEARCH_SERVICE

async def search_service(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query_text = update.message.text.strip().lower()
    services = get_services()
    matches = [s for s in services if is_match(query_text, s['name'])]

    if not matches:
        await update.message.reply_text(
            "❌ Hech qanday xizmat topilmadi.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔍 Qayta qidirish", callback_data="search_service"),
                 InlineKeyboardButton("⬅️ Xizmatlar menyusiga", callback_data="admin_services")]
            ])
        )
        logger.info(f"ℹ Qidiruv natijasiz: user_id={update.effective_user.id}, query={query_text}")
        return SEARCH_SERVICE

    text = f"🔍 <b>Qidiruv natijalari</b> ({len(matches)} ta xizmat):\n\n"
    for s in matches:
        status = "✅ Faol" if s.get('active', True) else "❌ NoFaol"
        text += (
            f"🆔 ID: {s['id']}\n"
            f"📌 Nomi: {s['name']}\n"
            f"💰 Narxi: {s['price']} so‘m\n"
            f"📦 Toifa: {s.get('category', 'Belgilanmagan')}\n"
            f"🔄 Holati: {status}\n"
        )
        markup = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✏️ Tahrirlash", callback_data=f"edit_service_{s['id']}"),
                InlineKeyboardButton("🗑 O‘chirish", callback_data=f"delete_service_{s['id']}")
            ]
        ])
        await update.message.reply_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=markup
        )
        text = ""

    await update.message.reply_text(
        "⬆️ Yuqoridagi qidiruv natijalari.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔍 Qayta qidirish", callback_data="search_service"),
             InlineKeyboardButton("⬅️ Xizmatlar menyusiga", callback_data="admin_services")]
        ])
    )
    logger.info(f"✅ Qidiruv natijalari ko‘rsatildi: user_id={update.effective_user.id}, query={query_text}, count={len(matches)}")
    return SEARCH_SERVICE
async def group_by_category_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    services = get_services()
    categories = sorted(set(s.get('category', 'Belgilanmagan') for s in services))
    if not categories:
        await query.edit_message_text(
            "📭 Hozirda toifalar mavjud emas.",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Xizmatlar menyusiga", callback_data="admin_services")]
            ])
        )
        logger.info(f"ℹ Toifalar bo‘sh: user_id={query.from_user.id}")
        return

    buttons = []
    for i in range(0, len(categories), 2):
        row = [InlineKeyboardButton(categories[i], callback_data=f"view_category_{categories[i]}")]
        if i + 1 < len(categories):
            row.append(InlineKeyboardButton(categories[i + 1], callback_data=f"view_category_{categories[i + 1]}"))
        buttons.append(row)
    buttons.append([InlineKeyboardButton("⬅️ Xizmatlar menyusiga", callback_data="admin_services")])

    await query.edit_message_text(
        "📦 <b>Toifalar bo‘yicha ko‘rish</b>\n\nQuyidagi toifalardan birini tanlang:",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    logger.info(f"✅ Toifalar ro‘yxati ko‘rsatildi: user_id={query.from_user.id}, count={len(categories)}")
    return GROUP_BY_CATEGORY

async def view_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    category = query.data.replace("view_category_", "")
    services = get_services()
    category_services = [s for s in services if s.get('category', 'Belgilanmagan') == category]

    if not category_services:
        await query.edit_message_text(
            f"📭 {category} toifasida xizmatlar mavjud emas.",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Toifalarga", callback_data="group_by_category"),
                 InlineKeyboardButton("⬅️ Xizmatlar menyusiga", callback_data="admin_services")]
            ])
        )
        logger.info(f"ℹ Toifa bo‘sh: user_id={query.from_user.id}, category={category}")
        return

    text = f"📦 <b>{category} toifasidagi xizmatlar</b>\n\n"
    for s in category_services:
        status = "✅ Faol" if s.get('active', True) else "❌ NoFaol"
        text += (
            f"🆔 ID: {s['id']}\n"
            f"📌 Nomi: {s['name']}\n"
            f"💰 Narxi: {s['price']} so‘m\n"
            f"🔄 Holati: {status}\n"
        )
        markup = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✏️ Tahrirlash", callback_data=f"edit_service_{s['id']}"),
                InlineKeyboardButton("🗑 O‘chirish", callback_data=f"delete_service_{s['id']}")
            ]
        ])
        await query.message.reply_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=markup
        )
        text = ""

    await query.message.reply_text(
        "⬆️ Yuqoridagi toifa xizmatlari.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Toifalarga", callback_data="group_by_category"),
             InlineKeyboardButton("⬅️ Xizmatlar menyusiga", callback_data="admin_services")]
        ])
    )
    logger.info(f"✅ Toifa xizmatlari ko‘rsatildi: user_id={query.from_user.id}, category={category}, count={len(category_services)}")
  
async def toggle_service_visibility_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    context.user_data['service_action'] = 'toggle_visibility'
    await query.edit_message_text(
        "🔄 <b>Faollikni o‘zgartirish</b>\n\nFaollik holatini o‘zgartirmoqchi bo‘lgan xizmat ID raqamini yozing:",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Xizmatlar menyusiga", callback_data="admin_services")]
        ])
    )
    logger.info(f"✅ Faollik o‘zgartirish boshlandi: user_id={query.from_user.id}")
    return TOGGLE_VISIBILITY_ID

async def toggle_visibility(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        service_id = int(update.message.text.strip())
        services = get_services()
        service = next((s for s in services if s['id'] == service_id), None)
        if not service:
            await update.message.reply_text(
                "❌ Bunday ID topilmadi. Qayta kiriting:",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⬅️ Xizmatlar menyusiga", callback_data="admin_services")]
                ])
            )
            logger.error(f"❌ Xizmat topilmadi: user_id={update.effective_user.id}, service_id={service_id}")
            return TOGGLE_VISIBILITY_ID

        service['active'] = not service.get('active', True)
        save_services(services)
        context.bot_data['services'] = services
        status = "Faol" if service['active'] else "NoFaol"
        await update.message.reply_text(
            f"✅ Xizmat holati o‘zgartirildi: {service['name']} — {status}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Xizmatlar menyusiga", callback_data="admin_services")]
            ])
        )
        logger.info(f"✅ Xizmat faolligi o‘zgartirildi: user_id={update.effective_user.id}, service_id={service_id}, status={status}")
        context.user_data.clear()
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text(
            "❌ Faqat raqam kiriting (masalan, 123). Qayta urining:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Xizmatlar menyusiga", callback_data="admin_services")]
            ])
        )
        logger.error(f"❌ Noto‘g‘ri ID formati: user_id={update.effective_user.id}, input={update.message.text}")
        return TOGGLE_VISIBILITY_ID
 
async def admin_payments_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    payments = {k: v for k, v in context.bot_data.items() if k.startswith('payment_')}
    text = "💸 <b>To‘lovlar ro‘yxati</b>\n\n"
    buttons = []
    for key, value in payments.items():
        order_id = key.replace('payment_', '')
        text += f"🧾 Buyurtma #{order_id}: {value['amount']} so‘m, Holat: {value['status']}\n"
        if value['status'] == 'awaiting_confirmation':
            buttons.append([InlineKeyboardButton(f"✅ Tasdiqlash #{order_id}", callback_data=f"confirm_payment_{order_id}")])
    markup = InlineKeyboardMarkup(get_admin_payments_buttons() + buttons if buttons else get_admin_payments_buttons())
    await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)
    logger.info(f"✅ To‘lovlar ko‘rsatildi: user_id={query.from_user.id}")

async def admin_users_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    page = context.user_data.get('users_page', 0)
    per_page = 10
    users = list(USERS.items())[page * per_page:(page + 1) * per_page]
    text = "👥 <b>Foydalanuvchilar ro‘yxati</b>\n\n"
    for user_id, user in users:
        text += f"🆔 {user_id}: {user.get('name', 'Noma’lum')}, Telefon: {user.get('phone', 'Noma’lum')}\n"
    buttons = []
    if page > 0:
        buttons.append(InlineKeyboardButton("⬅️ Oldingi", callback_data=f"users_page_{page-1}"))
    if (page + 1) * per_page < len(USERS):
        buttons.append(InlineKeyboardButton("Keyingi ➡️", callback_data=f"users_page_{page+1}"))
    markup = InlineKeyboardMarkup([buttons] + get_admin_users_buttons())
    await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)
    
async def admin_stats_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    orders = [order for user in USERS.values() for order in user.get('orders', [])]
    graph = create_stats_graph(orders)
    markup = InlineKeyboardMarkup(get_admin_stats_buttons())
    await query.message.reply_photo(
        photo=graph,
        caption="📊 <b>Statistika</b>\n\n7 kunlik buyurtma grafikasi:",
        parse_mode=ParseMode.HTML,
        reply_markup=markup
    )
    logger.info(f"✅ Statistika ko‘rsatildi: user_id={query.from_user.id}")

async def admin_settings_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    settings = {
        "To‘lov kartasi": "8600 3104 7319 9081",
        "Ish vaqti": "08:30 - 19:30",
        "Kanal havolasi": "https://t.me/texnosetUZ",
        "Joriy admin": str(ADMIN_ID)  # "Admin ID" o'rniga "Joriy admin"
    }
    text = "⚙️ <b>Sozlamalar</b>\n\n"
    for key, value in settings.items():
        text += f"🔧 {key}: {value}\n"
    markup = InlineKeyboardMarkup(get_admin_settings_buttons())
    await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)
    logger.info(f"✅ Sozlamalar ko‘rsatildi: user_id={query.from_user.id}")
    
    
async def admin_announce_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    context.user_data['waiting_for_announce'] = True
    await query.message.edit_text(
        "📣 <b>E’lon yuborish</b>\n\nIltimos, e’lon matnini yozing. Barcha foydalanuvchilarga yuboriladi:",
        parse_mode=ParseMode.HTML
    )
    logger.info(f"✅ E’lon so‘raldi: user_id={query.from_user.id}")

async def handle_announce_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('waiting_for_announce'):
        return

    text = update.message.text.strip()
    if not text:
        await update.message.reply_text("❌ E’lon matni bo‘sh bo‘lmasligi kerak!")
        return

    tasks = [context.bot.send_message(chat_id=user_id, text=f"📢 <b>E’lon:</b>\n\n{text}", parse_mode=ParseMode.HTML)
             for user_id in USERS.keys()]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    success_count = sum(1 for r in results if not isinstance(r, Exception))

    await update.message.reply_text(
        f"✅ E’lon {success_count} ta foydalanuvchiga yuborildi!{f' {len(results) - success_count} ta xatolik yuz berdi.' if success_count < len(USERS) else ''}",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Admin panel", callback_data="admin_main")]])
    )
    context.user_data.pop('waiting_for_announce', None)
    logger.info(f"✅ E’lon yuborildi: success_count={success_count}")
    

async def admin_main_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data.clear()

    markup = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📦 Xizmatlar", callback_data="admin_services"),
            InlineKeyboardButton("📋 Buyurtmalar", callback_data="admin_orders")
        ],
        [
            InlineKeyboardButton("💸 To‘lovlar", callback_data="admin_payments"),
            InlineKeyboardButton("👥 Foydalanuvchilar", callback_data="admin_users")
        ],
        [
            InlineKeyboardButton("📊 Statistika", callback_data="admin_stats"),
            InlineKeyboardButton("⚙️ Sozlamalar", callback_data="admin_settings")
        ]
    ])

    # Agar joriy xabar matnli bo‘lsa, uni tahrirlaymiz
    if query.message and query.message.text:
        await query.edit_message_text(
            "👋 <b>Admin panel</b>\n\nSifatli xizmat – oson boshqaruv!\nQuyidagi bo‘limlardan birini tanlang:",
            parse_mode=ParseMode.HTML,
            reply_markup=markup
        )
    else:
        # Agar matn bo‘lmasa, yangi xabar yuboramiz
        await query.message.reply_text(
            "👋 <b>Admin panel</b>\n\nSifatli xizmat – oson boshqaruv!\nQuyidagi bo‘limlardan birini tanlang:",
            parse_mode=ParseMode.HTML,
            reply_markup=markup
        )

    logger.info(f"✅ Bosh sahifaga qaytildi: user_id={query.from_user.id}")
    return ConversationHandler.END
    
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Xato yuz berdi: {context.error}", exc_info=context.error)
    if update and update.effective_user:
        # Agar callback query bo‘lsa, yangi xabar yuboramiz
        if update.callback_query:
            await update.callback_query.message.reply_text("❌ Botda xato yuz berdi. Iltimos, keyinroq urinib ko‘ring.")
        elif update.message:
            await update.message.reply_text("❌ Botda xato yuz berdi. Iltimos, keyinroq urinib ko‘ring.")
            

def main():
    if not TOKEN:
        logger.error("Bot tokeni mavjud emas.")
        exit()

    app = Application.builder().token(TOKEN).build()


    conv_handler = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(r"^#XIZMAT#\d+$"), trigger_inline_handler),
            CommandHandler("start", start),
            CommandHandler("admin", admin_main_menu),
            CallbackQueryHandler(add_service_handler, pattern=r"^add_service$"),
            CallbackQueryHandler(edit_service_handler, pattern=r"^edit_service(_\d+)?$"),
            CallbackQueryHandler(delete_service_handler, pattern=r"^delete_service(_\d+)?$"),
            CallbackQueryHandler(search_service_handler, pattern=r"^search_service$"),
            CallbackQueryHandler(toggle_service_visibility_handler, pattern=r"^toggle_service_visibility$"),
            CallbackQueryHandler(group_by_category_handler, pattern=r"^group_by_category$"),
            CallbackQueryHandler(view_category, pattern=r"^view_category_"),
            CallbackQueryHandler(select_edit_field, pattern=r"^select_edit_field$"),
            CallbackQueryHandler(admin_services_handler, pattern=r"^admin_services$"),
            CallbackQueryHandler(admin_orders_handler, pattern=r"^admin_orders$"),
            CallbackQueryHandler(admin_payments_handler, pattern=r"^admin_payments$"),
            CallbackQueryHandler(admin_users_handler, pattern=r"^admin_users$"),
            CallbackQueryHandler(admin_stats_handler, pattern=r"^admin_stats$"),
            CallbackQueryHandler(admin_settings_handler, pattern=r"^admin_settings$"),
            CallbackQueryHandler(admin_main_handler, pattern=r"^admin_main$"),
            CallbackQueryHandler(rating_callback_handler, pattern=r"^rate_"),  # Qo‘shildi
            CallbackQueryHandler(settings_admin_handler, pattern=r"^settings_admin$"),
            CallbackQueryHandler(admin_settings_handler, pattern=r"^admin_settings$"),
        ],
        states={
            ASKING_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, asking_name_handler)],
            WAIT_PHONE: [MessageHandler(filters.CONTACT | filters.TEXT, phone_handler)],
            WAIT_CONTACT_METHOD: [
                CallbackQueryHandler(contact_method_handler, pattern=r"^contact_"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, user_message_handler)
            ],
            WAIT_CONTACT_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, contact_time_handler)],
            SETTINGS_ADMIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_admin_id)],
            ADD_SERVICE_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_service_id)],
            ADD_SERVICE_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
            ADD_SERVICE_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_price)],
            ADD_SERVICE_PAYMENTS: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_payment)],
            ADD_SERVICE_IMAGE: [MessageHandler(filters.TEXT | filters.PHOTO, get_image)],
            ADD_SERVICE_CATEGORY: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_category)],
            EDIT_SERVICE_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_edit_service_id)],
            EDIT_SERVICE_FIELD: [
                CallbackQueryHandler(edit_service_field, pattern=r"^edit_(name|price|payments|image|category)$"),
                CallbackQueryHandler(select_edit_field, pattern=r"^select_edit_field$")
            ],
            EDIT_SERVICE_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_service_name)],
            EDIT_SERVICE_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_service_price)],
            EDIT_SERVICE_PAYMENTS: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_service_payments)],
            EDIT_SERVICE_IMAGE: [MessageHandler(filters.TEXT | filters.PHOTO, edit_service_image)],
            EDIT_SERVICE_CATEGORY: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_service_category)],
            DELETE_SERVICE_ID: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_delete),
                CallbackQueryHandler(confirm_delete, pattern=r"^confirm_delete_\d+$")
            ],
            SEARCH_SERVICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, search_service)],
            TOGGLE_VISIBILITY_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, toggle_visibility)],
            GROUP_BY_CATEGORY: [CallbackQueryHandler(view_category, pattern=r"^view_category_")],
            "rating_feedback": [MessageHandler(filters.TEXT & ~filters.COMMAND & filters.USER, rating_feedback_handler)]  # Qo‘shildi
        },
        fallbacks=[
            CallbackQueryHandler(admin_settings_handler, pattern=r"^admin_settings$"),
            MessageHandler(filters.TEXT & ~filters.COMMAND & filters.USER, fallback_handler),
            CallbackQueryHandler(verify_inline_secret, pattern=r"^verify_secret_"),
            CallbackQueryHandler(restart_handler, pattern=r"^restart$"),
            CallbackQueryHandler(continue_handler, pattern=r"^continue$"),
            CallbackQueryHandler(help_request_handler, pattern=r"^help_request$"),
            CallbackQueryHandler(admin_services_handler, pattern=r"^admin_services$"),
            CallbackQueryHandler(admin_main_handler, pattern=r"^admin_main$")
        ],
        per_message=False
    )

    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("admin", admin_main_menu))
    app.add_handler(CommandHandler("info", info_handler))
    app.add_handler(InlineQueryHandler(inline_query_handler))
    app.add_handler(CallbackQueryHandler(roziman_handler, pattern=r"^confirm_service$"))
    app.add_handler(MessageHandler(filters.CONTACT, phone_handler))
    app.add_handler(CallbackQueryHandler(contact_method_handler, pattern=r"^contact_"))
    app.add_handler(MessageHandler(filters.Regex(r"^/pay"), pay_command_handler))
    app.add_handler(MessageHandler(filters.Regex(r"^/(bajarildi|bekor)"), command_in_topic_handler))
    app.add_handler(MessageHandler(filters.ALL & filters.Chat(GROUP_ID), relay_from_group))
    app.add_handler(CallbackQueryHandler(group_order_buttons, pattern=r"^group_(accept|cancel)_"))
    app.add_handler(CallbackQueryHandler(rating_callback_handler, pattern=r"^rate_"))
    app.add_handler(CallbackQueryHandler(help_request_handler, pattern=r"^help_request$"))
    app.add_handler(CallbackQueryHandler(show_history, pattern=r"^show_history$"))
    app.add_handler(CallbackQueryHandler(history_pagination_handler, pattern=r"^history_(prev|next)_"))
    app.add_handler(CallbackQueryHandler(send_receipt_handler, pattern=r"^send_receipt_"))
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL, user_file_handler))
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL & filters.USER, user_file_handler))
    app.add_handler(CallbackQueryHandler(confirm_payment_handler, pattern=r"^confirm_payment_"))
    app.add_handler(MessageHandler(filters.ALL & filters.USER, universal_router))
    app.add_handler(MessageHandler(filters.TEXT & filters.USER, rating_feedback_handler))
    app.add_handler(CallbackQueryHandler(accept_help_button_handler, pattern=r"^accept_help_"))
    app.add_handler(CallbackQueryHandler(restart_handler, pattern=r"^restart$"))
    app.add_handler(CallbackQueryHandler(continue_handler, pattern=r"^continue$"))
    app.add_handler(MessageHandler(filters.TEXT & filters.USER, fallback_handler))
    app.add_error_handler(error_handler)
    app.add_handler(CallbackQueryHandler(bonus_services_handler, pattern="^bonus_services$"))

    logger.info("🤖 Bot ishga tushdi!")
    app.run_polling()

if __name__ == "__main__":
    main()
