import os
import logging
import requests
import asyncio
from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
import keyboards as kb
import database as db

ADMIN_IDS = [int(i.strip()) for i in os.getenv("ADMIN_IDS", "").split(",") if i.strip()]
GAS_URL = os.getenv("GAS_URL")

class OrderState(StatesGroup):
    waiting_for_phone = State()
    waiting_for_fio = State()
    waiting_for_delivery = State()

async def process_buy(callback_query: types.CallbackQuery, state: FSMContext, user_products, ALL_PRODUCTS):
    index = int(callback_query.data.split('_')[1])
    user_id = callback_query.from_user.id
    
    # БЕРЕМО ДАНІ БЕЗПЕЧНО
    user_data_items = user_products.get(user_id, {}).get('products', [])
    if not user_data_items or index >= len(user_data_items):
        await callback_query.answer("⚠️ Помилка даних. Оберіть товар знову.", show_alert=True)
        return
        
    product = user_data_items[index]
    photos = db.get_product_photos(ALL_PRODUCTS, product.get('Артикул'))
    main_photo = photos[0] if photos else "https://via.placeholder.com/500"

    await state.update_data(
        item=f"{product.get('Бренд')} {product.get('Модель')}", 
        article=str(product.get('Артикул', '—')), 
        price=str(product.get('Ціна', '0')),
        photo=main_photo,
        size=user_products.get(user_id, {}).get('size', 'Не вказано')
    )
    
    await OrderState.waiting_for_phone.set()
    await callback_query.message.answer("🚀 Поділіться номером телефону за допомогою кнопки:", reply_markup=kb.get_contact_keyboard())

async def get_phone(message: types.Message, state: FSMContext):
    if not message.contact:
        await message.answer("Будь ласка, натисніть на кнопку 'Надіслати контакт' 👇")
        return
    await state.update_data(phone=message.contact.phone_number)
    await OrderState.next()
    await message.answer("✅ Тепер вкажіть ПІБ отримувача:", reply_markup=types.ReplyKeyboardRemove())

async def get_fio(message: types.Message, state: FSMContext):
    await state.update_data(fio=message.text)
    await OrderState.next()
    await message.answer("📦 Місто та № відділення Нової Пошти:")

async def get_delivery(message: types.Message, state: FSMContext, bot):
    await state.update_data(delivery=message.text)
    data = await state.get_data()
    user_id = message.from_user.id
    
    # Форматуємо телефон
    phone = "".join(filter(str.isdigit, str(data.get('phone', ''))))
    if not phone.startswith('38') and len(phone) <= 10: phone = f"38{phone}"
    phone_link = f"+{phone}"

    username = f"@{message.from_user.username}" if message.from_user.username else f"ID: {user_id}"

    # --- КРОК 1: МИТТЄВЕ ПОВІДОМЛЕННЯ АДМІНУ ---
    admin_text = (
        f"🛍 <b>НОВЕ ЗАМОВЛЕННЯ!</b>\n"
        f"───────────────────\n"
        f"⠀👟 <b>{data.get('item')}</b>\n"
        f"⠀🆔 Артикул: <code>{data.get('article')}</code>\n"
        f"⠀📏 Розмір: <b>{data.get('size')}</b>\n"
        f"⠀👤 Клієнт: {data.get('fio')}\n"
        f"⠀📱 Тел: <code>{phone_link}</code>\n"
        f"⠀✈️ НП: {data.get('delivery')}\n"
        f"⠀🔗 Юзер: {username}"
    )
    
    admin_kb = types.InlineKeyboardMarkup()
    chat_url = f"https://t.me/{message.from_user.username}" if message.from_user.username else f"tg://user?id={user_id}"
    admin_kb.add(types.InlineKeyboardButton("💬 Чат з клієнтом", url=chat_url))
    admin_kb.add(types.InlineKeyboardButton("📞 Зателефонувати", url=f"tel:{phone_link}"))

    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, admin_text, parse_mode="HTML", reply_markup=admin_kb)
        except Exception as e:
            logging.error(f"Адмін {admin_id} не отримав СМС: {e}")

    # --- КРОК 2: ПІДТВЕРДЖЕННЯ КЛІЄНТУ ---
    client_text = (
        f"✅ <b>ВАШЕ ЗАМОВЛЕННЯ ПРИЙНЯТО!</b>\n\n"
        f"⠀👟 Товар: {data.get('item')}\n"
        f"⠀💰 Ціна: {data.get('price')} грн\n"
        f"⠀📏 Розмір: {data.get('size')}\n"
        f"───────────────────\n"
        f"🚀 Менеджер зв'яжеться з Вами найближчим часом!"
    )
    try:
        await bot.send_photo(user_id, data.get('photo'), caption=client_text, parse_mode="HTML", reply_markup=kb.main_menu())
    except:
        await message.answer(client_text, reply_markup=kb.main_menu())

    # --- КРОК 3: ЗАПИС В ТАБЛИЦЮ (У ФОНІ) ---
    payload = {
        "item": data.get("item"), "article": data.get("article"), 
        "price": data.get("price"), "phone": phone_link,
        "fio": data.get("fio"), "delivery": data.get("delivery"), 
        "user": username, "size": data.get("size")
    }
    try:
        requests.post(GAS_URL, json=payload, timeout=15)
    except:
        pass

    await state.finish()
