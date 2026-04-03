#!/usr/bin/python3.10
# -*- coding: utf-8 -*-
import os
import logging
import requests
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from dotenv import load_dotenv

# 1. ЗАВАНТАЖЕННЯ КОНФІГУРАЦІЇ
load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")
GAS_URL = os.getenv("GAS_URL")

# Імпорт твоїх локальних модулів
import database as db
import keyboards as kb
import users  

# 2. НАЛАШТУВАННЯ
logging.basicConfig(level=logging.WARNING)
storage = MemoryStorage()

# --- ТЕПЕР БЕЗ ПРОКСІ (ЧИСТИЙ ЗАПУСК НА RAILWAY) ---
bot = Bot(token=TOKEN)
dp = Dispatcher(bot=bot, storage=storage)

# --- СТАНИ ЗАМОВЛЕННЯ ---
class OrderState(StatesGroup):
    waiting_for_phone = State()
    waiting_for_fio = State()
    waiting_for_delivery = State()

user_products = {}

# --- АДМІН-КОМАНДИ ---

@dp.message_handler(commands=['stats'], state="*")
async def show_stats(message: types.Message):
    """Показує статистику трафіку тільки адміну"""
    if str(message.from_user.id) == str(ADMIN_ID):
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
        else:
            await message.answer("❌ Не вдалося отримати дані з таблиці.")

@dp.message_handler(content_types=['photo'], state="*")
async def get_photo_id(message: types.Message):
    """Отримання ID фото для адміна"""
    if str(message.from_user.id) == str(ADMIN_ID):
        photo_id = message.photo[-1].file_id
        await message.reply(f"🆔 <b>ID для таблиці:</b>\n<code>{photo_id}</code>", parse_mode="HTML")

# --- ЛОГІКА КОРУСТУВАЧА (СТАРТ) ---

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

# --- РОБОТА З КАТАЛОГОМ ---

@dp.message_handler(lambda message: message.text in ["👟 Чоловічі", "👠 Жіночі"], state="*")
async def show_brands(message: types.Message):
    category = "Чоловічі" if "Чоловічі" in message.text else "Жіночі"
    user_products[message.from_user.id] = {'category': category}

    data = db.get_all_items()
    if not data:
        await message.answer("❌ Помилка бази даних.")
        return

    brands = sorted(list(set([str(item.get('Бренд')).strip() for item in data if str(item.get('Категорія')).strip() == category])))
    if not brands:
        await message.answer("На жаль, зараз порожньо.")
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

    products = db.get_items_by_filter(user_products[user_id].get('category'), user_products[user_id].get('brand'), size)
    user_products[user_id]['products'] = products

    if not products:
        await bot.answer_callback_query(callback_query.id, text="Нічого не знайдено.")
        return

    try: await bot.delete_message(chat_id=user_id, message_id=callback_query.message.message_id)
    except: pass

    await show_product(user_id, 0)

# --- ПОКАЗ ТОВАРУ ТА ПАГІНАЦІЯ ---

async def show_product(user_id, index, message_to_edit=None):
    data = user_products.get(user_id)
    if not data or not data.get('products'): return

    total = len(data['products'])
    product = data['products'][index]

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
        except:
            try: await bot.edit_message_caption(chat_id=user_id, message_id=message_to_edit, caption=caption, parse_mode="HTML", reply_markup=reply_markup)
            except: pass
    else:
        await bot.send_photo(user_id, photo, caption=caption, parse_mode="HTML", reply_markup=reply_markup)

@dp.callback_query_handler(lambda c: c.data.startswith(('next_', 'prev_')), state="*")
async def paginate(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id)
    action, index = callback_query.data.split('_')
    new_index = int(index) + 1 if action == 'next' else int(index) - 1
    user_id = callback_query.from_user.id
    if user_id in user_products:
        if 0 <= new_index < len(user_products[user_id]['products']):
            await show_product(user_id, new_index, callback_query.message.message_id)

# --- ДОДАТКОВІ ФУНКЦІЇ ---

