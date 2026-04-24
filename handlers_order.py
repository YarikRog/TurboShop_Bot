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
ADMIN_NOTIFY_CHAT_ID = os.getenv("ADMIN_NOTIFY_CHAT_ID", "").strip()
MANAGER_USERNAME = os.getenv("MANAGER_USERNAME", "").strip()
CURRENCY = os.getenv("CURRENCY", "грн").strip()
ORDER_SUCCESS_TEXT = os.getenv(
    "ORDER_SUCCESS_TEXT",
    "✅ Дякуємо! Замовлення прийнято. Менеджер скоро зв’яжеться з вами."
).strip()
DELIVERY_PROMPT = os.getenv(
    "DELIVERY_PROMPT",
    "🚚 Вкажіть місто та номер відділення Нової Пошти.\nНаприклад: Київ, НП №12"
).strip()


class OrderState(StatesGroup):
    waiting_for_phone = State()
    waiting_for_fio = State()
    waiting_for_delivery = State()
    confirmation = State()


def _get_product_article(product):
    return str(product.get("Артикул") or product.get("article") or "").strip()


def _get_product_title(product):
    brand = str(product.get("Бренд") or product.get("brand") or "").strip()
    model = str(product.get("Модель") or product.get("Model") or product.get("model") or "").strip()
    title = f"{brand} {model}".strip()
    return title or "Товар"


def _parse_photo_ids(raw_photos):
    raw = str(raw_photos or "")
    for delimiter in (";", "\n", "\r"):
        raw = raw.replace(delimiter, ",")
    return [item.strip() for item in raw.split(",") if item.strip() and item.strip().lower() != "none"]


def _normalize_phone(raw_phone):
    raw_phone = str(raw_phone or "").strip()
    digits = "".join(ch for ch in raw_phone if ch.isdigit())

    if len(digits) == 10 and digits.startswith("0"):
        return "+38" + digits

    if len(digits) == 12 and digits.startswith("380"):
        return "+" + digits

    if len(digits) == 13 and digits.startswith("380"):
        return "+" + digits[-12:]

    if raw_phone.startswith("+") and len(digits) >= 10:
        return "+" + digits

    if len(digits) >= 10:
        return digits

    return ""


def _is_invalid_size(size):
    size = str(size or "").strip()
    return not size or size in {"—", "Оберіть розмір", "New Arrivals", "Не вказано"}


def _order_summary_text(data):
    return (
        f"🧾 <b>Перевірте замовлення</b>\n\n"
        f"👟 Товар: <b>{data.get('item', '—')}</b>\n"
        f"🆔 Артикул: <code>{data.get('article', '—')}</code>\n"
        f"📏 Розмір: <b>{data.get('size', '—')}</b>\n"
        f"💰 Ціна: <b>{data.get('price', '—')} {CURRENCY}</b>\n\n"
        f"👤 Ім’я: <b>{data.get('fio', '—')}</b>\n"
        f"📱 Телефон: <b>{data.get('phone', '—')}</b>\n"
        f"🚚 Доставка: <b>{data.get('delivery', '—')}</b>\n\n"
        f"Якщо все правильно — натисніть <b>✅ Підтвердити замовлення</b>."
    )


def _admin_order_text(data, user):
    username = f"@{user.username}" if user.username else f"ID: {user.id}"
    source = data.get("source", "direct")

    return (
        f"🔥 <b>НОВЕ ЗАМОВЛЕННЯ</b>\n\n"
        f"👟 Товар: <b>{data.get('item', '—')}</b>\n"
        f"🆔 Артикул: <code>{data.get('article', '—')}</code>\n"
        f"📏 Розмір: <b>{data.get('size', '—')}</b>\n"
        f"💰 Ціна: <b>{data.get('price', '—')} {CURRENCY}</b>\n\n"
        f"👤 Клієнт: <b>{data.get('fio', '—')}</b>\n"
        f"📱 Телефон: <b>{data.get('phone', '—')}</b>\n"
        f"🚚 Доставка: <b>{data.get('delivery', '—')}</b>\n\n"
        f"👤 Telegram: {username}\n"
        f"📌 Джерело: {source}"
    )


async def process_buy(callback_query: types.CallbackQuery, state: FSMContext, ALL_PRODUCTS):
    article = callback_query.data.replace("buy_", "").strip()
    product = next((i for i in ALL_PRODUCTS if _get_product_article(i) == article), None)

    if not product:
        product = await db.get_product_by_article(article)

    if not product:
        return await callback_query.answer("❌ Помилка: товар не знайдено.", show_alert=True)

    data = await state.get_data()
    selected_size = str(data.get("size", "")).strip()

    if _is_invalid_size(selected_size):
        return await callback_query.answer("Спочатку оберіть розмір.", show_alert=True)

    photos = _parse_photo_ids(product.get("Фото") or product.get("photo_ids") or "")

    await state.update_data(
        item=_get_product_title(product),
        product_id=str(product.get("product_id", "")).strip(),
        article=article,
        price=str(product.get("Ціна") or product.get("price") or "0"),
        photo=photos[0] if photos else None,
        size=selected_size,
    )

    await OrderState.waiting_for_phone.set()

    await callback_query.message.answer(
        f"✅ Розмір <b>{selected_size}</b> обрано.\n\n"
        f"📲 Тепер надішліть номер телефону для оформлення замовлення.\n"
        f"Можна натиснути кнопку нижче або ввести номер вручну.",
        reply_markup=kb.get_contact_keyboard(),
        parse_mode="HTML",
    )
    await callback_query.answer()


