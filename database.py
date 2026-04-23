import os
import logging
import asyncio
from typing import Any

import aiohttp

GAS_URL = os.getenv("GAS_URL")
logger = logging.getLogger("TurboBot.Database")
HTTP_TIMEOUT = aiohttp.ClientTimeout(total=15)


def _normalize_product(item: dict[str, Any]) -> dict[str, Any]:
    product = dict(item or {})

    article = str(product.get("article") or product.get("Артикул") or "").strip()
    brand = str(product.get("brand") or product.get("Бренд") or "").strip()
    model = str(product.get("model") or product.get("Модель") or product.get("Model") or "").strip()
    category = str(product.get("category") or product.get("Категорія") or "").strip()
    season = str(product.get("season") or product.get("Сезон") or "").strip()
    price = product.get("price", product.get("Ціна", ""))
    sizes = str(product.get("sizes") or product.get("Розміри") or "").strip()
    description = str(product.get("description") or product.get("Опис") or "").strip()
    photo_ids = str(product.get("photo_ids") or product.get("Фото") or "").strip()
    status = str(product.get("status") or product.get("Статус") or "draft").strip()
    stock = str(product.get("stock") or product.get("Залишок") or "").strip()
    product_id = product.get("product_id", product.get("ID", product.get("productId", "")))

    product.update(
        {
            "product_id": product_id,
            "article": article,
            "brand": brand,
            "model": model,
            "category": category,
            "season": season,
            "price": price,
            "sizes": sizes,
            "description": description,
            "photo_ids": photo_ids,
            "status": status,
            "stock": stock,
            "Артикул": article,
            "Бренд": brand,
            "Модель": model,
            "Model": model,
            "Категорія": category,
            "Сезон": season,
            "Ціна": price,
            "Розміри": sizes,
            "Опис": description,
            "Фото": photo_ids,
            "Статус": status,
            "Залишок": stock,
        }
    )
    return product


def _extract_products(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [_normalize_product(item) for item in data if isinstance(item, dict)]

    if isinstance(data, dict):
        for key in ("products", "items", "data"):
            value = data.get(key)
            if isinstance(value, list):
                return [_normalize_product(item) for item in value if isinstance(item, dict)]
        if data.get("article") or data.get("Артикул"):
            return [_normalize_product(data)]

    return []


async def _request_json(method: str, params: dict[str, Any] | None = None, payload: dict[str, Any] | None = None):
    if not GAS_URL:
        logger.error("GAS_URL is not defined in environment variables")
        return None

    try:
        async with aiohttp.ClientSession(timeout=HTTP_TIMEOUT) as session:
            async with session.request(method, GAS_URL, params=params, json=payload) as response:
                if response.status != 200:
                    body = await response.text()
                    logger.error("GAS request failed: %s %s", response.status, body[:300])
                    return None

                content_type = response.headers.get("Content-Type", "")
                if "application/json" in content_type.lower():
                    return await response.json()

                text = await response.text()
                logger.warning("GAS returned non-JSON response: %s", text[:300])
                return {"ok": True, "raw": text}
    except asyncio.TimeoutError:
        logger.error("GAS request timed out after %ss", HTTP_TIMEOUT.total)
    except Exception as exc:
        logger.error("Critical GAS request error: %s", exc, exc_info=True)
    return None


async def get_products():
    data = await _request_json("GET")
    return _extract_products(data)


async def get_all_items():
    """Backward-compatible catalog loader used by the current cache."""
    return await get_products()


async def get_product_by_article(article: str):
    article = str(article).strip()
    if not article:
        return None

    data = await _request_json("POST", payload={"action": "get_product_by_article", "article": article})
    products = _extract_products(data)
    if products:
        return products[0]

    all_products = await get_products()
    return next((item for item in all_products if str(item.get("Артикул", "")).strip() == article), None)


async def create_product(payload: dict[str, Any]):
    request_payload = {**payload, "action": "create_product"}
    return await _request_json("POST", payload=request_payload)


async def create_order(payload: dict[str, Any]):
    request_payload = {**payload, "action": "create_order"}
    data = await _request_json("POST", payload=request_payload)
    if data is not None:
        return data

    # Backward compatibility with the legacy order endpoint.
    return await _request_json("POST", payload=payload)


async def register_user(payload: dict[str, Any]):
    request_payload = {**payload, "action": "register_user"}
    return await _request_json("POST", payload=request_payload)


async def create_post_log(payload: dict[str, Any]):
    request_payload = {**payload, "action": "create_post_log"}
    return await _request_json("POST", payload=request_payload)


async def update_product_status(article: str, status: str):
    payload = {"action": "update_product_status", "article": article, "status": status}
    return await _request_json("POST", payload=payload)


async def get_stats():
    return await _request_json("POST", payload={"action": "get_stats"})


def get_available_sizes(all_products, category, brand_name):
    """Швидка фільтрація розмірів без зайвих алокацій."""
    if not all_products:
        return []

    sizes = set()
    category = str(category).strip()
    brand_name = str(brand_name).strip()

    for item in all_products:
        if str(item.get("Категорія")).strip() == category and str(item.get("Бренд")).strip() == brand_name:
            raw_val = str(item.get("Розміри", "")).replace(" ", "")
            if raw_val and raw_val.lower() != "none":
                item_sizes = [s.strip() for s in raw_val.replace(";", ",").split(",") if s.strip()]
                sizes.update(item_sizes)

    try:
        return sorted(
            list(sizes),
            key=lambda value: float(value.replace(",", ".")) if value.replace(",", "", 1).replace(".", "", 1).isdigit() else value,
        )
    except Exception:
        return sorted(list(sizes))
