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

# Імпорт твоїх локальних модулів
import database as db
import keyboards as kb
import users  

# 1. КОНФІГ (Railway Variables)
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = [int(i.strip()) for i in os.getenv("ADMIN_IDS", "").split(",") if i.strip()]
GAS_URL = os.getenv("GAS_URL")

logging.basicConfig(level=logging.WARNING)
storage = MemoryStorage()
bot = Bot(token=TOKEN)
dp = Dispatcher(bot=bot, storage=storage)

# Глобальні змінні
ALL_PRODUCTS = []
user_products = {}

# --- ФОНОВЕ ОНОВЛЕННЯ ---
async def update_cache_task():
    global ALL_PRODUCTS
    while True:
        try:
            data = db.get_all_items()
            if data:
                ALL_PRODUCTS = data
                print(f"✅ Кеш оновлено: {len(ALL_PRODUCTS)} товарів")
        except Exception as e: 
            print(f"❌ Помилка кешу: {e}")
        await asyncio.sleep(600) # Оновлення кожні 10 хв

class OrderState(StatesGroup):
    waiting_for_phone = State()
    waiting_for_fio = State()
    waiting_for_delivery = State()

# --- СЛУЖБОВІ ФУНКЦІЇ ---

async def show_product(user_id, index, message_to_edit=None):
    data = user_products.get(user_id)
    
    # ПЕРЕВІРКА: якщо даних немає (наприклад, після рестарту бота)
    if not data or 'products' not in data or not data['products']:
        await bot.send_message(user_id, "⚠️ Дані застаріли. Будь ласка, почни пошук спочатку через Головне меню.", reply_markup=kb.main_menu())
        return

    product = data['products'][index]
    total = len(data['products'])
    
    caption = (
        f"👟 <b>{product.get('Бренд')} {product.get('Модель')}</b>\n"
        f"💰 Ціна: <b>{product.get('Ціна')} грн</b>\n"
        f"📏 Розмір: {data.get('size', '—')}\n"
        f"🆔 Артикул: <code>{product.get('Артикул')}</code>"
    )
    
    photo = str(product.get('Фото')).split(',')[0].strip()
    markup = kb.get_product_navigation(index, total, product.get('Артикул'))

    if message_to_edit:
        try:
            media = types.InputMediaPhoto(photo, caption=caption, parse_mode="HTML")
            await bot.edit_message_media(chat_id=user_id, message_id=message_to_edit, media=media, reply_markup=markup)
        except:
            pass
    else:
        await bot.send_photo(user_id, photo, caption=caption, parse_mode="HTML", reply_markup=markup)

# --- ХЕНДЛЕРИ ---

@dp.message_handler(commands=['start'], state="*")
async def send_welcome(message: types.Message, state: FSMContext):
    await state.finish()
    users.register_user(message.from_user.id, message.from_user.username, "Direct")
    await message.answer("Вітаємо у TurboShop! 👟\nТут ти знайдеш найкращий стафф.", reply_markup=kb.main_menu())

# НОВИНКИ
@dp.message_handler(lambda message: message.text == "🔥 Наші новинки", state="*")
async def show_novinki(message: types.Message):
    novinki = ALL_PRODUCTS[-10:]
    if not novinki:
        await message.answer("Скоро будуть! 😉")
        return
    user_products[message.from_user.id] = {'products': novinki, 'size': 'Всі'}
    await show_product(message.from_user.id, 0)

# МЕНЕДЖЕР
@dp.message_handler(lambda message: message.text == "💬 Менеджер", state="*")
async def contact_manager(message: types.Message):
    await message.answer("Виникли питання? Пиши нашому менеджеру: @yarik721 👨‍💻")

# КОШИК
@dp.message_handler(lambda message: message.text == "🛒 Кошик", state="*")
async def show_cart(message: types.Message):
    await message.answer("Твій кошик поки порожній. Час щось обрати! 👟")

# ВИБІР СТАТІ
@dp.message_handler(lambda message: message.text in ["👟 Чоловічі", "👠 Жіночі"], state="*")
async def show_brands(message: types.Message):
    category = "Чоловічі" if "Чоловічі" in message.text else "Жіночі"
    user_products[message.from_user.id] = {'category': category}
    brands = sorted(list(set([str(i.get('Бренд')).strip() for i in ALL_PRODUCTS if str(i.get('Категорія')).strip() == category])))
    if not brands:
        await message.answer("На жаль, зараз порожньо.")
        return
    await message.answer(f"Обери бренд ({category}):", reply_markup=kb.get_brands_keyboard(brands))

