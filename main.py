#!/usr/bin/python3.10
# -*- coding: utf-8 -*-
import os
import logging
import asyncio
import requests
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.contrib.fsm_storage.memory import MemoryStorage

# 1. ЗАВАНТАЖЕННЯ КОНФІГУРАЦІЇ (Railway Variables)
TOKEN = os.getenv("BOT_TOKEN")
# Робимо список адмінів з рядка через кому
ADMIN_IDS = [int(i.strip()) for i in os.getenv("ADMIN_IDS", "").split(",") if i.strip()]
GAS_URL = os.getenv("GAS_URL")

# Імпорт твоїх локальних модулів
import database as db
import keyboards as kb
import users  

# 2. НАЛАШТУВАННЯ
logging.basicConfig(level=logging.WARNING)
storage = MemoryStorage()
bot = Bot(token=TOKEN)
dp = Dispatcher(bot=bot, storage=storage)

# Глобальний кеш товарів
ALL_PRODUCTS = []

# --- ФОНОВЕ ОНОВЛЕННЯ БАЗИ ---
async def update_cache_task():
    global ALL_PRODUCTS
    while True:
        try:
            data = db.get_all_items()
            if data:
                ALL_PRODUCTS = data
                print(f"✅ Кеш оновлено: {len(ALL_PRODUCTS)} товарів")
        except Exception as e:
            print(f"❌ Помилка оновлення кешу: {e}")
        await asyncio.sleep(600) # 10 хвилин

# --- СТАНИ ЗАМОВЛЕННЯ ---
class OrderState(StatesGroup):
    waiting_for_phone = State()
    waiting_for_fio = State()
    waiting_for_delivery = State()

user_products = {}

# --- АДМІН-КОМАНДИ ---

@dp.message_handler(commands=['stats'], state="*")
async def show_stats(message: types.Message):
    if message.from_user.id in ADMIN_IDS:
        data = users.get_admin_stats()
        if data:
            text = (
                "📊 <b>АНАЛІТИКА МАГАЗИНУ</b>\n\n"
                f"👥 Всього юзерів: <code>{data.get('total', 0)}</code>\n"
                f"📸 Instagram: <code>{data.get('insta', 0)}</code>\n"
                f"🏁 QR Code: <code>{data.get('qr', 0)}</code>\n"
                f"🔍 Telegram: <code>{data.get('tg', 0)}</code>"
            )
            await message.answer(text, parse_mode="HTML")

@dp.message_handler(content_types=['photo'], state="*")
async def get_photo_id(message: types.Message):
    if message.from_user.id in ADMIN_IDS:
        photo_id = message.photo[-1].file_id
        await message.reply(f"🆔 <b>ID для таблиці:</b>\n<code>{photo_id}</code>", parse_mode="HTML")

# --- ЛОГІКА КОРИСТУВАЧА ---

@dp.message_handler(commands=['start'], state="*")
async def send_welcome(message: types.Message, state: FSMContext):
    await state.finish()
    args = message.get_args()
    source_map = {'insta': 'Instagram', 'qr': 'QR Code', 'tg': 'Telegram'}
    user_source = source_map.get(args, "Direct")

    users.register_user(
        user_id=message.from_user.id,
        username=message.from_user.username,
        source=user_source
    )
    await message.answer("Вітаємо у TurboShop! 👟\nОбери категорію для пошуку:", reply_markup=kb.main_menu())

@dp.message_handler(lambda message: message.text in ["👟 Чоловічі", "👠 Жіночі"], state="*")
async def show_brands(message: types.Message):
    category = "Чоловічі" if "Чоловічі" in message.text else "Жіночі"
    user_products[message.from_user.id] = {'category': category}

    # Використовуємо кеш замість прямого запиту
    brands = sorted(list(set([str(item.get('Бренд')).strip() for item in ALL_PRODUCTS if str(item.get('Категорія')).strip() == category])))
    
    if not brands:
        await message.answer("На жаль, зараз порожньо або база оновлюється.")
        return

    await message.answer(f"Обери бренд ({category}):", reply_markup=kb.get_brands_keyboard(brands))

@dp.message_handler(lambda message: message.text.startswith("🔹 "))
async def choose_size(message: types.Message):
    brand = message.text.replace("🔹 ", "").strip()
    user_id = message.from_user.id
    if user_id not in user_products:
        await message.answer("Будь ласка, почни з вибору категорії.")
        return

    user_products[user_id]['brand'] = brand
    # Тут залишаємо як є, або теж переводимо на кеш у db.py
    sizes = db.get_available_sizes(user_products[user_id]['category'], brand)

    if not sizes:
        await message.answer("Розмірів не знайдено.")
        return
    await message.answer(f"Який розмір {brand} шукаємо?", reply_markup=kb.get_sizes_keyboard(sizes))

