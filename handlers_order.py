import os
import logging
import requests
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
    
    if user_id not in user_products:
        await callback_query.answer("⚠️ Помилка сесії. Почніть заново.", show_alert=True)
        return
        
    product = user_products[user_id]['products'][index]
    photos = db.get_product_photos(ALL_PRODUCTS, product.get('Артикул'))
    main_photo = photos[0] if photos else "https://via.placeholder.com/500"

    await state.update_data(
        item=f"{product.get('Бренд')} {product.get('Модель')}", 
        article=str(product.get('Артикул', '—')), 
        price=str(product.get('Ціна', '0')),
        photo=main_photo
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
    user_data = await state.get_data()
    user_id = message.from_user.id
    
    raw_username = message.from_user.username
    final_username = f"@{raw_username}" if raw_username else f"ID: {user_id}"
    
    raw_phone = str(user_data.get('phone', ''))
    clean_phone = "".join(filter(str.isdigit, raw_phone))
    if not clean_phone.startswith('38') and len(clean_phone) <= 10:
        clean_phone = f"38{clean_phone}"
    phone_formatted = f"+{clean_phone}"

    # Формуємо дані для повідомлень
    item_name = user_data.get("item", "—")
    price = user_data.get("price", "0")
    article = user_data.get("article", "—")
    fio = user_data.get("fio", "—")
    delivery = user_data.get("delivery", "—")

    # --- 1. ПОВІДОМЛЕННЯ АДМІНУ (ТОБІ) ---
    admin_msg = (f"🛍 <b>НОВЕ ЗАМОВЛЕННЯ!</b>\n"
                 f"───────────────────\n"
                 f"⠀👟 <b>{item_name}</b>\n"
                 f"⠀🆔 Артикул: <code>{article}</code>\n"
                 f"⠀👤 Клієнт: {fio}\n"
                 f"⠀📱 Тел: <code>{phone_formatted}</code>\n"
                 f"⠀✈️ НП: {delivery}\n"
                 f"⠀🔗 Юзер: {final_username}")

    admin_kb = types.InlineKeyboardMarkup(row_width=1)
    chat_link = f"https://t.me/{raw_username}" if raw_username else f"tg://user?id={user_id}"
    admin_kb.add(
        types.InlineKeyboardButton("💬 Чат з клієнтом", url=chat_link),
        types.InlineKeyboardButton("📞 Зателефонувати", url=f"tel:{phone_formatted}")
    )

    for admin in ADMIN_IDS:
        try:
            await bot.send_message(admin, admin_msg, parse_mode="HTML", reply_markup=admin_kb)
        except Exception as e:
            logging.error(f"Помилка відправки адміну {admin}: {e}")

    # --- 2. ПІДТВЕРДЖЕННЯ КЛІЄНТУ ---
    client_msg = (
        f"✅ <b>ВАШЕ ЗАМОВЛЕННЯ ПРИЙНЯТО!</b>\n\n"
        f"<b>Деталі замовлення:</b>\n"
        f"───────────────────\n"
        f"⠀👟 Товар: <b>{item_name}</b>\n"
        f"⠀💰 Ціна: <b>{price} грн</b>\n"
        f"⠀👤 Отримувач: {fio}\n"
        f"⠀📱 Телефон: {phone_formatted}\n"
        f"⠀✈️ Доставка: {delivery}\n"
        f"───────────────────\n\n"
        f"🚀 Менеджер зв'яжеться з <b>Вами</b> найближчим часом!"
    )
    
    try:
        await bot.send_photo(user_id, user_data.get('photo'), caption=client_msg, parse_mode="HTML", reply_markup=kb.main_menu())
    except:
        await message.answer(client_msg, parse_mode="HTML", reply_markup=kb.main_menu())

    # --- 3. ЗАПИС В ТАБЛИЦЮ (В ОСТАННЮ ЧЕРГУ) ---
    payload = {
        "item": item_name,
        "article": article,
        "price": price,
        "phone": phone_formatted,
        "fio": fio,
        "delivery": delivery,
        "user": final_username
    }
    try: 
        # Таймаут 20 секунд, щоб точно встигло
        requests.post(GAS_URL, json=payload, timeout=20)
    except Exception as e: 
        logging.error(f"GAS Error: {e}")
        
    await state.finish()
