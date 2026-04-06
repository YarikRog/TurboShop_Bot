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
    
    # Отримуємо головне фото для підтвердження
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
    
    # Жорстка перевірка юзернейму для таблиці (стовпчик H)
    raw_username = message.from_user.username
    final_username = f"@{raw_username}" if raw_username else f"ID: {user_id}"
    
    # Безпечне форматування номера
    raw_phone = str(user_data.get('phone', ''))
    clean_phone = "".join(filter(str.isdigit, raw_phone))
    if not clean_phone.startswith('38') and len(clean_phone) <= 10:
        clean_phone = f"38{clean_phone}"
    phone_formatted = f"+{clean_phone}"

    # 1. Відправка в GAS (Таблиця)
    payload = {
        "item": user_data.get("item", "—"),
        "article": user_data.get("article", "—"),
        "price": user_data.get("price", "0"),
        "phone": phone_formatted,
        "fio": user_data.get("fio", "—"),
        "delivery": user_data.get("delivery", "—"),
        "user": final_username
    }
    try: 
        requests.post(GAS_URL, json=payload, timeout=5)
    except: 
        pass

    # 2. Повідомлення АДМІНУ (тобі) з кнопкою виклику
    admin_msg = (f"🛍 <b>НОВЕ ЗАМОВЛЕННЯ!</b>\n"
                 f"───────────────────\n"
                 f"⠀👟 <b>{payload['item']}</b>\n"
                 f"⠀🆔 Артикул: <code>{payload['article']}</code>\n"
                 f"⠀👤 Клієнт: {payload['fio']}\n"
                 f"⠀📱 Тел: <code>{phone_formatted}</code>\n"
                 f"⠀✈️ НП: {payload['delivery']}\n"
                 f"⠀🔗 Юзер: {final_username}")

    admin_kb = types.InlineKeyboardMarkup(row_width=1)
    btn_chat = types.InlineKeyboardButton("💬 Чат з клієнтом", url=f"tg://user?id={user_id}")
    btn_call = types.InlineKeyboardButton("📞 Зателефонувати", url=f"tel:{phone_formatted}")
    admin_kb.add(btn_chat, btn_call)

    for admin in ADMIN_IDS:
        try:
            await bot.send_message(admin, admin_msg, parse_mode="HTML", reply_markup=admin_kb)
        except:
            pass
        
    # 3. Підтвердження КЛІЄНТУ (з ФОТО та повною інфою)
    client_msg = (
        f"✅ <b>ВАШЕ ЗАМОВЛЕННЯ ПРИЙНЯТО!</b>\n\n"
        f"<b>Деталі замовлення:</b>\n"
        f"───────────────────\n"
        f"⠀👟 Товар: <b>{payload['item']}</b>\n"
        f"⠀💰 Ціна: <b>{payload['price']} грн</b>\n"
        f"⠀👤 Отримувач: {payload['fio']}\n"
        f"⠀📱 Телефон: {phone_formatted}\n"
        f"⠀✈️ Доставка: {payload['delivery']}\n"
        f"───────────────────\n\n"
        f"🚀 Менеджер зв'яжеться з <b>Вами</b> найближчим часом!"
    )
    
    try:
        await bot.send_photo(user_id, user_data.get('photo'), caption=client_msg, parse_mode="HTML", reply_markup=kb.main_menu())
    except:
        await message.answer(client_msg, parse_mode="HTML", reply_markup=kb.main_menu())
        
    await state.finish()
