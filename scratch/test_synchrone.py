import os
import sys
from datetime import datetime
sys.path.append(os.path.dirname(os.path.abspath('.')))

from app.core.database import SessionLocal
from app.services.panne_service import PanneService
from app.schemas.panne import PanneCreate
from app.models.bien import Bien
from app.models.panne import TypePanneEnum, PrioritePanneEnum

db = SessionLocal()
try:
    bien = db.query(Bien).first()
    if not bien:
        print('Aucun bien trouvé')
        sys.exit(1)
        
    print(f'Test avec le bien ID: {bien.id_bien}')
    
    from app.models.discussion_concertation import DiscussionConcertation
    discussions = db.query(DiscussionConcertation).filter(DiscussionConcertation.id_bien == bien.id_bien).all()
    print(f'Discussions existantes: {len(discussions)}')

    panne_service = PanneService(db)
    
    from app.models.utilisateur import Utilisateur
    from app.models.role import Role
    tech = db.query(Utilisateur).join(Role).filter(Role.nom == 'TECHNICIEN').first()
    tech_id = tech.id if tech else 1

    data = PanneCreate(
        id_bien=bien.id_bien,
        type_panne=TypePanneEnum.MECANIQUE,
        priorite=PrioritePanneEnum.HAUTE,
        diagnostic='Le moteur est irrécupérable et hors d\'usage.'
    )
    
    panne = panne_service.declarer_panne(data, id_technicien=tech_id)
    print(f'Panne déclarée avec ID: {panne.id_panne}, Statut: {panne.statut}')
    
    discussions = db.query(DiscussionConcertation).filter(DiscussionConcertation.id_bien == bien.id_bien).all()
    print(f'Discussions après: {len(discussions)}')
except Exception as e:
    import traceback
    traceback.print_exc()
finally:
    db.close()
