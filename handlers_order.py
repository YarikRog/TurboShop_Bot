import os
import logging
import aiohttp
import asyncio
from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
import keyboards as kb

logger = logging.getLogger("TurboBot.Order")

ADMIN_IDS = [int(i.strip()) for i in os.getenv("ADMIN_IDS", "").split(",") if i.strip().isdigit()]
GAS_URL = os.getenv("GAS_URL")

class OrderState(StatesGroup):
    waiting_for_phone = State()
    waiting_for_fio = State()
    waiting_for_delivery = State()

async def process_buy(callback_query: types.CallbackQuery, state: FSMContext, ALL_PRODUCTS):
    article = callback_query.data.replace("buy_", "").strip()
    product = next((i for i in ALL_PRODUCTS if str(i.get('Артикул', '')).strip() == article), None)

    if not product:
        return await callback_query.answer("❌ Помилка: товар не знайдено.", show_alert=True)

    data = await state.get_data()
    photos = [p.strip() for p in str(product.get('Фото', '')).split(',') if p.strip()]
    
    await state.update_data(
        item=f"{product.get('Бренд')} {product.get('Модель') or product.get('Model', '')}",
        article=article,
        price=str(product.get('Ціна', '0')),
        photo=photos[0] if photos else None,
        size=data.get('size', 'Не вказано')
    )
    
    await OrderState.waiting_for_phone.set()
    await callback_query.message.answer("📲 Надішліть ваш контакт для оформлення:", reply_markup=kb.get_contact_keyboard())
    await callback_query.answer()

async def get_phone(message: types.Message, state: FSMContext):
    phone = message.contact.phone_number if message.contact else message.text
    await state.update_data(phone=phone)
    await OrderState.next()
    await message.answer("📝 Введіть ПІБ отримувача:", reply_markup=types.ReplyKeyboardRemove())

async def get_fio(message: types.Message, state: FSMContext):
    await state.update_data(fio=message.text)
    await OrderState.next()
    await message.answer("✈️ Вкажіть місто та номер відділення Нової Пошти:")

async def get_delivery(message: types.Message, state: FSMContext, bot):
    await state.update_data(delivery=message.text)
    data = await state.get_data()
    await state.finish()

    # Формування даних
    username = f"@{message.from_user.username}" if message.from_user.username else f"ID: {message.from_user.id}"
    text_admin = (
        f"🛍 <b>ЗАМОВЛЕННЯ</b>\n"
        f"Товар: {data['item']} ({data['article']})\n"
        f"Розмір: {data['size']}\n"
        f"Клієнт: {data['fio']}\n"
        f"Тел: {data['phone']}\n"
        f"Доставка: {data['delivery']}\n"
        f"Юзер: {username}"
    )

    # Відправка адмінам
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, text_admin, parse_mode="HTML")
        except: pass

    await message.answer("✅ Дякуємо! Замовлення прийнято. Менеджер зв'яжеться з вами.", reply_markup=kb.main_menu())

    # АСИНХРОННИЙ ЛОГ В ТАБЛИЦЮ (БЕЗ БЛОКУВАННЯ)
    payload = {**data, "user": username}
    asyncio.create_task(send_to_gas(payload))

async def send_to_gas(payload):
    if not GAS_URL: return
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(GAS_URL, json=payload, timeout=10) as resp:
                if resp.status != 200: logger.error(f"GAS Log Error: {resp.status}")
    except Exception as e:
        logger.error(f"GAS Log failure: {e}")