async def get_phone(message: types.Message, state: FSMContext):
    raw_phone = message.contact.phone_number if message.contact else message.text
    phone = _normalize_phone(raw_phone)

    if not phone:
        return await message.answer(
            "❌ Вкажіть коректний номер телефону.\nНаприклад: +380671234567",
            reply_markup=kb.get_contact_keyboard(),
        )

    await state.update_data(phone=phone)
    await OrderState.waiting_for_fio.set()

    await message.answer(
        "👤 Як до вас звертатись?\nНаприклад: Ярослав",
        reply_markup=kb.get_cancel_keyboard(),
    )


async def get_fio(message: types.Message, state: FSMContext):
    fio = str(message.text or "").strip()

    if len(fio) < 2:
        return await message.answer(
            "❌ Ім’я занадто коротке. Напишіть, будь ласка, як до вас звертатись.",
            reply_markup=kb.get_cancel_keyboard(),
        )

    await state.update_data(fio=fio)
    await OrderState.waiting_for_delivery.set()

    await message.answer(
        DELIVERY_PROMPT,
        reply_markup=kb.get_cancel_keyboard(),
    )


async def get_delivery(message: types.Message, state: FSMContext, bot):
    delivery = str(message.text or "").strip()

    if len(delivery) < 5:
        return await message.answer(
            "❌ Дані доставки занадто короткі.\nВкажіть місто та номер відділення Нової Пошти.",
            reply_markup=kb.get_cancel_keyboard(),
        )

    await state.update_data(delivery=delivery)
    await OrderState.confirmation.set()

    data = await state.get_data()

    await message.answer(
        _order_summary_text(data),
        parse_mode="HTML",
        reply_markup=kb.get_order_confirmation_keyboard(),
    )


async def edit_order_phone(message: types.Message, state: FSMContext):
    await OrderState.waiting_for_phone.set()
    await message.answer(
        "📲 Надішліть новий номер телефону:",
        reply_markup=kb.get_contact_keyboard(),
    )


async def edit_order_fio(message: types.Message, state: FSMContext):
    await OrderState.waiting_for_fio.set()
    await message.answer(
        "👤 Напишіть нове ім’я:",
        reply_markup=kb.get_cancel_keyboard(),
    )


async def edit_order_delivery(message: types.Message, state: FSMContext):
    await OrderState.waiting_for_delivery.set()
    await message.answer(
        DELIVERY_PROMPT,
        reply_markup=kb.get_cancel_keyboard(),
    )


async def confirm_order(message: types.Message, state: FSMContext, bot):
    data = await state.get_data()

    required_fields = ["article", "item", "size", "price", "fio", "phone", "delivery"]
    missing = [field for field in required_fields if not str(data.get(field, "")).strip()]

    if missing:
        logger.warning("Order confirmation missing fields: %s", missing)
        await state.finish()
        return await message.answer(
            "❌ Не вистачає даних для замовлення. Спробуйте оформити ще раз.",
            reply_markup=kb.main_menu(admin.is_admin(message.from_user.id)),
        )

    source = data.get("source", "direct")

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
        return await message.answer(
            "❌ Не вдалося зберегти замовлення. Спробуйте ще раз або напишіть менеджеру.",
            reply_markup=kb.get_order_confirmation_keyboard(),
        )

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

    text_admin = _admin_order_text(data, message.from_user)

    notify_targets = []

    if ADMIN_NOTIFY_CHAT_ID:
        try:
            notify_targets.append(int(ADMIN_NOTIFY_CHAT_ID))
        except ValueError:
            logger.warning("ADMIN_NOTIFY_CHAT_ID is not numeric: %s", ADMIN_NOTIFY_CHAT_ID)

    notify_targets.extend(ADMIN_IDS)
    notify_targets = list(dict.fromkeys(notify_targets))

    for chat_id in notify_targets:
        try:
            await bot.send_message(chat_id, text_admin, parse_mode="HTML")
        except Exception as exc:
            logger.warning("Failed to send admin notification to %s: %s", chat_id, exc)

    await state.finish()

    await message.answer(
        ORDER_SUCCESS_TEXT,
        reply_markup=kb.get_after_order_keyboard(
            manager_username=MANAGER_USERNAME,
            is_admin=admin.is_admin(message.from_user.id),
        ),
    )