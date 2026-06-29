import os
from typing import Any, Optional


class ConfigService:
    def __init__(self, db=None):
        self.db = db
        self._cache: dict[str, Any] = {}

    async def get(self, key: str, default: Optional[Any] = None) -> Optional[Any]:
        if key in self._cache:
            return self._cache[key]

        value = None

        if self.db:
            value = await self.db.get_system_setting_value(key)

        if value in [None, ""]:
            value = os.getenv(key.upper(), default)

        self._cache[key] = value
        return value

    async def clear_cache(self):
        self._cache.clear()
