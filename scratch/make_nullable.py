# scratch/make_nullable.py
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import engine
from sqlalchemy import text

with engine.begin() as conn:
    try:
        conn.execute(text("ALTER TABLE ecritures_comptables ALTER COLUMN id_bien DROP NOT NULL"))
        print("id_bien column is now nullable in ecritures_comptables.")
    except Exception as e:
        print("Error or already nullable:", e)
