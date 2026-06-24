# backend/app/api/endpoints/rapports.py
from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime, date

from ...core.database import get_db
from ...core.security import get_current_user
from ...models.utilisateur import Utilisateur
from ...services.rapport_service import RapportService
from ...utils.pdf_generator import generer_pdf_rapport, generer_pdf_rapport_avec_sections
from ...utils.excel_export import generer_excel_rapport, generer_csv_rapport, generer_excel_rapport_multifeuilles

router = APIRouter(prefix="/rapports", tags=["Rapports"])


def check_rapport_permission(user: Utilisateur, rapport_type: str) -> bool:
    """
    Vérifie les permissions pour les rapports.
    - Rapports financiers: ADMIN, DG, COMPTABLE
    - Rapports techniques: ADMIN, DG, COMPTABLE, TECHNICIEN
    """
    if not user:
        return False
    
    role = user.role.nom.upper() if user.role else "USER"
    
    if role == "ADMIN":
        return True
    
    if rapport_type == "financier":
        return role in ["DG", "COMPTABLE"]
    
    if rapport_type == "technique":
        return role in ["DG", "COMPTABLE", "TECHNICIEN"]
    
    if rapport_type == "amortissements":
        return role in ["DG", "COMPTABLE"]
    
    return False


@router.get("/financier")
async def get_rapport_financier(
    date_debut: date = Query(..., description="Date de début (YYYY-MM-DD)"),
    date_fin: date = Query(..., description="Date de fin (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """Retourne le rapport financier au format JSON pour affichage web"""
    if not check_rapport_permission(current_user, "financier"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permissions insuffisantes pour consulter le rapport financier"
        )
    
    if date_debut > date_fin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La date de début doit être antérieure à la date de fin"
        )
    
    service = RapportService(db)
    result = service.get_rapport_financier(date_debut, date_fin)
    return result


@router.get("/technique")
async def get_rapport_technique(
    date_debut: date = Query(..., description="Date de début (YYYY-MM-DD)"),
    date_fin: date = Query(..., description="Date de fin (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """Retourne le rapport technique au format JSON pour affichage web"""
    if not check_rapport_permission(current_user, "technique"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permissions insuffisantes pour consulter le rapport technique"
        )
    
    if date_debut > date_fin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La date de début doit être antérieure à la date de fin"
        )
    
    service = RapportService(db)
    result = service.get_rapport_technique(date_debut, date_fin)
    return result


@router.get("/amortissements")
async def get_rapport_amortissements(
    annee: int = Query(..., description="Année (ex: 2024)"),
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """Retourne le rapport des amortissements pour une année"""
    if not check_rapport_permission(current_user, "amortissements"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permissions insuffisantes pour consulter le rapport des amortissements"
        )
    
    service = RapportService(db)
    result = service.get_rapport_amortissements(annee)
    return result


@router.get("/export")
async def exporter_rapport(
    type_rapport: str = Query(..., regex="^(financier|technique|amortissements)$"),
    format: str = Query(..., regex="^(pdf|excel|csv)$"),
    date_debut: Optional[date] = Query(None, description="Date début (pour financier/technique)"),
    date_fin: Optional[date] = Query(None, description="Date fin (pour financier/technique)"),
    annee: Optional[int] = Query(None, description="Année (pour amortissements)"),
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """Exporte un rapport au format PDF, Excel ou CSV"""
    
    # Validation des permissions
    if not check_rapport_permission(current_user, type_rapport):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permissions insuffisantes pour exporter le rapport {type_rapport}"
        )
    
    service = RapportService(db)
    
    # Définition du nom du fichier
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Génération des données selon le type
    if type_rapport == "financier":
        if not date_debut or not date_fin:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="date_debut et date_fin requis pour le rapport financier"
            )
        if date_debut > date_fin:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="La date de début doit être antérieure à la date de fin"
            )
        
        data = service.get_rapport_financier(date_debut, date_fin)
        
        # Préparation des données pour l'export
        titre = f"Rapport Financier - {date_debut.strftime('%d/%m/%Y')} au {date_fin.strftime('%d/%m/%Y')}"
        
        # Section synthèse
        synthese_data = [
            ["Valeur acquisition totale", f"{data['synthese']['valeur_acquisition_totale']:,.2f} FCFA"],
            ["Coût des pannes", f"{data['synthese']['cout_pannes_total']:,.2f} FCFA"],
            ["Coût des maintenances", f"{data['synthese']['cout_maintenances_total']:,.2f} FCFA"],
            ["Dotation aux amortissements", f"{data['synthese']['dotation_amortissements_total']:,.2f} FCFA"],
            ["Total des dépenses", f"{data['synthese']['total_depenses']:,.2f} FCFA"]
        ]
        
        # Section biens
        biens_data = [
            [b['id'], b['qr_code'], b['date_acquisition'], f"{b['prix_acquisition']:,.2f}", b['etat'], b['localisation'], b['type']]
            for b in data['details_biens']
        ]
        
        # Section pannes
        pannes_data = [
            [p['id'], p['bien_id'], p['date_declaration'], p['type'], p['priorite'], p['statut'], f"{p['cout']:,.2f}"]
            for p in data['details_pannes']
        ]
        
        if format == "pdf":
            sections = [
                {"titre": "1. Synthèse financière", "en_tetes": ["Indicateur", "Valeur"], "donnees": synthese_data},
                {"titre": f"2. Liste des biens ({len(biens_data)} biens)", "en_tetes": ["ID", "QR Code", "Date acquisition", "Prix", "État", "Localisation", "Type"], "donnees": biens_data},
                {"titre": f"3. Pannes sur la période ({len(pannes_data)} pannes)", "en_tetes": ["ID", "Bien ID", "Date", "Type", "Priorité", "Statut", "Coût"], "donnees": pannes_data}
            ]
            content = generer_pdf_rapport_avec_sections(titre, sections, format_paysage=True)
            media_type = "application/pdf"
            filename = f"rapport_financier_{timestamp}.pdf"
        
        elif format == "excel":
            feuilles = [
                {"nom": "Synthèse", "en_tetes": ["Indicateur", "Valeur"], "donnees": synthese_data},
                {"nom": "Biens", "en_tetes": ["ID", "QR Code", "Date acquisition", "Prix (FCFA)", "État", "Localisation", "Type"], "donnees": biens_data},
                {"nom": "Pannes", "en_tetes": ["ID", "Bien ID", "Date", "Type", "Priorité", "Statut", "Coût (FCFA)"], "donnees": pannes_data},
                {"nom": "Maintenances", "en_tetes": ["ID", "Bien ID", "Type", "Statut", "Date planifiée", "Date début", "Date fin", "Coût (FCFA)", "Description"], "donnees": [
                    [m['id'], m['bien_id'], m['type'], m['statut'], m['date_planifiee'], m['date_debut'], m['date_fin'], f"{m['cout']:,.2f}", m['description']]
                    for m in data['details_maintenances']
                ]}
            ]
            content = generer_excel_rapport_multifeuilles(titre, feuilles)
            media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            filename = f"rapport_financier_{timestamp}.xlsx"
        
        else:  # csv
            content = generer_csv_rapport(
                ["Indicateur", "Valeur"],
                synthese_data
            )
            media_type = "text/csv; charset=utf-8"
            filename = f"rapport_financier_{timestamp}.csv"
    
    elif type_rapport == "technique":
        if not date_debut or not date_fin:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="date_debut et date_fin requis pour le rapport technique"
            )
        if date_debut > date_fin:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="La date de début doit être antérieure à la date de fin"
            )
        
        data = service.get_rapport_technique(date_debut, date_fin)
        
        titre = f"Rapport Technique - {date_debut.strftime('%d/%m/%Y')} au {date_fin.strftime('%d/%m/%Y')}"
        
        # Section synthèse
        synthese_data = [
            ["Total biens", data['synthese']['total_biens']],
            ["Biens actifs", data['synthese']['biens_actifs']],
            ["Biens réformés", data['synthese']['biens_reformes']],
            ["Taux d'occupation", f"{data['synthese']['taux_occupation']}%"],
            ["Total pannes", data['synthese']['total_pannes']],
            ["Total maintenances", data['synthese']['total_maintenances']],
            ["Taux résolution maintenances", f"{data['synthese']['taux_resolution_maintenances']}%"]
        ]
        
        # Répartition états
        etats_data = [[k, v] for k, v in data['repartition_etats'].items()]
        
        # Pannes par type
        pannes_type_data = [[k, v] for k, v in data['pannes_par_type'].items()]
        
        # Top biens en panne
        top_biens_data = [[b['bien_id'], b['qr_code'], b['nb_pannes']] for b in data['top_biens_pannes']]
        
        if format == "pdf":
            sections = [
                {"titre": "1. Synthèse technique", "en_tetes": ["Indicateur", "Valeur"], "donnees": synthese_data},
                {"titre": "2. Répartition par état", "en_tetes": ["État", "Nombre"], "donnees": etats_data},
                {"titre": "3. Pannes par type", "en_tetes": ["Type de panne", "Nombre"], "donnees": pannes_type_data},
                {"titre": "4. Top 5 biens les plus en panne", "en_tetes": ["Bien ID", "QR Code", "Nombre de pannes"], "donnees": top_biens_data}
            ]
            content = generer_pdf_rapport_avec_sections(titre, sections, format_paysage=True)
            media_type = "application/pdf"
            filename = f"rapport_technique_{timestamp}.pdf"
        
        elif format == "excel":
            feuilles = [
                {"nom": "Synthèse", "en_tetes": ["Indicateur", "Valeur"], "donnees": synthese_data},
                {"nom": "États des biens", "en_tetes": ["État", "Nombre"], "donnees": etats_data},
                {"nom": "Pannes par type", "en_tetes": ["Type", "Nombre"], "donnees": pannes_type_data},
                {"nom": "Top biens en panne", "en_tetes": ["Bien ID", "QR Code", "Nb pannes"], "donnees": top_biens_data},
                {"nom": "Détail des pannes", "en_tetes": ["ID", "Bien ID", "Date", "Type", "Priorité", "Statut", "Durée (jours)", "Coût"], "donnees": [
                    [p['id'], p['bien_id'], p['date_declaration'], p['type'], p['priorite'], p['statut'], p.get('duree_resolution', 0), f"{p['cout']:,.2f}"]
                    for p in data['details_pannes']
                ]}
            ]
            content = generer_excel_rapport_multifeuilles(titre, feuilles)
            media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            filename = f"rapport_technique_{timestamp}.xlsx"
        
        else:  # csv
            content = generer_csv_rapport(
                ["Indicateur", "Valeur"],
                synthese_data
            )
            media_type = "text/csv; charset=utf-8"
            filename = f"rapport_technique_{timestamp}.csv"
    
    elif type_rapport == "amortissements":
        if not annee:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="annee requis pour le rapport des amortissements"
            )
        
        data = service.get_rapport_amortissements(annee)
        
        titre = f"Rapport des Amortissements - Année {annee}"
        
        amortissements_data = [
            [
                a['bien_id'],
                a['qr_code'],
                a['type_bien'],
                a['methode'],
                f"{a['valeur_origine']:,.2f}",
                f"{a['valeur_residuelle']:,.2f}",
                f"{a['annuite']:,.2f}"
            ]
            for a in data['details']
        ]
        
        # Ligne de total
        total_data = [["TOTAL", "", "", "", "", "", f"{data['total_dotations']:,.2f} FCFA"]]
        
        if format == "pdf":
            sections = [
                {"titre": "Synthèse", "en_tetes": ["Indicateur", "Valeur"], "donnees": [
                    ["Année", str(annee)],
                    ["Total des dotations", f"{data['total_dotations']:,.2f} FCFA"],
                    ["Nombre de biens amortis", str(data['nombre_biens_amortis'])]
                ]},
                {"titre": f"Détail des amortissements ({len(amortissements_data)} biens)", 
                 "en_tetes": ["Bien ID", "QR Code", "Type", "Méthode", "Valeur origine", "Valeur résiduelle", "Annuite (FCFA)"], 
                 "donnees": amortissements_data + total_data}
            ]
            content = generer_pdf_rapport_avec_sections(titre, sections, format_paysage=True)
            media_type = "application/pdf"
            filename = f"rapport_amortissements_{annee}_{timestamp}.pdf"
        
        elif format == "excel":
            feuilles = [
                {"nom": "Synthèse", "en_tetes": ["Indicateur", "Valeur"], "donnees": [
                    ["Année", str(annee)],
                    ["Total des dotations", f"{data['total_dotations']:,.2f} FCFA"],
                    ["Nombre de biens amortis", str(data['nombre_biens_amortis'])]
                ]},
                {"nom": "Détail des amortissements", 
                 "en_tetes": ["Bien ID", "QR Code", "Type", "Méthode", "Valeur origine (FCFA)", "Valeur résiduelle (FCFA)", "Annuite (FCFA)"], 
                 "donnees": amortissements_data + total_data}
            ]
            content = generer_excel_rapport_multifeuilles(titre, feuilles)
            media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            filename = f"rapport_amortissements_{annee}_{timestamp}.xlsx"
        
        else:  # csv
            content = generer_csv_rapport(
                ["Bien ID", "QR Code", "Type", "Méthode", "Valeur origine", "Valeur residuelle", "Annuite"],
                amortissements_data
            )
            media_type = "text/csv; charset=utf-8"
            filename = f"rapport_amortissements_{annee}_{timestamp}.csv"
    
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Type de rapport non supporté: {type_rapport}"
        )
    
    # Retourner le fichier
    return StreamingResponse(
        content=iter([content]) if isinstance(content, bytes) else content,
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


# ============================================================
# NOUVEAUX ENDPOINTS OHADA/SYSCOHADA
# ============================================================

@router.get("/financier-ohada")
async def get_rapport_financier_ohada(
    date_debut: date = Query(..., description="Date de début (YYYY-MM-DD)"),
    date_fin: date = Query(..., description="Date de fin (YYYY-MM-DD)"),
    exercice: Optional[int] = Query(None, description="Exercice comptable (ex: 2026)"),
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """Retourne le rapport financier complet conforme aux normes OHADA/SYSCOHADA"""
    if not check_rapport_permission(current_user, "financier"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permissions insuffisantes pour consulter le rapport financier"
        )
    
    if date_debut > date_fin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La date de début doit être antérieure à la date de fin"
        )
    
    # Si exercice non fourni, utiliser l'année de la date de fin
    if not exercice:
        exercice = date_fin.year
    
    service = RapportService(db)
    result = service.get_rapport_financier_ohada(date_debut, date_fin, exercice)
    return result


@router.get("/export/ohada")
async def exporter_rapport_ohada(
    format: str = Query(..., regex="^(pdf|excel)$"),
    date_debut: date = Query(..., description="Date de début (YYYY-MM-DD)"),
    date_fin: date = Query(..., description="Date de fin (YYYY-MM-DD)"),
    exercice: Optional[int] = Query(None, description="Exercice comptable"),
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """Exporte le rapport financier OHADA au format PDF ou Excel"""
    if not check_rapport_permission(current_user, "financier"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permissions insuffisantes pour exporter le rapport financier"
        )
    
    if date_debut > date_fin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La date de début doit être antérieure à la date de fin"
        )
    
    if not exercice:
        exercice = date_fin.year
    
    service = RapportService(db)
    data = service.get_rapport_financier_ohada(date_debut, date_fin, exercice)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    titre = f"Rapport Financier SYSCOHADA - {date_debut.strftime('%d/%m/%Y')} au {date_fin.strftime('%d/%m/%Y')}"
    
    if format == "pdf":
        # ✅ Utiliser la fonction existante generer_pdf_rapport_avec_sections
        sections = _prepare_pdf_sections_ohada(data, exercice)
        content = generer_pdf_rapport_avec_sections(titre, sections, format_paysage=True)
        media_type = "application/pdf"
        filename = f"rapport_financier_ohada_{timestamp}.pdf"
        
    else:  # excel
        # ✅ Utiliser la fonction existante generer_excel_rapport_multifeuilles
        feuilles = _prepare_excel_sheets_ohada(data, exercice)
        content = generer_excel_rapport_multifeuilles(titre, feuilles)
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        filename = f"rapport_financier_ohada_{timestamp}.xlsx"
    
    return StreamingResponse(
        iter([content]) if isinstance(content, bytes) else content,
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


# ============================================================
# FONCTIONS AIDES POUR L'EXPORT OHADA
# ============================================================

def _prepare_pdf_sections_ohada(data: dict, exercice: int) -> list:
    """Prépare les sections pour le PDF OHADA"""
    sections = []
    
    # Section 1: Synthèse du patrimoine
    patrimoine_data = [
        ["Valeur totale d'acquisition", f"{data['patrimoine']['valeur_totale_acquisition']:,.2f} FCFA"],
        ["Total des biens", str(data['patrimoine']['total_biens'])],
    ]
    sections.append({
        "titre": "A. Synthèse du patrimoine immobilier",
        "en_tetes": ["Indicateur", "Valeur"],
        "donnees": patrimoine_data
    })
    
    # Section 2: Amortissements
    amort_data = [
        ["Dotations de l'exercice", f"{data['amortissements']['dotations_exercice']:,.2f} FCFA"],
        ["Cumul des amortissements", f"{data['amortissements']['cumul_total_amortissements']:,.2f} FCFA"],
        ["Valeur nette comptable (VNC)", f"{data['amortissements']['valeur_nette_comptable_totale']:,.2f} FCFA"],
    ]
    sections.append({
        "titre": f"B. Amortissements - Exercice {exercice} (Note 3C)",
        "en_tetes": ["Indicateur", "Valeur"],
        "donnees": amort_data
    })
    
    # Section 3: Charges
    charges_data = [
        ["Coût des pannes", f"{data['charges_cycle_vie']['pannes']['cout_total']:,.2f} FCFA"],
        ["Nombre de pannes", str(data['charges_cycle_vie']['pannes']['total'])],
        ["Coût des maintenances", f"{data['charges_cycle_vie']['maintenances']['cout_total']:,.2f} FCFA"],
        ["Nombre de maintenances", str(data['charges_cycle_vie']['maintenances']['total'])],
        ["Total des charges", f"{data['charges_cycle_vie']['total_charges']:,.2f} FCFA"],
    ]
    sections.append({
        "titre": "C. Charges de maintenance et réparations",
        "en_tetes": ["Indicateur", "Valeur"],
        "donnees": charges_data
    })
    
    # Section 4: Cessions
    cessions_data = [
        ["Total des cessions", str(data['cessions_mouvements']['total_cessions'])],
        ["Total prix de vente", f"{data['cessions_mouvements']['total_prix_vente']:,.2f} FCFA"],
        ["Plus-values", f"{data['cessions_mouvements']['plus_values']:,.2f} FCFA"],
        ["Moins-values", f"{data['cessions_mouvements']['moins_values']:,.2f} FCFA"],
        ["Biens mis au rebut", str(data['cessions_mouvements']['total_rebuts'])],
    ]
    sections.append({
        "titre": "D. Cessions et mouvements (Note 3D)",
        "en_tetes": ["Indicateur", "Valeur"],
        "donnees": cessions_data
    })
    
    return sections


def _prepare_excel_sheets_ohada(data: dict, exercice: int) -> list:
    """Prépare les feuilles pour l'Excel OHADA"""
    feuilles = []
    
    # Feuille 1: Synthèse
    feuilles.append({
        "nom": "Synthèse",
        "en_tetes": ["Indicateur", "Valeur"],
        "donnees": [
            ["Valeur totale d'acquisition", f"{data['patrimoine']['valeur_totale_acquisition']:,.2f}"],
            ["Total des biens", str(data['patrimoine']['total_biens'])],
            ["Dotations exercice", f"{data['amortissements']['dotations_exercice']:,.2f}"],
            ["Cumul amortissements", f"{data['amortissements']['cumul_total_amortissements']:,.2f}"],
            ["VNC totale", f"{data['amortissements']['valeur_nette_comptable_totale']:,.2f}"],
            ["Coût pannes", f"{data['charges_cycle_vie']['pannes']['cout_total']:,.2f}"],
            ["Coût maintenances", f"{data['charges_cycle_vie']['maintenances']['cout_total']:,.2f}"],
            ["Total charges", f"{data['charges_cycle_vie']['total_charges']:,.2f}"],
            ["Plus-values", f"{data['cessions_mouvements']['plus_values']:,.2f}"],
            ["Moins-values", f"{data['cessions_mouvements']['moins_values']:,.2f}"],
        ]
    })
    
    # Feuille 2: Répartition par type
    repartition_data = [
        [t, str(v['count']), f"{v['valeur']:,.2f}"]
        for t, v in data['patrimoine']['repartition_par_type'].items()
    ]
    feuilles.append({
        "nom": "Répartition par type",
        "en_tetes": ["Type", "Nombre", "Valeur (FCFA)"],
        "donnees": repartition_data
    })
    
    # Feuille 3: Détail des amortissements
    amort_details = []
    for a in data['tableau_amortissements']['details'][:50]:  # Limite à 50 pour l'Excel
        amort_details.append([
            a['designation'],
            a['type_bien'],
            a['methode'],
            f"{a['valeur_origine']:,.2f}",
            f"{a['annuite_exercice']:,.2f}",
            f"{a['cumul_amortissements']:,.2f}",
            f"{a['valeur_nette_comptable']:,.2f}"
        ])
    
    # Ajouter le total
    total_row = [
        "TOTAL",
        "",
        "",
        f"{data['tableau_amortissements']['total_valeur_origine']:,.2f}",
        f"{data['tableau_amortissements']['total_annuite_exercice']:,.2f}",
        f"{data['tableau_amortissements']['total_cumul_amortissements']:,.2f}",
        f"{data['tableau_amortissements']['total_valeur_nette_comptable']:,.2f}"
    ]
    amort_details.append(total_row)
    
    feuilles.append({
        "nom": "Détail amortissements",
        "en_tetes": ["Bien", "Type", "Méthode", "Valeur brute", "Dotation N", "Cumul", "VNC"],
        "donnees": amort_details
    })
    
    # Feuille 4: Cessions
    cessions_data = []
    for c in data['cessions_mouvements']['details_cessions'][:50]:
        cessions_data.append([
            c['designation'],
            c['date_cession'],
            f"{c['valeur_acquisition']:,.2f}",
            f"{c['cumul_amortissement']:,.2f}",
            f"{c['vnc']:,.2f}",
            f"{c['prix_vente']:,.2f}",
            c['type_cession'],
            c['acheteur'],
            f"{c['resultat']:,.2f}"
        ])
    
    feuilles.append({
        "nom": "Cessions",
        "en_tetes": ["Bien", "Date", "Valeur acquisition", "Cumul amort", "VNC", "Prix vente", "Type", "Acheteur", "Résultat"],
        "donnees": cessions_data
    })
    
    return feuilles