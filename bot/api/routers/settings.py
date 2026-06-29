from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional
from pydantic import BaseModel

from bot.api import auth
from bot.utils.database import Database


router = APIRouter(
    prefix="/api/settings",
    tags=["settings"],
    dependencies=[Depends(auth.get_current_admin_user)],
)


class SystemSetting(BaseModel):
    setting_key: str
    setting_value: Optional[str] = None
    value_type: str = "string"
    category: str = "General"
    description: Optional[str] = None
    editable: bool = True


class SystemSettingUpdate(BaseModel):
    setting_value: Optional[str] = None
    value_type: str = "string"
    category: str = "General"
    description: Optional[str] = None
    editable: bool = True


@router.get("/", response_model=List[SystemSetting])
async def get_settings(db: Database = Depends(auth.get_db)):
    records = await db.get_system_settings()
    return [SystemSetting(**dict(record)) for record in records]


@router.put("/{setting_key}", status_code=status.HTTP_204_NO_CONTENT)
async def update_setting(
    setting_key: str,
    setting: SystemSettingUpdate,
    db: Database = Depends(auth.get_db)
):
    existing_value = await db.get_system_setting_value(setting_key)
    if existing_value is None:
        raise HTTPException(status_code=404, detail="Setting not found")

    await db.upsert_system_setting(
        key=setting_key,
        value=setting.setting_value or "",
        value_type=setting.value_type,
        category=setting.category,
        description=setting.description or "",
        editable=setting.editable,
    )
