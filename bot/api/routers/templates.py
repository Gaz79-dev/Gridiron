from fastapi import APIRouter, Depends, HTTPException, Body
from typing import List
from pydantic import BaseModel

from bot.api import auth
from bot.api.dependencies import get_db
from bot.utils.database import Database
from bot.api.models import SquadTemplate, SquadTemplateCreate, SquadTemplateDefinition

router = APIRouter(
    prefix="/api/templates",
    tags=["templates"],
    dependencies=[Depends(auth.get_current_admin_user)],
)

@router.post("", response_model=SquadTemplate)
async def create_squad_template(
    template_data: SquadTemplateCreate,
    db: Database = Depends(get_db)
):
    """
    Creates a new squad template with its definitions.
    """
    guild_id = 1 
    
    try:
        template_id = await db.create_squad_template(
            guild_id,
            template_data.template_name,
            template_data.definitions
        )
        created_template = await db.get_squad_template_by_id(template_id)
        if not created_template:
            raise HTTPException(status_code=500, detail="Failed to retrieve created template")
        return created_template
    except Exception as e:
        print(f"Error creating template: {e}")
        raise HTTPException(status_code=500, detail="An internal error occurred while creating the template.")


@router.get("", response_model=List[SquadTemplate])
async def get_all_squad_templates(db: Database = Depends(get_db)):
    """
    Retrieves all squad templates.
    """
    return await db.get_all_squad_templates()

# --- NEW: Endpoint to update a template ---
@router.put("/{template_id}", response_model=SquadTemplate)
async def update_squad_template(
    template_id: int,
    template_data: SquadTemplateCreate,
    db: Database = Depends(get_db)
):
    """
    Updates an existing squad template.
    """
    try:
        await db.update_squad_template(
            template_id,
            template_data.template_name,
            template_data.definitions
        )
        updated_template = await db.get_squad_template_by_id(template_id)
        if not updated_template:
            raise HTTPException(status_code=404, detail="Template not found after update")
        return updated_template
    except Exception as e:
        print(f"Error updating template: {e}")
        raise HTTPException(status_code=500, detail="An internal error occurred while updating the template.")


@router.delete("/{template_id}", status_code=204)
async def delete_squad_template(template_id: int, db: Database = Depends(get_db)):
    """
    Deletes a squad template and its definitions.
    """
    await db.delete_squad_template(template_id)
    return
