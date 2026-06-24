from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from ...core.database import get_db
from ...api.dependencies import get_current_user, is_admin
from ...models.role import Role  # ← Importer le modèle Role

router = APIRouter(prefix="/roles", tags=["Rôles"])


@router.get("/")
def list_roles(
    db: Session = Depends(get_db),
    current_user=Depends(is_admin),
):
   
    roles = db.query(Role).all()
    
    # ✅ Retourner un tableau d'objets
    return [
        {
            "id_role": role.id_role,
            "nom": role.nom,
            "description": getattr(role, 'description', None)
        }
        for role in roles
    ]