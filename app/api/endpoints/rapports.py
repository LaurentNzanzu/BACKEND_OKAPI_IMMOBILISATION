# backend/app/api/endpoints/rapports.py
from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from typing import Optional
from datetime import datetime, date
import logging

from ...core.database import get_db
from ...core.security import get_current_user
from ...models.utilisateur import Utilisateur
from ...models.projection_investissement import ProjectionInvestissement
from ...services.rapport_service import RapportService
from ...services.audit_service import AuditService
from ...services.notification_service import NotificationService
from ...utils.pdf_generator import generer_pdf_rapport, generer_pdf_rapport_avec_sections
from ...utils.excel_export import generer_excel_rapport, generer_csv_rapport, generer_excel_rapport_multifeuilles

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/rapports", tags=["Rapports"])


# ============================================================
# FONCTION ASYNCHRONE POUR LA GÉNÉRATION DE RAPPORT (BACKGROUND TASK)
# ============================================================

def _generer_rapport_async(
    exercice: int,
    format_export: str,
    user_email: str,
    user_nom: str
):
    """
    Génère un rapport en arrière-plan et notifie l'utilisateur par email.
    Crée sa propre session BDD pour isolation.
    """
    from ...core.database import SessionLocal
    from ...services.notification_service import NotificationService
    
    db = SessionLocal()
    try:
        service = RapportService(db)
        
        if format_export == "pdf":
            # Génération du PDF
            resultat = service.generer_tableau8_ohada(exercice)
            chemin_fichier = f"/tmp/tableau8_{exercice}.pdf"
            # ... génération du fichier ...
            
        elif format_export == "excel":
            resultat = service.generer_tableau8_ohada(exercice)
            chemin_fichier = f"/tmp/tableau8_{exercice}.xlsx"
            # ... génération du fichier ...
        else:
            raise ValueError(f"Format non supporté: {format_export}")
        
        # Envoyer le fichier par email
        notif = NotificationService(db)
        notif.envoyer_rapport_par_email(
            destinataire=user_email,
            chemin_fichier=chemin_fichier,
            sujet=f"Tableau 8 OHADA - Exercice {exercice}",
            corps=f"Bonjour {user_nom},\n\nLe rapport Tableau 8 pour l'exercice {exercice} est disponible en pièce jointe.\n\nCordialement,\nL'équipe OKAPI"
        )
        
        logger.info(f"✅ Rapport Tableau 8 {exercice} envoyé à {user_email}")
        
    except Exception as e:
        logger.error(f"❌ Erreur génération rapport {exercice}: {e}")
        try:
            notif = NotificationService(db)
            notif.envoyer_alert_admin(
                sujet=f"Erreur génération Tableau 8 OHADA - Exercice {exercice}",
                message=f"L'utilisateur {user_nom} a demandé un rapport qui a échoué: {str(e)}"
            )
        except:
            pass
    finally:
        db.close()


# ============================================================
# FONCTIONS UTILITAIRES
# ============================================================

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


# ============================================================
# ENDPOINTS DE LECTURE (RAPIDES)
# ============================================================

