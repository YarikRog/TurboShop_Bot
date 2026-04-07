import os
import logging
import aiohttp
import asyncio
from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
import keyboards as kb

logger = logging.getLogger("TurboBot.Order")

ADMIN_IDS = [int(i.strip()) for i in os.getenv("ADMIN_IDS", "").split(",") if i.strip()]
GAS_URL = os.getenv("GAS_URL")

class OrderState(StatesGroup):
    waiting_for_phone = State()
    waiting_for_fio = State()
    waiting_for_delivery = State()

async def process_buy(callback_query: types.CallbackQuery, state: FSMContext, ALL_PRODUCTS):
    # Отримуємо артикул з callback_data
    article = callback_query.data.replace("buy_", "").strip()
    
    # Шукаємо товар у переданому кеші (нормалізовано)
    product = next((i for i in ALL_PRODUCTS if str(i.get('Артикул', '')).strip().lower() == article.lower()), None)

    if not product:
        return await callback_query.answer("❌ Помилка: товар не знайдено в базі.", show_alert=True)

    user_data = await state.get_data()
    
    # Зберігаємо дані для фіналу
    photo_field = str(product.get('Фото', ''))
    main_photo = [p.strip() for p in photo_field.split(',') if p.strip()][0] if photo_field else ""

    await state.update_data(
        item=f"{product.get('Бренд')} {product.get('Модель') or product.get('Model')}".strip(),
        article=article,
        price=str(product.get('Ціна', '0')),
        photo=main_photo,
        size=user_data.get('size', '—')
    )
    
    await OrderState.waiting_for_phone.set()
    await callback_query.message.answer(
        "🚀 <b>Майже готово!</b>\nНатисніть кнопку нижче, щоб поділитися номером телефону:",
        reply_markup=kb.get_contact_keyboard(),
        parse_mode="HTML"
    )
    await callback_query.answer()

async def get_phone(message: types.Message, state: FSMContext):
    if not message.contact:
        return await message.answer("Будь ласка, використовуйте кнопку 'Поділитися номером' 📱")
        
    await state.update_data(phone=message.contact.phone_number)
    await OrderState.next()
    await message.answer("✅ Записав. Тепер напишіть ПІБ отримувача:", reply_markup=types.ReplyKeyboardRemove())

async def get_fio(message: types.Message, state: FSMContext):
    if len(message.text) < 5:
        return await message.answer("Будь ласка, напишіть повне Прізвище та Ім'я")
        
    await state.update_data(fio=message.text.strip())
    await OrderState.next()
    await message.answer("📦 Вкажіть місто та номер відділення Нової Пошти:")

async def get_delivery(message: types.Message, state: FSMContext, bot):
    await state.update_data(delivery=message.text.strip())
    data = await state.get_data()
    
    # Підготовка даних (Форматування телефону)
    raw_phone = "".join(filter(str.isdigit, str(data.get('phone', ''))))
    phone_formatted = f"+{raw_phone}" if raw_phone.startswith('38') else f"+38{raw_phone}"

    # Відправка адмінам
    admin_text = (
        f"⚡️ <b>НОВЕ ЗАМОВЛЕННЯ</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"👟 <b>{data.get('item')}</b>\n"
        f"🆔 Артикул: <code>{data.get('article')}</code>\n"
        f"📏 Розмір: <b>{data.get('size')}</b>\n"
        f"💰 Ціна: {data.get('price')} грн\n"
        f"━━━━━━━━━━━━━━\n"
        f"👤 Клієнт: {data.get('fio')}\n"
        f"📱 Тел: <code>{phone_formatted}</code>\n"
        f"📍 Доставка: {data.get('delivery')}\n"
        f"🔗 Юзер: @{message.from_user.username or 'без_юзернейму'}"
    )

    for admin in ADMIN_IDS:
        try:
            await bot.send_message(admin, admin_text, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Admin alert failed: {e}")

    # Відправка клієнту
    await message.answer("✅ <b>Дякуємо! Замовлення прийнято.</b>\nМенеджер зв'яжеться з вами найближчим часом.", reply_markup=kb.main_menu(), parse_mode="HTML")

    # АСИНХРОННИЙ запис у таблицю (БЕЗ BLOCKING)
    payload = {
        "item": data.get('item'),
        "article": data.get('article'),
        "price": data.get('price'),
        "phone": phone_formatted,
        "fio": data.get('fio'),
        "delivery": data.get('delivery'),
        "user": f"@{message.from_user.username or message.from_user.id}",
        "size": data.get('size')
    }

    async def send_to_gas():
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(GAS_URL, json=payload, timeout=10) as r:
                    if r.status != 200:
                        logger.error(f"GAS error: {r.status}")
            except Exception as e:
                logger.error(f"GAS connection error: {e}")

    asyncio.create_task(send_to_gas())
    await state.finish()
