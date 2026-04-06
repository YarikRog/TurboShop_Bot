import os
import logging
import requests
import asyncio
from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
import keyboards as kb
import database as db

# Логування для відстеження замовлень
logger = logging.getLogger(__name__)

# Зчитуємо ID адмінів та URL скрипта
ADMIN_IDS = [int(i.strip()) for i in os.getenv("ADMIN_IDS", "").split(",") if i.strip()]
GAS_URL = os.getenv("GAS_URL")

class OrderState(StatesGroup):
    waiting_for_phone = State()
    waiting_for_fio = State()
    waiting_for_delivery = State()

async def process_buy(callback_query: types.CallbackQuery, state: FSMContext, ALL_PRODUCTS):
    # Тепер ми не передаємо індекс через аргумент, а беремо його або ставимо дефолт
    index = int(callback_query.data.split('_')[1])
    user_id = callback_query.from_user.id
    
    # ДІСТАЄМО ДАНІ З ТВОГО НОВОГО REDIS (FSM)
    user_data = await state.get_data()
    product_ids = user_data.get('product_ids', [])
    selected_size = user_data.get('size', 'Не вказано')

    if not product_ids or index >= len(product_ids):
        await callback_query.answer("⚠️ Помилка сесії. Оберіть товар знову.", show_alert=True)
        return
    
    # Отримуємо товар з кешу в main.py (імпортуємо акуратно)
    from main import cache
    article = product_ids[index]
    product = cache.get_by_id(article)

    if not product:
        await callback_query.answer("❌ Товар більше не доступний.", show_alert=True)
        return

    # Готуємо фото для підтвердження
    photo_field = product.get('Фото', '')
    photos = [p.strip() for p in photo_field.split(',') if p.strip() not in ["", "None"]]
    main_photo = photos[0] if photos else "https://via.placeholder.com/500"

    # Зберігаємо все необхідне для замовлення в стан
    await state.update_data(
        item=f"{product.get('Бренд')} {product.get('Модель')}", 
        article=str(article), 
        price=str(product.get('Ціна', '0')),
        photo=main_photo,
        size=selected_size
    )
    
    await OrderState.waiting_for_phone.set()
    await callback_query.message.answer(
        "🚀 Залишилося зовсім трохи!\nПоділися номером телефону за допомогою кнопки нижче: 👇", 
        reply_markup=kb.get_contact_keyboard()
    )

async def get_phone(message: types.Message, state: FSMContext):
    if not message.contact:
        await message.answer("Будь ласка, натисни на кнопку 'Надіслати контакт' 📱")
        return
        
    await state.update_data(phone=message.contact.phone_number)
    await OrderState.next()
    await message.answer("✅ Прийнято! Тепер напиши ПІБ отримувача:", reply_markup=types.ReplyKeyboardRemove())

async def get_fio(message: types.Message, state: FSMContext):
    if len(message.text) < 5:
        await message.answer("Напиши, будь ласка, повне ПІБ (Прізвище, Ім'я, По батькові)")
        return
    await state.update_data(fio=message.text)
    await OrderState.next()
    await message.answer("📦 Вкажи місто та № відділення Нової Пошти:")

async def get_delivery(message: types.Message, state: FSMContext, bot):
    await state.update_data(delivery=message.text)
    data = await state.get_data()
    user_id = message.from_user.id
    
    # Витягуємо дані для фіналізації
    item_name = data.get("item", "—")
    price = data.get("price", "0")
    article = data.get("article", "—")
    fio = data.get("fio", "—")
    delivery = data.get("delivery", "—")
    size = data.get("size", "—")
    
    username = message.from_user.username
    user_display = f"@{username}" if username else f"ID: {user_id}"
    
    # Форматування телефону
    phone = "".join(filter(str.isdigit, str(data.get('phone', ''))))
    if not phone.startswith('38') and len(phone) == 10:
        phone = f"38{phone}"
    phone_formatted = f"+{phone}"

    # --- 1. СПОВІЩЕННЯ АДМІНІВ (Беремо з MANAGERS або ADMIN_IDS) ---
    # Поки що шлемо на ADMIN_IDS, як ти і просив для тестів
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
        except Exception as e:
            logger.error(f"Помилка відправки адміну {admin}: {e}")

    # --- 2. ПІДТВЕРДЖЕННЯ КЛІЄНТУ ---
    client_msg = (
        f"✅ <b>ДЯКУЄМО! ЗАМОВЛЕННЯ ПРИЙНЯТО!</b>\n\n"
        f"<b>Твій вибір:</b>\n"
        f"───────────────────\n"
        f"⠀👟 Модель: <b>{item_name}</b>\n"
        f"⠀💰 До сплати: <b>{price} грн</b>\n"
        f"⠀📏 Розмір: <b>{size}</b>\n"
        f"───────────────────\n\n"
        f"🚀 Менеджер вже обробляє заявку і скоро зв'яжеться з тобою!"
    )
    
    try:
        await bot.send_photo(user_id, data.get('photo'), caption=client_msg, parse_mode="HTML", reply_markup=kb.main_menu())
    except:
        await message.answer(client_msg, parse_mode="HTML", reply_markup=kb.main_menu())

    # --- 3. ЗАПИС В ТАБЛИЦЮ ---
    payload = {
        "item": item_name,
        "article": article,
        "price": price,
        "phone": phone_formatted,
        "fio": fio,
        "delivery": delivery,
        "user": user_display,
        "size": size
    }
    
    # Використовуємо асинхронний запит, щоб бот не "зависав" на час відповіді Google Таблиці
    async def log_to_gas():
        try:
            requests.post(GAS_URL, json=payload, timeout=10)
        except Exception as e:
            logger.error(f"GAS API Error: {e}")

    asyncio.create_task(log_to_gas())
        
    await state.finish()
