import os
import logging
from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
import keyboards as kb
import database as db
import handlers_admin as admin

logger = logging.getLogger("TurboBot.Order")

ADMIN_IDS = [int(i.strip()) for i in os.getenv("ADMIN_IDS", "").split(",") if i.strip().isdigit()]

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
    selected_size = str(data.get("size", "")).strip()
    if not selected_size or selected_size in {"—", "Оберіть розмір", "New Arrivals", "Не вказано"}:
        return await callback_query.answer("Спочатку оберіть розмір.", show_alert=True)

    photos = [p.strip() for p in str(product.get('Фото', '')).split(',') if p.strip()]
    
    await state.update_data(
        item=f"{product.get('Бренд')} {product.get('Модель') or product.get('Model', '')}",
        product_id=str(product.get("product_id", "")).strip(),
        article=article,
        price=str(product.get('Ціна', '0')),
        photo=photos[0] if photos else None,
        size=selected_size
    )
    
    await OrderState.waiting_for_phone.set()
    await callback_query.message.answer(
        "📲 Надішліть ваш контакт для оформлення або введіть номер вручну:",
        reply_markup=kb.get_contact_keyboard(),
    )
    await callback_query.answer()

async def get_phone(message: types.Message, state: FSMContext):
    phone = message.contact.phone_number if message.contact else message.text
    digits = "".join(ch for ch in str(phone) if ch.isdigit())
    if len(digits) < 10:
        return await message.answer("Вкажіть коректний номер телефону.", reply_markup=kb.get_contact_keyboard())

    await state.update_data(phone=phone)
    await OrderState.next()
    await message.answer("📝 Введіть ПІБ отримувача:", reply_markup=kb.get_cancel_keyboard())

async def get_fio(message: types.Message, state: FSMContext):
    if not str(message.text).strip():
        return await message.answer("ПІБ не може бути порожнім.", reply_markup=kb.get_cancel_keyboard())

    await state.update_data(fio=message.text)
    await OrderState.next()
    await message.answer("✈️ Вкажіть місто та номер відділення Нової Пошти:", reply_markup=kb.get_cancel_keyboard())

async def get_delivery(message: types.Message, state: FSMContext, bot):
    if not str(message.text).strip():
        return await message.answer("Дані доставки не можуть бути порожніми.", reply_markup=kb.get_cancel_keyboard())

    await state.update_data(delivery=message.text)
    data = await state.get_data()
    await state.finish()

    username = f"@{message.from_user.username}" if message.from_user.username else f"ID: {message.from_user.id}"
    source = data.get("source", "direct")
    text_admin = (
        f"🛍 <b>ЗАМОВЛЕННЯ</b>\n"
        f"Товар: {data['item']} ({data['article']})\n"
        f"Розмір: {data['size']}\n"
        f"Клієнт: {data['fio']}\n"
        f"Тел: {data['phone']}\n"
        f"Доставка: {data['delivery']}\n"
        f"Юзер: {username}\n"
        f"Джерело: {source}"
    )

    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, text_admin, parse_mode="HTML")
        except Exception:
            pass

    order_payload = {
        "product_id": data.get("product_id", ""),
        "article": data["article"],
        "item": data["item"],
        "size": data["size"],
        "price": data["price"],
        "customer_name": data["fio"],
        "phone": data["phone"],
        "delivery": data["delivery"],
        "telegram_id": message.from_user.id,
        "telegram_username": message.from_user.username or "",
        "source": source,
        "status": "new",
    }
    order_result = await db.create_order(order_payload)
    if order_result is None:
        logger.warning("Order was not confirmed by GAS for article %s", data["article"])

    user_result = await db.register_user(
        {
            "telegram_id": message.from_user.id,
            "username": message.from_user.username or "",
            "source": source,
            "increment_orders": True,
        }
    )
    if user_result is None:
        logger.warning("User upsert was not confirmed by GAS for telegram_id=%s", message.from_user.id)

    await message.answer(
        "✅ Дякуємо! Замовлення прийнято. Менеджер зв'яжеться з вами.",
        reply_markup=kb.main_menu(admin.is_admin(message.from_user.id)),
    )