@dp.callback_query_handler(lambda c: c.data.startswith('size_'), state="*")
async def start_catalog(callback_query: types.CallbackQuery):
    size = callback_query.data.replace("size_", "")
    user_id = callback_query.from_user.id
    if user_id not in user_products: user_products[user_id] = {}
    user_products[user_id]['size'] = size

    # Фільтруємо вже завантажені товари (кеш)
    cat = user_products[user_id].get('category')
    brd = user_products[user_id].get('brand')
    products = [i for i in ALL_PRODUCTS if i.get('Категорія') == cat and i.get('Бренд') == brd and size in str(i.get('Розміри'))]
    
    user_products[user_id]['products'] = products
    if not products:
        await bot.answer_callback_query(callback_query.id, text="Нічого не знайдено.")
        return

    try: await bot.delete_message(chat_id=user_id, message_id=callback_query.message.message_id)
    except: pass
    await show_product(user_id, 0)

async def show_product(user_id, index, message_to_edit=None):
    data = user_products.get(user_id)
    if not data or not data.get('products'): return
    product = data['products'][index]
    total = len(data['products'])

    caption = (
        f"👟 <b>{product.get('Бренд')} {product.get('Модель')}</b>\n"
        f"💰 Ціна: <b>{product.get('Ціна')} грн</b>\n"
        f"📏 Розмір: {data['size']}\n"
        f"🆔 Артикул: <code>{product.get('Артикул')}</code>"
    )
    photo = str(product.get('Фото')).split(',')[0].strip()
    reply_markup = kb.get_product_navigation(index, total, product.get('Артикул'))

    if message_to_edit:
        try:
            media = types.InputMediaPhoto(photo, caption=caption, parse_mode="HTML")
            await bot.edit_message_media(chat_id=user_id, message_id=message_to_edit, media=media, reply_markup=reply_markup)
        except: pass
    else:
        await bot.send_photo(user_id, photo, caption=caption, parse_mode="HTML", reply_markup=reply_markup)

@dp.callback_query_handler(lambda c: c.data.startswith(('next_', 'prev_')), state="*")
async def paginate(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id)
    action, index = callback_query.data.split('_')
    new_index = int(index) + 1 if action == 'next' else int(index) - 1
    user_id = callback_query.from_user.id
    if user_id in user_products and 0 <= new_index < len(user_products[user_id]['products']):
        await show_product(user_id, new_index, callback_query.message.message_id)

# --- ОФОРМЛЕННЯ ЗАМОВЛЕННЯ ---

@dp.callback_query_handler(lambda c: c.data.startswith('buy_'), state="*")
async def process_buy(callback_query: types.CallbackQuery, state: FSMContext):
    index = int(callback_query.data.split('_')[1])
    product = user_products[callback_query.from_user.id]['products'][index]
    await state.update_data(item=f"{product.get('Бренд')} {product.get('Model')}", article=product.get('Артикул'), price=product.get('Ціна'), username=callback_query.from_user.username or "no_username")
    await OrderState.waiting_for_phone.set()
    await bot.send_message(callback_query.from_user.id, "🚀 Чудовий вибір! Поділіться номером телефону:", reply_markup=kb.get_contact_keyboard())

@dp.message_handler(content_types=['contact'], state=OrderState.waiting_for_phone)
async def get_phone(message: types.Message, state: FSMContext):
    await state.update_data(phone=message.contact.phone_number)
    await OrderState.next()
    await message.answer("✅ Номер отримано. ПІБ отримувача:", reply_markup=types.ReplyKeyboardRemove())

@dp.message_handler(state=OrderState.waiting_for_fio)
async def get_fio(message: types.Message, state: FSMContext):
    await state.update_data(fio=message.text)
    await OrderState.next()
    await message.answer("📦 Місто та номер відділення Нової Пошти:")

@dp.message_handler(state=OrderState.waiting_for_delivery)
async def get_delivery(message: types.Message, state: FSMContext):
    await state.update_data(delivery=message.text)
    order_data = await state.get_data()
    try: requests.post(GAS_URL, json=order_data, timeout=15)
    except: logging.error("GAS Order Post Error")

    admin_text = f"🔥 <b>НОВЕ ЗАМОВЛЕННЯ!</b>\n\n👟 Товар: {order_data['item']}\n🆔 Артикул: {order_data['article']}\n📱 Тел: {order_data['phone']}\n👤 ПІБ: {order_data['fio']}\n📍 Доставка: {order_data['delivery']}"
    for admin in ADMIN_IDS:
        try: await bot.send_message(admin, admin_text, parse_mode="HTML")
        except: pass

    await message.answer("✅ ВАШЕ ЗАМОВЛЕННЯ УСПІШНО ПРИЙНЯТО!\nМенеджер зв'яжеться з вами найближчим часом. 🚀", reply_markup=kb.main_menu())
    await state.finish()

@dp.message_handler(lambda message: message.text == "⬅️ Назад", state="*")
async def go_back(message: types.Message, state: FSMContext):
    await send_welcome(message, state)

if __name__ == '__main__':
    print("🚀 TurboShop Engine v3.0 (Railway + Multi-Admin) запуск...")
    loop = asyncio.get_event_loop()
    loop.create_task(update_cache_task()) # Запускаємо кеш
    executor.start_polling(dp, skip_updates=True)
