import os
import logging
import requests
import asyncio
from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
import keyboards as kb
import database as db

logger = logging.getLogger(__name__)

ADMIN_IDS = [int(i.strip()) for i in os.getenv("ADMIN_IDS", "").split(",") if i.strip()]
GAS_URL = os.getenv("GAS_URL")

class OrderState(StatesGroup):
    waiting_for_phone = State()
    waiting_for_fio = State()
    waiting_for_delivery = State()

async def process_buy(callback_query: types.CallbackQuery, state: FSMContext, ALL_PRODUCTS):
    # Тепер тут прилітає артикул (наприклад: AS-1090), а не "0"
    article = callback_query.data.replace("buy_", "").strip()
    
    user_data = await state.get_data()
    selected_size = user_data.get('size', 'Не вказано')

    def normalize(val):
        return str(val).strip().lower().replace("–", "-")

    # Шукаємо товар по артикулу
    product = next(
        (i for i in ALL_PRODUCTS if normalize(i.get('Артикул')) == normalize(article)), 
        None
    )

    if not product:
        logger.error(f"❌ ТОВАР НЕ ЗНАЙДЕНО. Артикул: '{article}'")
        await callback_query.answer("❌ Товар більше не доступний.", show_alert=True)
        return

    photo_field = str(product.get('Фото', ''))
    photos = [p.strip() for p in photo_field.split(',') if p.strip() and p.lower() != "none"]
    main_photo = photos[0] if photos else "https://via.placeholder.com/500"

    model_name = product.get('Model') or product.get('Модель') or ""

    await state.update_data(
        item=f"{product.get('Бренд')} {model_name}".strip(), 
        article=str(article), 
        price=str(product.get('Ціна', '0')),
        photo=main_photo,
        size=selected_size
    )
    
    await OrderState.waiting_for_phone.set()
    await callback_query.message.answer(
        "🚀 Залишилося зовсім трохи!\nПоділися номером телефону через кнопку нижче: 👇", 
        reply_markup=kb.get_contact_keyboard()
    )
    await callback_query.answer()

async def get_phone(message: types.Message, state: FSMContext):
    if not message.contact:
        await message.answer("Будь ласка, натисни кнопку 'Надіслати контакт' 📱")
        return
    await state.update_data(phone=message.contact.phone_number)
    await OrderState.next()
    await message.answer("✅ Прийнято! Тепер напиши ПІБ отримувача:", reply_markup=types.ReplyKeyboardRemove())

async def get_fio(message: types.Message, state: FSMContext):
    if len(message.text) < 5:
        await message.answer("Напиши повне ПІБ (Прізвище, Ім'я, По батькові)")
        return
    await state.update_data(fio=message.text)
    await OrderState.next()
    await message.answer("📦 Вкажи місто та № відділення Нової Пошти:")

async def get_delivery(message: types.Message, state: FSMContext, bot):
    await state.update_data(delivery=message.text)
    data = await state.get_data()
    user_id = message.from_user.id
    
    item_name = data.get("item", "—")
    price = data.get("price", "0")
    article = data.get("article", "—")
    fio = data.get("fio", "—")
    delivery = data.get("delivery", "—")
    size = data.get("size", "—")
    
    username = message.from_user.username
    user_display = f"@{username}" if username else f"ID: {user_id}"
    
    phone = "".join(filter(str.isdigit, str(data.get('phone', ''))))
    if not phone.startswith('38') and len(phone) == 10:
        phone = f"38{phone}"
    phone_formatted = f"+{phone}"

    # Адмін-повідомлення
    admin_msg = (
        f"🛍 <b>НОВЕ ЗАМОВЛЕННЯ!</b>\n"
        f"───────────────────\n"
        f"⠀👟 <b>{item_name}</b>\n"
        f"⠀🆔 Артикул: <code>{article}</code>\n"
        f"⠀📏 Розмір: <b>{size}</b>\n\n"
        f"👤 Клієнт: {fio}\n"
        f"📱 Тел: <code>{phone_formatted}</code>\n"
        f"✈️ НП: {delivery}\n"
        f"🔗 Юзер: {user_display}"
    )

    admin_kb = types.InlineKeyboardMarkup(row_width=1)
    chat_link = f"https://t.me/{username}" if username else f"tg://user?id={user_id}"
    admin_kb.add(
        types.InlineKeyboardButton("💬 Чат з клієнтом", url=chat_link),
        types.InlineKeyboardButton("📞 Зателефонувати", url=f"tel:{phone_formatted}")
    )

    for admin in ADMIN_IDS:
        try:
            await bot.send_message(admin, admin_msg, parse_mode="HTML", reply_markup=admin_kb)
        except:
            pass

    # Клієнт-повідомлення
    client_msg = (
        f"✅ <b>ЗАМОВЛЕННЯ ПРИЙНЯТО!</b>\n\n"
        f"<b>Твій вибір:</b> {item_name}\n"
        f"💰 До сплати: <b>{price} грн</b>\n"
        f"📏 Розмір: <b>{size}</b>\n\n"
        f"🚀 Менеджер скоро зв'яжеться з тобою!"
    )
    
    try:
        await bot.send_photo(user_id, data.get('photo'), caption=client_msg, parse_mode="HTML", reply_markup=kb.main_menu())
    except:
        await message.answer(client_msg, parse_mode="HTML", reply_markup=kb.main_menu())

    # Лог в таблицю
    payload = {
        "item": item_name, "article": article, "price": price,
        "phone": phone_formatted, "fio": fio, "delivery": delivery,
        "user": user_display, "size": size
    }
    
    async def log_to_gas():
        try:
            requests.post(GAS_URL, json=payload, timeout=10)
        except:
            pass

    asyncio.create_task(log_to_gas())
    await state.finish()
