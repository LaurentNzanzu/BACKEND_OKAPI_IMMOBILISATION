from sqlalchemy import create_engine, text, inspect

engine = create_engine("postgresql://postgres:4545@localhost:5432/gestion_immobilisationsDB")

with engine.connect() as conn:
    try:
        r = conn.execute(text("SELECT version_num FROM alembic_version")).fetchone()
        print("alembic_version:", r)
    except Exception as e:
        print("alembic_version error:", e)

    enums = conn.execute(
        text(
            """
            SELECT typname, enumlabel
            FROM pg_enum e
            JOIN pg_type t ON e.enumtypid = t.oid
            WHERE typname IN ('etatbien', 'statutbesoin', 'statutpanne', 'statut_fourniture', 'typedecisionenum', 'typecompatible')
            ORDER BY typname, enumsortorder
            """
        )
    ).fetchall()
    print("enums:")
    for row in enums:
        print(" ", row)

    insp = inspect(engine)
    if "decisions_ia" in insp.get_table_names():
        cols = {c["name"]: str(c["type"]) for c in insp.get_columns("decisions_ia")}
        print("decisions_ia cols:", cols)
    if "pieces_rechange" in insp.get_table_names():
        cols = {c["name"]: str(c["type"]) for c in insp.get_columns("pieces_rechange")}
        print("pieces_rechange cols:", cols)

    cols = [c["name"] for c in insp.get_columns("maintenances")]
    print("maintenances cols:", cols)
    print("fournitures_pieces exists:", "fournitures_pieces" in insp.get_table_names())
