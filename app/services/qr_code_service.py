# backend/app/services/qr_code_service.py
import qrcode
from io import BytesIO
import base64
from typing import Optional
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

class QRCodeService:
    """Service de génération et lecture de QR codes"""
    
    @staticmethod
    def generate_qr_code(data: str, bien_id: int = None) -> bytes:
        """
        Génère un QR code en format PNG
        
        Args:
            data: Contenu du QR code (généralement le qr_code du bien)
            bien_id: ID du bien (optionnel, pour log)
            
        Returns:
            bytes: Image PNG du QR code
        """
        try:
            # Création du QR code
            qr = qrcode.QRCode(
                version=1,  # Taille automatique
                error_correction=qrcode.constants.ERROR_CORRECT_M,
                box_size=10,
                border=4,
            )
            qr.add_data(data)
            qr.make(fit=True)
            
            # Création de l'image
            img = qr.make_image(fill_color="black", back_color="white")
            
            # Conversion en bytes
            buffer = BytesIO()
            img.save(buffer, format="PNG")
            buffer.seek(0)
            
            logger.info(f"QR code généré pour le bien ID {bien_id} - Données: {data}")
            return buffer.getvalue()
            
        except Exception as e:
            logger.error(f"Erreur génération QR code: {e}")
            raise

    @staticmethod
    def qr_code_to_base64(qr_bytes: bytes) -> str:
        """
        Convertit un QR code en base64 pour affichage frontend
        
        Args:
            qr_bytes: Image PNG en bytes
            
        Returns:
            str: QR code en base64 (data URI)
        """
        base64_str = base64.b64encode(qr_bytes).decode('utf-8')
        return f"data:image/png;base64,{base64_str}"

    @staticmethod
    def decode_qr_code(image_path: str) -> Optional[str]:
        """
        Décode un QR code à partir d'une image
        Nécessite: pip install opencv-python pyzbar
        
        Args:
            image_path: Chemin vers l'image du QR code
            
        Returns:
            str: Contenu du QR code ou None
        """
        try:
            import cv2
            from pyzbar import pyzbar
            
            # Lecture de l'image
            img = cv2.imread(image_path)
            
            # Détection des QR codes
            decoded_objects = pyzbar.decode(img)
            
            for obj in decoded_objects:
                return obj.data.decode("utf-8")
            
            return None
            
        except Exception as e:
            logger.error(f"Erreur décodage QR code: {e}")
            return None

    @staticmethod
    def generate_qr_file_path(qr_code: str, base_dir: str = "backend/app/qr_codes") -> Path:
        """
        Génère le chemin de stockage du fichier QR code
        
        Args:
            qr_code: Code QR du bien
            base_dir: Répertoire de base
            
        Returns:
            Path: Chemin complet du fichier
        """
        path = Path(base_dir)
        path.mkdir(parents=True, exist_ok=True)
        return path / f"{qr_code}.png"