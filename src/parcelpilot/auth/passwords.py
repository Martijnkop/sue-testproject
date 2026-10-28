from __future__ import annotations

import asyncio

import bcrypt

from parcelpilot.settings import settings


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=settings.bcrypt_rounds)).decode("utf-8")


def check_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


async def hash_password_async(password: str) -> str:
    return await asyncio.to_thread(hash_password, password)


async def check_password_async(password: str, password_hash: str) -> bool:
    return await asyncio.to_thread(check_password, password, password_hash)
