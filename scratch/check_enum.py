# scratch/check_enum.py
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import engine
from sqlalchemy import text

with engine.connect() as conn:
    res = conn.execute(text("SELECT enumlabel FROM pg_enum JOIN pg_type ON pg_enum.enumtypid = pg_type.oid WHERE pg_type.typname = 'typepiecejustificative'"))
    print("Labels typepiecejustificative :", [r[0] for r in res.fetchall()])
    
    # Let's also check other tables or schemas if needed
