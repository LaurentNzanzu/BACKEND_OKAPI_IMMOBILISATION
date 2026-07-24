# -*- coding: utf-8 -*-
import os
import sys
sys.path.append(os.path.abspath('.'))

from app.core.database import SessionLocal
from app.models.discussion_concertation import DiscussionConcertation

db = SessionLocal()
try:
    discussions = db.query(DiscussionConcertation).filter(DiscussionConcertation.id_bien == 1).all()
    for d in discussions:
        print(f"Update discussion {d.id} de {d.type_validation} a REBUT")
        d.type_validation = 'REBUT'
    db.commit()
    print("Mise a jour terminee.")
except Exception as e:
    print(e)
finally:
    db.close()
