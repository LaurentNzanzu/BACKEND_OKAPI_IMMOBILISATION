# backend/app/api/endpoints/qr_code.py
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import Optional
from io import BytesIO

from ...core.database import get_db
from ...models.bien import Bien
from ...services.qr_code_service import QRCodeService
from ...core.security import get_current_user
from ...models.utilisateur import Utilisateur

router = APIRouter(prefix="/qr-code", tags=["QR Code"])

@router.get("/{bien_id}/download")
async def download_qr_code(
    bien_id: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """
    Télécharge le QR code d'un bien au format PNG
    
    Args:
        bien_id: ID du bien
        
    Returns:
        StreamingResponse: Fichier PNG du QR code
    """
    # Récupération du bien
    bien = db.query(Bien).filter(Bien.id_bien == bien_id).first()
    if not bien:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Bien {bien_id} non trouvé"
        )
    
    # Génération du QR code
    qr_service = QRCodeService()
    qr_image = qr_service.generate_qr_code(data=bien.qr_code, bien_id=bien_id)
    
    # Retour du fichier en streaming
    return StreamingResponse(
        BytesIO(qr_image),
        media_type="image/png",
        headers={
            "Content-Disposition": f"attachment; filename=QR-{bien.qr_code}.png"
        }
    )

@router.get("/{bien_id}/view")
async def view_qr_code(
    bien_id: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """
    Récupère le QR code en base64 pour affichage frontend
    
    Args:
        bien_id: ID du bien
        
    Returns:
        dict: QR code en base64
    """
    # Récupération du bien
    bien = db.query(Bien).filter(Bien.id_bien == bien_id).first()
    if not bien:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Bien {bien_id} non trouvé"
        )
    
    # Génération du QR code
    qr_service = QRCodeService()
    qr_image = qr_service.generate_qr_code(data=bien.qr_code, bien_id=bien_id)
    qr_base64 = qr_service.qr_code_to_base64(qr_image)
    
    return {
        "bien_id": bien_id,
        "qr_code": bien.qr_code,
        "image_base64": qr_base64
    }

@router.post("/scan")
async def scan_qr_code(
    qr_data: str,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """
    Recherche un bien à partir de son QR code scanné
    
    Args:
        qr_data: Contenu du QR code scanné
        
    Returns:
        dict: Informations du bien trouvé
    """
    # Recherche du bien par QR code
    bien = db.query(Bien).filter(Bien.qr_code == qr_data).first()
    if not bien:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Aucun bien trouvé avec le QR code: {qr_data}"
        )
    
    return {
        "found": True,
        "bien": {
            "id_bien": bien.id_bien,
            "qr_code": bien.qr_code,
            "type_bien": bien.type_bien,
            "marque": getattr(bien, 'marque', None),
            "modele": getattr(bien, 'modele', None),
            "etat": bien.etat,
            "localisation": bien.localisation
        }
    }

@router.get("/{bien_id}/print")
async def print_qr_code_label(
    bien_id: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """
    Génère une étiquette QR code imprimable avec informations du bien
    
    Args:
        bien_id: ID du bien
        
    Returns:
        dict: Données pour génération d'étiquette
    """
    # Récupération du bien
    bien = db.query(Bien).filter(Bien.id_bien == bien_id).first()
    if not bien:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Bien {bien_id} non trouvé"
        )
    
    # Génération du QR code
    qr_service = QRCodeService()
    qr_image = qr_service.generate_qr_code(data=bien.qr_code, bien_id=bien_id)
    qr_base64 = qr_service.qr_code_to_base64(qr_image)
    
    return {
        "bien_id": bien.id_bien,
        "qr_code": bien.qr_code,
        "qr_image": qr_base64,
        "label_data": {
            "type": bien.type_bien,
            "marque": getattr(bien, 'marque', getattr(bien, 'fabricant', 'N/A')),
            "modele": getattr(bien, 'modele', 'N/A'),
            "date_acquisition": bien.date_acquisition.isoformat() if bien.date_acquisition else None,
            "localisation": bien.localisation or 'N/A'
        }
    }