@router.get("/financier")
async def get_rapport_financier(
    date_debut: date = Query(..., description="Date de début (YYYY-MM-DD)"),
    date_fin: date = Query(..., description="Date de fin (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """Retourne le rapport financier au format JSON pour affichage web."""
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
    """Retourne le rapport technique au format JSON pour affichage web."""
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
    """Retourne le rapport des amortissements pour une année."""
    if not check_rapport_permission(current_user, "amortissements"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permissions insuffisantes pour consulter le rapport des amortissements"
        )
    
    service = RapportService(db)
    result = service.get_rapport_amortissements(annee)
    return result


# ============================================================
# EXPORT DES RAPPORTS
# ============================================================

@router.get("/export")
async def exporter_rapport(
    type_rapport: str = Query(..., pattern="^(financier|technique|amortissements)$"),
    format: str = Query(..., pattern="^(pdf|excel|csv)$"),
    date_debut: Optional[date] = Query(None, description="Date début (pour financier/technique)"),
    date_fin: Optional[date] = Query(None, description="Date fin (pour financier/technique)"),
    annee: Optional[int] = Query(None, description="Année (pour amortissements)"),
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """Exporte un rapport au format PDF, Excel ou CSV."""
    
    if not check_rapport_permission(current_user, type_rapport):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permissions insuffisantes pour exporter le rapport {type_rapport}"
        )
    
    service = RapportService(db)
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
        titre = f"Rapport Financier - {date_debut.strftime('%d/%m/%Y')} au {date_fin.strftime('%d/%m/%Y')}"
        
        synthese_data = [
            ["Valeur acquisition totale", f"{data['synthese']['valeur_acquisition_totale']:,.2f} USD"],
            ["Coût des pannes", f"{data['synthese']['cout_pannes_total']:,.2f} USD"],
            ["Coût des maintenances", f"{data['synthese']['cout_maintenances_total']:,.2f} USD"],
            ["Dotation aux amortissements", f"{data['synthese']['dotation_amortissements_total']:,.2f} USD"],
            ["Total des dépenses", f"{data['synthese']['total_depenses']:,.2f} USD"]
        ]
        
        biens_data = [
            [b['id'], b['qr_code'], b['date_acquisition'], f"{b['prix_acquisition']:,.2f}", b['etat'], b['localisation'], b['type']]
            for b in data['details_biens']
        ]
        
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
                {"nom": "Biens", "en_tetes": ["ID", "QR Code", "Date acquisition", "Prix (USD)", "État", "Localisation", "Type"], "donnees": biens_data},
                {"nom": "Pannes", "en_tetes": ["ID", "Bien ID", "Date", "Type", "Priorité", "Statut", "Coût (USD)"], "donnees": pannes_data},
                {"nom": "Maintenances", "en_tetes": ["ID", "Bien ID", "Type", "Statut", "Date planifiée", "Date début", "Date fin", "Coût (USD)", "Description"], "donnees": [
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
        
        synthese_data = [
            ["Total biens", data['synthese']['total_biens']],
            ["Biens actifs", data['synthese']['biens_actifs']],
            ["Biens réformés", data['synthese']['biens_reformes']],
            ["Taux d'occupation", f"{data['synthese']['taux_occupation']}%"],
            ["Total pannes", data['synthese']['total_pannes']],
            ["Total maintenances", data['synthese']['total_maintenances']],
            ["Taux résolution maintenances", f"{data['synthese']['taux_resolution_maintenances']}%"]
        ]
        
        etats_data = [[k, v] for k, v in data['repartition_etats'].items()]
        pannes_type_data = [[k, v] for k, v in data['pannes_par_type'].items()]
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
        
        total_data = [["TOTAL", "", "", "", "", "", f"{data['total_dotations']:,.2f} USD"]]
        
        if format == "pdf":
            sections = [
                {"titre": "Synthèse", "en_tetes": ["Indicateur", "Valeur"], "donnees": [
                    ["Année", str(annee)],
                    ["Total des dotations", f"{data['total_dotations']:,.2f} USD"],
                    ["Nombre de biens amortis", str(data['nombre_biens_amortis'])]
                ]},
                {"titre": f"Détail des amortissements ({len(amortissements_data)} biens)", 
                 "en_tetes": ["Bien ID", "QR Code", "Type", "Méthode", "Valeur origine", "Valeur résiduelle", "Annuite (USD)"], 
                 "donnees": amortissements_data + total_data}
            ]
            content = generer_pdf_rapport_avec_sections(titre, sections, format_paysage=True)
            media_type = "application/pdf"
            filename = f"rapport_amortissements_{annee}_{timestamp}.pdf"
        
        elif format == "excel":
            feuilles = [
                {"nom": "Synthèse", "en_tetes": ["Indicateur", "Valeur"], "donnees": [
                    ["Année", str(annee)],
                    ["Total des dotations", f"{data['total_dotations']:,.2f} USD"],
                    ["Nombre de biens amortis", str(data['nombre_biens_amortis'])]
                ]},
                {"nom": "Détail des amortissements", 
                 "en_tetes": ["Bien ID", "QR Code", "Type", "Méthode", "Valeur origine (USD)", "Valeur résiduelle (USD)", "Annuite (USD)"], 
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
    """Retourne le rapport financier complet conforme aux normes OHADA/SYSCOHADA."""
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
    
    if not exercice:
        exercice = date_fin.year
    
    service = RapportService(db)
    result = service.get_rapport_financier_ohada(date_debut, date_fin, exercice)
    return result


@router.get("/export/ohada")
async def exporter_rapport_ohada(
    format: str = Query(..., pattern="^(pdf|excel)$"),
    date_debut: date = Query(..., description="Date de début (YYYY-MM-DD)"),
    date_fin: date = Query(..., description="Date de fin (YYYY-MM-DD)"),
    exercice: Optional[int] = Query(None, description="Exercice comptable"),
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """Exporte le rapport financier OHADA au format PDF ou Excel."""
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
        sections = _prepare_pdf_sections_ohada(data, exercice)
        content = generer_pdf_rapport_avec_sections(titre, sections, format_paysage=True)
        media_type = "application/pdf"
        filename = f"rapport_financier_ohada_{timestamp}.pdf"
        
    else:  # excel
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
# NOUVEAUX ENDPOINTS TÂCHE 3 - TABLEAU 8, PROJECTIONS, JOURNAL
# ============================================================

@router.get("/tableau-8")
async def get_tableau8_ohada(
    background_tasks: BackgroundTasks,  # ✅ Déplacé EN PREMIER (sans default)
    annee: int = Query(..., description="Année du tableau 8"),
    format_export: Optional[str] = Query("json", pattern="^(json|pdf|excel)$", description="Format d'export"),
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """
    Génère le Tableau 8 OHADA pour une année donnée.
    - Format JSON : synchrone (rapide)
    - Format PDF/Excel : asynchrone (BackgroundTasks) avec notification email
    """
    role = current_user.role.nom.upper() if current_user.role else ""
    if role not in ["COMPTABLE", "DG", "ADMIN"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès réservé au Comptable, au DG et à l'Admin"
        )
    
    service = RapportService(db)
    
    # Format JSON : synchrone (lecture rapide)
    if format_export == "json":
        resultat = service.generer_tableau8_ohada(annee)
        return resultat
    
    # Format PDF/Excel : asynchrone avec BackgroundTasks
    if format_export in ["pdf", "excel"]:
        # Vérifier que l'utilisateur a un email
        if not current_user.email:
            raise HTTPException(
                status_code=400,
                detail="Aucune adresse email configurée pour l'envoi du rapport"
            )
        
        # 🔴 DÉPORTER EN ARRIÈRE-PLAN
        background_tasks.add_task(
            _generer_rapport_async,
            exercice=annee,
            format_export=format_export,
            user_email=current_user.email,
            user_nom=current_user.nom or "Utilisateur"
        )
        
        return {
            "message": f"Génération du Tableau 8 ({format_export}) en cours",
            "exercice": annee,
            "format": format_export,
            "status": "processing",
            "notification": f"Le rapport sera envoyé à {current_user.email}",
            "check_status": f"/api/v1/rapports/tableau-8?annee={annee}&format_export=json"
        }
    
    raise HTTPException(
        status_code=400,
        detail=f"Format d'export non supporté: {format_export}"
    )

@router.get("/tableau8/export-pdf")
@router.get("/tableau-8/export-pdf")
async def export_tableau8_pdf(
    annee: int = Query(..., description="Année du tableau 8"),
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """
    Exporte le Tableau 8 OHADA au format PDF.
    """
    import io
    role = current_user.role.nom.upper() if current_user.role else ""
    if role not in ["COMPTABLE", "DG", "ADMIN"]:
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    service = RapportService(db)
    data = service.generer_tableau8_ohada(annee)
    
    # ✅ CORRECTION : Utiliser generer_pdf_rapport_avec_sections
    from ...utils.pdf_generator import generer_pdf_rapport_avec_sections
    
    # Préparer les sections pour le PDF
    titre = f"Tableau 8 OHADA - Exercice {annee}"
    
    # Construire les données du tableau
    tableau_data = []
    for cat, valeurs in data['categories'].items():
        tableau_data.append([
            cat,
            f"{valeurs['brut_debut']:,.2f}",
            f"{valeurs['augmentations']:,.2f}",
            f"{valeurs['diminutions']:,.2f}",
            f"{valeurs['brut_fin']:,.2f}",
            f"{valeurs['amortissements_cumules']:,.2f}",
            f"{valeurs['dotations_exercice']:,.2f}",
            f"{valeurs['vnc_fin']:,.2f}"
        ])
    
    # Ajouter la ligne de total
    total = data['total_general']
    tableau_data.append([
        "TOTAL",
        f"{total['brut_debut']:,.2f}",
        f"{total['augmentations']:,.2f}",
        f"{total['diminutions']:,.2f}",
        f"{total['brut_fin']:,.2f}",
        f"{total['amortissements_cumules']:,.2f}",
        f"{total['dotations_exercice']:,.2f}",
        f"{total['vnc_fin']:,.2f}"
    ])
    
    sections = [
        {
            "titre": "Synthèse du patrimoine",
            "en_tetes": ["Catégorie", "Brut début", "Augmentations", "Diminutions", "Brut fin", "Amort. cumulés", "Dotations", "VNC fin"],
            "donnees": tableau_data
        }
    ]
    
    pdf_content = generer_pdf_rapport_avec_sections(titre, sections, format_paysage=True)
    
    return StreamingResponse(
        io.BytesIO(pdf_content if isinstance(pdf_content, bytes) else pdf_content.encode('utf-8')),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=tableau8_{annee}.pdf"}
    )

@router.get("/projections")
async def get_projections_pluriannuelles(
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """
    Récupère les projections d'investissement N+1 à N+5.
    ✅ Utilise les données pré-calculées par le CRON (lecture rapide)
    """
    role = current_user.role.nom.upper() if current_user.role else ""
    if role not in ["DG", "COMPTABLE", "ADMIN"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès réservé au DG, au Comptable et à l'Admin"
        )
    
    service = RapportService(db)
    
    # ✅ UTILISER LES DONNÉES PRÉ-CALCULÉES
    return service.get_projections_pluriannuelles()


@router.get("/projections/bien/{bien_id}")
async def get_projections_bien(
    bien_id: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """
    Récupère les projections d'investissement pour un bien spécifique.
    ✅ Utilise les données pré-calculées par le CRON
    """
    role = current_user.role.nom.upper() if current_user.role else ""
    if role not in ["DG", "COMPTABLE", "ADMIN"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès réservé au DG, au Comptable et à l'Admin"
        )
    
    service = RapportService(db)
    
    # ✅ UTILISER LES DONNÉES PRÉ-CALCULÉES
    return service.get_projections_synthese(bien_id)


# ============================================================
# JOURNAL DES IMMOBILISATIONS
# ============================================================

@router.get("/journal-immobilisations/{bien_id}")
async def get_journal_immobilisations(
    bien_id: int,
    limit: int = Query(100, ge=1, le=500, description="Nombre maximum d'événements"),
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """
    Récupère tout l'historique d'un bien (journal des immobilisations).
    """
    if not check_rapport_permission(current_user, "financier"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permissions insuffisantes pour consulter le journal"
        )
    
    audit_service = AuditService(db)
    historique = audit_service.get_historique_bien(bien_id, limit)
    arbre_remplacement = audit_service.get_arbre_remplacement(bien_id)
    
    from ...models.bien import Bien
    bien = db.query(Bien).filter(Bien.id_bien == bien_id).first()
    
    return {
        "bien_id": bien_id,
        "bien_designation": bien.description if bien else f"Bien #{bien_id}",
        "total_evenements": len(historique),
        "evenements": [
            {
                "date": e.date_evenement.isoformat() if e.date_evenement else None,
                "type": e.type_evenement.value if e.type_evenement else None,
                "libelle": e.libelle,
                "montant": float(e.montant) if e.montant else 0,
                "reference": e.reference_piece,
                "ancienne_valeur": float(e.ancienne_valeur) if e.ancienne_valeur else None,
                "nouvelle_valeur": float(e.nouvelle_valeur) if e.nouvelle_valeur else None,
                "utilisateur": e.utilisateur.nom if e.utilisateur else None
            }
            for e in historique
        ],
        "arbre_remplacement": arbre_remplacement
    }


@router.get("/journal-immobilisations/bien/{bien_id}/chronologique")
async def get_journal_immobilisations_chronologique(
    bien_id: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """
    Récupère l'historique d'un bien dans l'ordre chronologique.
    """
    if not check_rapport_permission(current_user, "financier"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permissions insuffisantes pour consulter le journal"
        )
    
    audit_service = AuditService(db)
    historique = audit_service.get_historique_bien_chronologique(bien_id)
    
    return {
        "bien_id": bien_id,
        "total_evenements": len(historique),
        "evenements": [
            {
                "date": e.date_evenement.isoformat() if e.date_evenement else None,
                "type": e.type_evenement.value if e.type_evenement else None,
                "libelle": e.libelle,
                "montant": float(e.montant) if e.montant else 0,
                "reference": e.reference_piece
            }
            for e in historique
        ]
    }


@router.get("/journal-immobilisations/statistiques")
async def get_journal_statistiques(
    date_debut: Optional[date] = Query(None, description="Date de début"),
    date_fin: Optional[date] = Query(None, description="Date de fin"),
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """
    Récupère les statistiques du journal des immobilisations.
    """
    if not check_rapport_permission(current_user, "financier"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permissions insuffisantes pour consulter les statistiques"
        )
    
    audit_service = AuditService(db)
    
    date_debut_dt = datetime.combine(date_debut, datetime.min.time()) if date_debut else None
    date_fin_dt = datetime.combine(date_fin, datetime.max.time()) if date_fin else None
    
    stats = audit_service.get_statistiques_journal(date_debut_dt, date_fin_dt)
    
    return stats


@router.get("/journal-immobilisations/arbre/{bien_id}")
async def get_arbre_remplacement(
    bien_id: int,
    inverse: bool = Query(False, description="Obtenir l'arbre inverse"),
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """
    Récupère l'arbre de remplacement d'un bien.
    """
    if not check_rapport_permission(current_user, "financier"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permissions insuffisantes pour consulter l'arbre de remplacement"
        )
    
    audit_service = AuditService(db)
    
    if inverse:
        arbre = audit_service.get_arbre_remplacement_inverse(bien_id)
    else:
        arbre = audit_service.get_arbre_remplacement(bien_id)
    
    verification = audit_service.verifier_chainage_remplacement(bien_id)
    
    return {
        "bien_id": bien_id,
        "arbre": arbre,
        "est_valide": verification["est_valide"],
        "nombre_remplacements": verification["nombre_remplacements"]
    }


# ============================================================
# FONCTIONS AIDES POUR L'EXPORT OHADA
# ============================================================

def _get_critere_projection(projection) -> str:
    """Retourne le critère ayant déclenché la projection."""
    if projection.critere_fin_amortissement:
        return "fin_amortissement"
    elif projection.critere_score_fiabilite:
        return "score_fiabilite"
    elif projection.critere_obligation_legale:
        return "obligation_legale"
    elif projection.critere_remplacement_cyclique:
        return "remplacement_cyclique"
    return "estimation"


def _prepare_pdf_sections_ohada(data: dict, exercice: int) -> list:
    """Prépare les sections pour le PDF OHADA."""
    sections = []
    
    patrimoine_data = [
        ["Valeur totale d'acquisition", f"{data['patrimoine']['valeur_totale_acquisition']:,.2f} USD"],
        ["Total des biens", str(data['patrimoine']['total_biens'])],
    ]
    sections.append({
        "titre": "A. Synthèse du patrimoine immobilier",
        "en_tetes": ["Indicateur", "Valeur"],
        "donnees": patrimoine_data
    })
    
    amort_data = [
        ["Dotations de l'exercice", f"{data['amortissements']['dotations_exercice']:,.2f} USD"],
        ["Cumul des amortissements", f"{data['amortissements']['cumul_total_amortissements']:,.2f} USD"],
        ["Valeur nette comptable (VNC)", f"{data['amortissements']['valeur_nette_comptable_totale']:,.2f} USD"],
    ]
    sections.append({
        "titre": f"B. Amortissements - Exercice {exercice} (Note 3C)",
        "en_tetes": ["Indicateur", "Valeur"],
        "donnees": amort_data
    })
    
    charges_data = [
        ["Coût des pannes", f"{data['charges_cycle_vie']['pannes']['cout_total']:,.2f} USD"],
        ["Nombre de pannes", str(data['charges_cycle_vie']['pannes']['total'])],
        ["Coût des maintenances", f"{data['charges_cycle_vie']['maintenances']['cout_total']:,.2f} USD"],
        ["Nombre de maintenances", str(data['charges_cycle_vie']['maintenances']['total'])],
        ["Total des charges", f"{data['charges_cycle_vie']['total_charges']:,.2f} USD"],
    ]
    sections.append({
        "titre": "C. Charges de maintenance et réparations",
        "en_tetes": ["Indicateur", "Valeur"],
        "donnees": charges_data
    })
    
    cessions_data = [
        ["Total des cessions", str(data['cessions_mouvements']['total_cessions'])],
        ["Total prix de vente", f"{data['cessions_mouvements']['total_prix_vente']:,.2f} USD"],
        ["Plus-values", f"{data['cessions_mouvements']['plus_values']:,.2f} USD"],
        ["Moins-values", f"{data['cessions_mouvements']['moins_values']:,.2f} USD"],
        ["Biens mis au rebut", str(data['cessions_mouvements']['total_rebuts'])],
    ]
    sections.append({
        "titre": "D. Cessions et mouvements (Note 3D)",
        "en_tetes": ["Indicateur", "Valeur"],
        "donnees": cessions_data
    })
    
    return sections


def _prepare_excel_sheets_ohada(data: dict, exercice: int) -> list:
    """Prépare les feuilles pour l'Excel OHADA."""
    feuilles = []
    
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
    
    repartition_data = [
        [t, str(v['count']), f"{v['valeur']:,.2f}"]
        for t, v in data['patrimoine']['repartition_par_type'].items()
    ]
    feuilles.append({
        "nom": "Répartition par type",
        "en_tetes": ["Type", "Nombre", "Valeur (USD)"],
        "donnees": repartition_data
    })
    
    amort_details = []
    for a in data['tableau_amortissements']['details'][:50]:
        amort_details.append([
            a['designation'],
            a['type_bien'],
            a['methode'],
            f"{a['valeur_origine']:,.2f}",
            f"{a['annuite_exercice']:,.2f}",
            f"{a['cumul_amortissements']:,.2f}",
            f"{a['valeur_nette_comptable']:,.2f}"
        ])
    
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