@dp.message_handler(lambda message: message.text.startswith("🔹 "))
async def choose_size(message: types.Message):
    brand = message.text.replace("🔹 ", "").strip()
    user_id = message.from_user.id
    if user_id not in user_products:
        user_products[user_id] = {}
    user_products[user_id]['brand'] = brand
    sizes = db.get_available_sizes(user_products[user_id].get('category', 'Чоловічі'), brand)
    await message.answer(f"Який розмір {brand} шукаємо?", reply_markup=kb.get_sizes_keyboard(sizes))

@dp.callback_query_handler(lambda c: c.data.startswith('size_'), state="*")
async def start_catalog(callback_query: types.CallbackQuery):
    size = callback_query.data.replace("size_", "")
    u_id = callback_query.from_user.id
    if u_id not in user_products: user_products[u_id] = {}
    user_products[u_id]['size'] = size
    
    cat = user_products[u_id].get('category')
    brd = user_products[u_id].get('brand')
    products = [i for i in ALL_PRODUCTS if i.get('Категорія') == cat and i.get('Бренд') == brd and size in str(i.get('Розміри'))]
    
    user_products[u_id]['products'] = products
    if not products:
        await bot.answer_callback_query(callback_query.id, text="Немає в наявності.", show_alert=True)
        return
    await show_product(u_id, 0)

@dp.callback_query_handler(lambda c: c.data.startswith(('next_', 'prev_')), state="*")
async def paginate(callback_query: types.CallbackQuery):
    action, index = callback_query.data.split('_')
    new_index = int(index) + 1 if action == 'next' else int(index) - 1
    user_id = callback_query.from_user.id
    
    if user_id not in user_products or 'products' not in user_products[user_id]:
        await bot.answer_callback_query(callback_query.id, text="⚠️ Оберіть категорію заново", show_alert=True)
        return

    if 0 <= new_index < len(user_products[user_id]['products']):
        await show_product(user_id, new_index, callback_query.message.message_id)
        await bot.answer_callback_query(callback_query.id)
    else:
        await bot.answer_callback_query(callback_query.id, text="Це кінець списку")

# --- ОФОРМЛЕННЯ ---

@dp.callback_query_handler(lambda c: c.data.startswith('buy_'), state="*")
async def process_buy(callback_query: types.CallbackQuery, state: FSMContext):
    index = int(callback_query.data.split('_')[1])
    user_id = callback_query.from_user.id
    if user_id not in user_products or 'products' not in user_products[user_id]:
        await bot.send_message(user_id, "Помилка сесії. Почніть спочатку.")
        return
        
    product = user_products[user_id]['products'][index]
    await state.update_data(item=f"{product.get('Бренд')} {product.get('Модель')}", article=product.get('Артикул'), price=product.get('Ціна'))
    await OrderState.waiting_for_phone.set()
    await bot.send_message(user_id, "🚀 Поділіться номером телефону:", reply_markup=kb.get_contact_keyboard())

@dp.message_handler(content_types=['contact'], state=OrderState.waiting_for_phone)
async def get_phone(message: types.Message, state: FSMContext):
    await state.update_data(phone=message.contact.phone_number)
    await OrderState.next()
    await message.answer("✅ Тепер ПІБ отримувача:", reply_markup=types.ReplyKeyboardRemove())

@dp.message_handler(state=OrderState.waiting_for_fio)
async def get_fio(message: types.Message, state: FSMContext):
    await state.update_data(fio=message.text)
    await OrderState.next()
    await message.answer("📦 Місто та № відділення Нової Пошти:")

@dp.message_handler(state=OrderState.waiting_for_delivery)
async def get_delivery(message: types.Message, state: FSMContext):
    await state.update_data(delivery=message.text)
    data = await state.get_data()
    try: 
        requests.post(GAS_URL, json=data, timeout=10)
    except: 
        logging.error("Помилка відправки в GAS")
    
    msg = f"🔥 <b>ЗАМОВЛЕННЯ!</b>\n\n👟 {data['item']}\n📱 {data['phone']}\n👤 {data['fio']}\n📍 {data['delivery']}"
    for admin in ADMIN_IDS:
        try: await bot.send_message(admin, msg, parse_mode="HTML")
        except: pass
        
    await message.answer("✅ ВАШЕ ЗАМОВЛЕННЯ УСПІШНО ПРИЙНЯТО!\nМенеджер зв'яжеться з вами. 🚀", reply_markup=kb.main_menu())
    await state.finish()

@dp.message_handler(lambda message: message.text in ["🏠 Головне меню", "⬅️ Назад"], state="*")
async def go_home(message: types.Message, state: FSMContext):
    await send_welcome(message, state)

if __name__ == '__main__':
    print("🚀 TurboShop Engine v3.1 запуск...")
    loop = asyncio.get_event_loop()
    loop.create_task(update_cache_task())
    executor.start_polling(dp, skip_updates=True)
