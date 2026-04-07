import os
import aiohttp
import logging

GAS_URL = os.getenv("GAS_URL")
logger = logging.getLogger("TurboBot.DB")

async def get_all_items():
    if not GAS_URL:
        logger.error("GAS_URL is not set!")
        return []
        
    try:
        # Асинхронний запит з жорстким таймаутом
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(GAS_URL) as resp:
                if resp.status == 200:
                    return await resp.json()
                logger.error(f"DB error status: {resp.status}")
                return []
    except Exception as e:
        logger.error(f"DB fetching error: {e}")
        return []