@dp.callback_query_handler(lambda c: c.data.startswith('more_photos_'), state="*")
async def show_more_photos(callback_query: types.CallbackQuery):
    article = callback_query.data.replace("more_photos_", "")
    user_id = callback_query.from_user.id
    photos = db.get_product_photos(article)

    if len(photos) <= 1:
        await bot.answer_callback_query(callback_query.id, text="Немає додаткових фото 🧐", show_alert=True)
        return

    await bot.answer_callback_query(callback_query.id, text="Завантажую альбом... ⏳")
    media = types.MediaGroup()
    for i, p in enumerate(photos):
        cap = f"📸 Додаткові фото для артикулу: {article}" if i == 0 else ""
        media.attach_photo(p, caption=cap)

    try: await bot.send_media_group(chat_id=user_id, media=media)
    except: await bot.send_message(user_id, "❌ Помилка завантаження фото.")

@dp.callback_query_handler(lambda c: c.data == 'show_grid_now', state="*")
async def process_grid_independent(callback_query: types.CallbackQuery):
    grid_text = "📏 40-25.5см | 41-26см | 42-26.5см | 43-27.5см | 44-28см | 45-29см"
    await bot.answer_callback_query(callback_query.id, text=grid_text, show_alert=True)

@dp.callback_query_handler(lambda c: c.data == 'ignore_count', state="*")
async def ignore_callback(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id)

# --- ОФОРМЛЕННЯ ЗАМОВЛЕННЯ ---

@dp.callback_query_handler(lambda c: c.data.startswith('buy_'), state="*")
async def process_buy(callback_query: types.CallbackQuery, state: FSMContext):
    index = int(callback_query.data.split('_')[1])
    product = user_products[callback_query.from_user.id]['products'][index]

    await state.update_data(
        item=f"{product.get('Бренд')} {product.get('Модель')}",
        article=product.get('Артикул'),
        price=product.get('Ціна'),
        username=callback_query.from_user.username or "no_username"
    )

    await OrderState.waiting_for_phone.set()
    await bot.send_message(callback_query.from_user.id, "🚀 Чудовий вибір! Поділіться номером телефону:", reply_markup=kb.get_contact_keyboard())
    await bot.answer_callback_query(callback_query.id)

@dp.message_handler(content_types=['contact'], state=OrderState.waiting_for_phone)
async def get_phone(message: types.Message, state: FSMContext):
    await state.update_data(phone=message.contact.phone_number)
    await OrderState.next()
    await message.answer("✅ Номер отримано. Тепер напишіть ПІБ отримувача:", reply_markup=types.ReplyKeyboardRemove())

@dp.message_handler(state=OrderState.waiting_for_fio)
async def get_fio(message: types.Message, state: FSMContext):
    await state.update_data(fio=message.text)
    await OrderState.next()
    await message.answer("📦 Напишіть місто та номер відділення Нової Пошти:")

@dp.message_handler(state=OrderState.waiting_for_delivery)
async def get_delivery(message: types.Message, state: FSMContext):
    await state.update_data(delivery=message.text)
    order_data = await state.get_data()

    try: requests.post(GAS_URL, json=order_data, timeout=15)
    except: logging.error("GAS Order Post Error")

    admin_text = (
        f"🔥 <b>НОВЕ ЗАМОВЛЕННЯ!</b>\n\n"
        f"👟 Товар: {order_data['item']}\n"
        f"🆔 Артикул: <code>{order_data['article']}</code>\n"
        f"💰 Ціна: {order_data['price']} грн\n"
        f"📱 Тел: {order_data['phone']}\n"
        f"👤 ПІБ: {order_data['fio']}\n"
        f"📍 Доставка: {order_data['delivery']}\n"
        f"🔗 Юзер: @{order_data['username']}"
    )
    await bot.send_message(ADMIN_ID, admin_text, parse_mode="HTML")
    await message.answer("✅ Замовлення прийнято! Менеджер зв'яжеться з вами.", reply_markup=kb.main_menu())
    await state.finish()

@dp.message_handler(lambda message: message.text == "⬅️ Назад", state="*")
async def go_back(message: types.Message, state: FSMContext):
    await send_welcome(message, state)

if __name__ == '__main__':
    print("🚀 TurboShop Engine v2.9 (Railway optimized) активовано!")
    executor.start_polling(dp, skip_updates=True)
