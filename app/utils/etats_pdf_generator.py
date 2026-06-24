import io
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT, TA_JUSTIFY
from typing import Dict, Any, List, Optional
import os

_STYLES = None

def _get_styles():
    global _STYLES
    if _STYLES is None:
        _STYLES = getSampleStyleSheet()
        
        # Style pour le logo textuel par défaut
        _STYLES.add(ParagraphStyle(
            name='OkapiLogo',
            parent=_STYLES['Normal'],
            fontSize=24,
            alignment=TA_CENTER,
            textColor=colors.HexColor('#1b5e20'),
            fontName='Helvetica-Bold'
        ))
        
        # Titre principal
        _STYLES.add(ParagraphStyle(
            name='OkapiTitle',
            parent=_STYLES['Heading1'],
            fontSize=16,
            alignment=TA_CENTER,
            spaceAfter=15,
            textColor=colors.HexColor('#1b5e20'),
            fontName='Helvetica-Bold'
        ))
        
        # Titre de section
        _STYLES.add(ParagraphStyle(
            name='OkapiSection',
            parent=_STYLES['Heading2'],
            fontSize=11,
            spaceAfter=8,
            spaceBefore=12,
            textColor=colors.HexColor('#1b5e20'),
            fontName='Helvetica-Bold',
            textTransform='uppercase'
        ))
        
        # Labels (Hiérarchie typographique accentuée)
        _STYLES.add(ParagraphStyle(
            name='OkapiLabel',
            parent=_STYLES['Normal'],
            fontSize=9,
            textColor=colors.HexColor('#4b5563'), # Gris foncé
            fontName='Helvetica-Bold'
        ))
        
        # Valeurs standards
        _STYLES.add(ParagraphStyle(
            name='OkapiValue',
            parent=_STYLES['Normal'],
            fontSize=9,
            textColor=colors.HexColor('#1f2937') # Presque noir
        ))
        
        # Alertes et erreurs de calcul
        _STYLES.add(ParagraphStyle(
            name='OkapiValueAlert',
            parent=_STYLES['Normal'],
            fontSize=9,
            textColor=colors.HexColor('#d32f2f'), # Rouge vif
            fontName='Helvetica-Bold'
        ))
        
        # Notes de bas de page et informations légales
        _STYLES.add(ParagraphStyle(
            name='OkapiNote',
            parent=_STYLES['Normal'],
            fontSize=7,
            textColor=colors.HexColor('#6b7280')
        ))
        
        _STYLES.add(ParagraphStyle(
            name='OkapiFooter',
            parent=_STYLES['Normal'],
            fontSize=7,
            alignment=TA_CENTER,
            textColor=colors.HexColor('#9ca3af')
        ))
        
    return _STYLES

def _get_logo_path() -> str:
    possible_paths = [
        os.path.join(os.path.dirname(__file__), '..', '..', 'frontend', 'src', 'assets', 'Logo.jpeg'),
        os.path.join(os.path.dirname(__file__), '..', '..', 'frontend', 'public', 'logo.png'),
        os.path.join(os.path.dirname(__file__), '..', '..', 'frontend', 'public', 'okapi-logo.png'),
        os.path.join(os.path.dirname(__file__), '..', 'assets', 'logo.png'),
    ]
    for path in possible_paths:
        if os.path.exists(path):
            return path
    return None

def _get_etat_besoin_logo_path() -> str:
    return os.path.normpath(
        os.path.join(os.path.dirname(__file__), '..', '..', 'frontend', 'src', 'assets', 'Logo.jpeg')
    )

def _create_logo_element(logo_path: str, styles, max_width: float = 50, max_height: float = 50):
    """Crée un logo avec ratio préservé dans une zone max_width x max_height."""
    try:
        from reportlab.lib.utils import ImageReader
        reader = ImageReader(logo_path)
        iw, ih = reader.getSize()
        if iw and ih:
            scale = min(max_width / iw, max_height / ih)
            return Image(logo_path, width=iw * scale, height=ih * scale)
        return Image(logo_path, width=max_width, height=max_height)
    except Exception:
        return Paragraph("OKAPI", styles['OkapiLogo'])

def _add_header(elements, doc, titre, sous_titre=None, doc_ref=None, logo_path=None):
    styles = _get_styles()
    width = doc.width
    
    # Barre supérieure verte
    elements.append(Spacer(1, 5))
    elements.append(Table([['']], colWidths=[width], rowHeights=[2],
                          style=TableStyle([('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#1b5e20'))])))
    elements.append(Spacer(1, 12))

    # Gestion propre du branding (Logo)
    if logo_path is not None:
        resolved_logo = logo_path if os.path.exists(logo_path) else None
    else:
        resolved_logo = _get_logo_path()

    if resolved_logo:
        logo_element = _create_logo_element(resolved_logo, styles)
    else:
        logo_element = Paragraph("OKAPI", styles['OkapiLogo'])

    # Informations légales de l'entreprise
    company_data = [
        [logo_element,
         Paragraph("<font size='14'><b>OKAPI AGROBUSINESS</b></font><br/>"
                   "<font size='9'>Société Privée à Responsabilité Limitée</font><br/>"
                   "<font size='7' color='#6b7280'>RCCM: CD/KNG/RCCM/21-B-03234 | Id. Nat.: 01-A0101-N93880K | Impôt: A2283297Q</font>",
                   styles['Normal'])]
    ]
    company_table = Table(company_data, colWidths=[60, width - 60])
    company_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (1, 0), (1, 0), 12),
    ]))
    elements.append(company_table)
    elements.append(Spacer(1, 15))

    # Titre du document
    titre_para = Paragraph(f"<b>{titre}</b><br/><font size='10' color='#4b5563'>{sous_titre or ''}</font>", styles['OkapiTitle'])
    elements.append(titre_para)

    # Références et dates
    date_str = datetime.now().strftime("%d/%m/%Y à %H:%M")
    ref_line = [
        [Paragraph(f"<b>Référence :</b> {doc_ref or 'N/A'}", styles['OkapiValue']),
         Paragraph(f"<b>Date d'édition :</b> {date_str}", styles['OkapiValue'])]
    ]
    ref_table = Table(ref_line, colWidths=[width/2, width/2])
    ref_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
    ]))
    elements.append(ref_table)

    # Séparateur subtil
    elements.append(Table([['']], colWidths=[width], rowHeights=[0.5],
                          style=TableStyle([('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#e5e7eb'))])))
    elements.append(Spacer(1, 15))

def _add_footer(elements, doc):
    styles = _get_styles()
    elements.append(Spacer(1, 25))
    elements.append(Table([['']], colWidths=[doc.width], rowHeights=[0.5],
                          style=TableStyle([('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#e5e7eb'))])))
    elements.append(Spacer(1, 6))
    footer_text = f"Document généré par OKAPI AGROBUSINESS le {datetime.now().strftime('%d/%m/%Y à %H:%M:%S')}"
    elements.append(Paragraph(footer_text, styles['OkapiFooter']))

def _create_info_table(data: List[List], col_widths: List) -> Table:
    # Tableau minimaliste (lignes horizontales uniquement)
    table = Table(data, colWidths=col_widths)
    style_commands = [
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
    ]

    for i in range(len(data)):
        if i < len(data) - 1:
            style_commands.append(('LINEBELOW', (0, i), (-1, i), 0.5, colors.HexColor('#f3f4f6')))

    table.setStyle(TableStyle(style_commands))
    return table

def generate_fiche_bien_pdf(data: Dict[str, Any]) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            rightMargin=1.8*cm, leftMargin=1.8*cm,
                            topMargin=1.5*cm, bottomMargin=1.5*cm)
    styles = _get_styles()
    elements = []
    
    bien = data['bien']
    type_bien = bien.get('type_bien', 'Bien').upper()
    marque_fabricant = bien.get('marque_fabricant', '') or ''
    modele = bien.get('modele', '') or ''

    designation = f"{marque_fabricant} {modele}".strip()
    if not designation:
        designation = f"Bien #{bien.get('id_bien', '')}"

    titre = "FICHE D'IMMOBILISATION"
    sous_titre = f"{type_bien} • {designation}"
    _add_header(elements, doc, titre, sous_titre, bien.get('qr_code'))

    elements.append(Paragraph("1. IDENTIFICATION DU BIEN", styles['OkapiSection']))

    # Calcul de la valeur réelle de l'immobilisation incluant tous les frais
    prix_acq = bien.get('prix_acquisition', 0)
    transport = bien.get('frais_transport', 0)
    douane = bien.get('frais_douane', 0)
    assurance = bien.get('assurance', 0)
    manutention = bien.get('manutention', 0)
    
    # La valeur totale intègre tous les coûts de mise en service
    prix_total_evalue = prix_acq + transport + douane + assurance + manutention

    ident_data = [
        [Paragraph("Type d'immobilisation:", styles['OkapiLabel']), Paragraph(bien.get('type_bien', '-') or "-", styles['OkapiValue']), 
         Paragraph("État:", styles['OkapiLabel']), Paragraph(bien.get('etat', '-') or "-", styles['OkapiValue'])],
        [Paragraph("Marque / Fabricant:", styles['OkapiLabel']), Paragraph(marque_fabricant or "-", styles['OkapiValue']), 
         Paragraph("Modèle:", styles['OkapiLabel']), Paragraph(modele or "-", styles['OkapiValue'])],
        [Paragraph("N° Série / Immat.:", styles['OkapiLabel']), Paragraph(bien.get('numero_serie', '-') or "-", styles['OkapiValue']), 
         Paragraph("Âge:", styles['OkapiLabel']), Paragraph(f"{bien.get('age_ans', 0)} an(s)", styles['OkapiValue'])],
        [Paragraph("Localisation:", styles['OkapiLabel']), Paragraph(bien.get('localisation', '-') or "-", styles['OkapiValue']), 
         Paragraph("Date acquisition:", styles['OkapiLabel']), Paragraph(bien.get('date_acquisition', '-') or "-", styles['OkapiValue'])],
        [Paragraph("Prix d'acquisition:", styles['OkapiLabel']), Paragraph(f"{prix_acq:,.0f} FCFA", styles['OkapiValue']), 
         Paragraph("<b>Valeur Totale (avec frais):</b>", styles['OkapiLabel']), Paragraph(f"<b>{prix_total_evalue:,.0f} FCFA</b>", styles['OkapiValue'])],
    ]

    ident_table = _create_info_table(ident_data, [doc.width*0.22, doc.width*0.28, doc.width*0.22, doc.width*0.28])
    elements.append(ident_table)

    if bien.get('description'):
        elements.append(Spacer(1, 10))
        elements.append(Paragraph("<b>Description :</b>", styles['OkapiLabel']))
        elements.append(Spacer(1, 4))
        elements.append(Paragraph(bien['description'], styles['OkapiValue']))

    specificites = bien.get('specificites', {})
    if specificites:
        elements.append(Spacer(1, 18))
        elements.append(Paragraph("2. CARACTÉRISTIQUES TECHNIQUES", styles['OkapiSection']))
        
        # Mise en page aérée sur deux colonnes (Label au-dessus de la valeur)
        spec_items = list(specificites.items())
        col1_data = []
        col2_data = []
        
        for i, (key, val) in enumerate(spec_items):
            label = key.replace('_', ' ').title()
            value = str(val) if val else "-"
            item_html = f"<b><font color='#4b5563'>{label}</font></b><br/><font color='#1f2937'>{value}</font>"
            
            if i % 2 == 0:
                col1_data.append(Paragraph(item_html, styles['Normal']))
            else:
                col2_data.append(Paragraph(item_html, styles['Normal']))
        
        while len(col1_data) > len(col2_data):
            col2_data.append(Spacer(1, 0))
        
        spec_table_data = list(zip(col1_data, col2_data))
        spec_table = Table(spec_table_data, colWidths=[doc.width/2 - 5, doc.width/2 - 5])
        spec_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 12), # Respiration
            ('LEFTPADDING', (0, 0), (0, -1), 0),
            ('LEFTPADDING', (1, 0), (1, -1), 20),
        ]))
        elements.append(spec_table)

    elements.append(Spacer(1, 18))
    elements.append(Paragraph("3. DÉCOMPOSITION EN COMPOSANTS (OHADA)", styles['OkapiSection']))
    
    composants = data.get('composants', [])
    # Utilisation de la Valeur Totale Évaluée pour éviter les pourcentages anormaux
    prix_de_base = prix_total_evalue if prix_total_evalue > 0 else 1

    if composants:
        total_compos = sum(c.get('valeur', 0) for c in composants)
        is_overflow = total_compos > prix_total_evalue
        
        comp_data = [["Désignation", "Valeur (FCFA)", "Durée de vie", "% du bien"]]
        
        for comp in composants:
            valeur = comp.get('valeur', 0)
            pourc = (valeur / prix_de_base * 100)
            
            comp_data.append([
                comp.get('designation', '-'),
                f"{valeur:,.0f}",
                f"{comp.get('duree_vie_ans', 0)} ans",
                f"{pourc:.1f}%"
            ])
        
        pourc_total = (total_compos / prix_de_base * 100)
        is_total_alert = pourc_total > 100
        
        comp_data.append([
            Paragraph("<b>TOTAL COMPOSANTS</b>", styles['OkapiLabel']),
            Paragraph(f"<b>{total_compos:,.0f}</b>", styles['OkapiLabel']),
            " ",
            Paragraph(f"<b>{pourc_total:.1f}%</b>", styles['OkapiValueAlert'] if is_total_alert else styles['OkapiLabel'])
        ])
        
        valeur_structure = prix_total_evalue - total_compos
        pourc_structure = 100 - pourc_total
        is_structure_negative = valeur_structure < 0
        
        comp_data.append([
            Paragraph("<b>VALEUR STRUCTURE</b>", styles['OkapiLabel']),
            Paragraph(f"<b>{valeur_structure:,.0f}</b>", styles['OkapiValueAlert'] if is_structure_negative else styles['OkapiLabel']),
            " ",
            Paragraph(f"<b>{pourc_structure:.1f}%</b>", styles['OkapiValueAlert'] if is_structure_negative else styles['OkapiLabel'])
        ])
        
        col_widths = [doc.width*0.45, doc.width*0.20, doc.width*0.20, doc.width*0.15]
        comp_table = Table(comp_data, colWidths=col_widths)
        
        style_commands = [
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1b5e20')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 8),
            ('ALIGN', (1, 1), (1, -1), 'RIGHT'),
            ('ALIGN', (2, 1), (2, -1), 'CENTER'),
            ('ALIGN', (3, 1), (3, -1), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ]
        
        # Design minimaliste : lignes simples
        for i in range(len(comp_data)):
            if i < len(comp_data) - 1:
                style_commands.append(('LINEBELOW', (0, i), (-1, i), 0.5, colors.HexColor('#e5e7eb')))
        
        # Surlignage d'erreur si débordement
        if is_total_alert or is_structure_negative:
            style_commands.append(('BACKGROUND', (0, len(comp_data)-2), (-1, -1), colors.HexColor('#fef2f2')))
        
        comp_table.setStyle(TableStyle(style_commands))
        elements.append(comp_table)
        
        if is_overflow:
            elements.append(Spacer(1, 8))
            elements.append(Paragraph("<font color='#d32f2f'><b>⚠️ Alerte de valorisation :</b> La somme des composants dépasse la Valeur Totale du bien (incluant frais annexes).</font>", styles['OkapiNote']))
        else:
            elements.append(Spacer(1, 8))
            elements.append(Paragraph("Note : Conformément à l'article 38-1 de l'AUDCIF, la décomposition en composants permet un amortissement différencié calculé sur la valeur d'origine complète.", styles['OkapiNote']))
    else:
        elements.append(Paragraph("Aucun composant défini pour ce bien. Amortissement global recommandé.", styles['OkapiValue']))

    elements.append(Spacer(1, 18))
    maintenances = data.get('maintenances_recentes', [])
    pannes = data.get('pannes_recentes', [])

    if maintenances or pannes:
        elements.append(Paragraph("4. HISTORIQUE RÉCENT", styles['OkapiSection']))
        
        if maintenances:
            elements.append(Paragraph("<b>Dernières maintenances</b>", styles['OkapiLabel']))
            elements.append(Spacer(1, 6))
            maint_data = [["Date", "Type", "Coût (FCFA)"]]
            for m in maintenances[:3]:
                maint_data.append([m.get('date', '-'), m.get('type', '-'), f"{m.get('cout', 0):,.0f}"])
            
            maint_table = Table(maint_data, colWidths=[doc.width/3, doc.width/3, doc.width/3])
            maint_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f3f4f6')),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('TOPPADDING', (0, 0), (-1, -1), 8),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                ('LINEBELOW', (0, 0), (-1, 0), 1, colors.HexColor('#d1d5db')),
            ]))
            for i in range(1, len(maint_data)):
                maint_table.setStyle(TableStyle([('LINEBELOW', (0, i), (-1, i), 0.5, colors.HexColor('#e5e7eb'))]))
            elements.append(maint_table)
            elements.append(Spacer(1, 12))
        
        if pannes:
            elements.append(Paragraph("<b>Dernières pannes</b>", styles['OkapiLabel']))
            elements.append(Spacer(1, 6))
            panne_data = [["Date", "Type", "Statut"]]
            for p in pannes[:3]:
                panne_data.append([p.get('date', '-'), p.get('type', '-'), p.get('statut', '-')])
            
            panne_table = Table(panne_data, colWidths=[doc.width/3, doc.width/3, doc.width/3])
            panne_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f3f4f6')),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('TOPPADDING', (0, 0), (-1, -1), 8),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                ('LINEBELOW', (0, 0), (-1, 0), 1, colors.HexColor('#d1d5db')),
            ]))
            for i in range(1, len(panne_data)):
                panne_table.setStyle(TableStyle([('LINEBELOW', (0, i), (-1, i), 0.5, colors.HexColor('#e5e7eb'))]))
            elements.append(panne_table)

    # Bloc signatures (Épuré)
    elements.append(Spacer(1, 35))
    sig_data = [
        ["Le Responsable du Patrimoine", "Le Directeur Général", "Le Comptable"],
        [" ", " ", " "],
        ["(Cachet et signature)", "(Cachet et signature)", "(Cachet et signature)"]
    ]
    sig_table = Table(sig_data, colWidths=[doc.width/3, doc.width/3, doc.width/3])
    sig_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#4b5563')),
        ('FONTSIZE', (0, 2), (-1, 2), 7),
        ('TEXTCOLOR', (0, 2), (-1, 2), colors.HexColor('#9ca3af')),
        ('TOPPADDING', (0, 1), (-1, 1), 40), # Espace pour signer
        ('BOTTOMPADDING', (0, 1), (-1, 1), 10),
    ]))
    elements.append(sig_table)

    _add_footer(elements, doc)

    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()

def generate_fiche_amortissement_pdf(data: Dict[str, Any]) -> bytes:
    """Génère le PDF de la fiche d'amortissement d'un bien"""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            rightMargin=1.8*cm, leftMargin=1.8*cm,
                            topMargin=1.5*cm, bottomMargin=1.5*cm)
    styles = _get_styles()
    elements = []
    
    bien = data['bien']
    amort = data['amortissement']
    plan = data.get('plan_amortissement', [])
    stats = data.get('statistiques', {})
    ecritures = data.get('ecritures_comptables', [])
    
    designation = f"{bien.get('marque_fabricant', '')} {bien.get('modele', '')}".strip()
    if not designation:
        designation = f"Bien #{bien.get('id_bien', '')}"
    
    titre = "FICHE D'AMORTISSEMENT"
    sous_titre = f"{bien.get('type_bien', '').upper()} • {designation}"
    _add_header(elements, doc, titre, sous_titre, bien.get('qr_code'))
    
    # 1. IDENTIFICATION DU BIEN
    elements.append(Paragraph("1. IDENTIFICATION DU BIEN", styles['OkapiSection']))
    
    ident_data = [
        [Paragraph("Désignation:", styles['OkapiLabel']), Paragraph(designation, styles['OkapiValue']),
         Paragraph("Type:", styles['OkapiLabel']), Paragraph(bien.get('type_bien', '-'), styles['OkapiValue'])],
        [Paragraph("Localisation:", styles['OkapiLabel']), Paragraph(bien.get('localisation', '-'), styles['OkapiValue']),
         Paragraph("État:", styles['OkapiLabel']), Paragraph(bien.get('etat', '-'), styles['OkapiValue'])],
        [Paragraph("Date acquisition:", styles['OkapiLabel']), Paragraph(bien.get('date_acquisition', '-'), styles['OkapiValue']),
         Paragraph("Valeur d'origine:", styles['OkapiLabel']), Paragraph(f"{amort.get('valeur_origine', 0):,.0f} FCFA", styles['OkapiValue'])],
    ]
    
    ident_table = _create_info_table(ident_data, [doc.width*0.22, doc.width*0.28, doc.width*0.22, doc.width*0.28])
    elements.append(ident_table)
    elements.append(Spacer(1, 10))
    
    # 2. PARAMÈTRES D'AMORTISSEMENT
    elements.append(Paragraph("2. PARAMÈTRES D'AMORTISSEMENT", styles['OkapiSection']))
    
    params_data = [
        [Paragraph("Méthode:", styles['OkapiLabel']), Paragraph(amort.get('methode', 'LINEAIRE'), styles['OkapiValue']),
         Paragraph("Exercice en cours:", styles['OkapiLabel']), Paragraph(str(amort.get('exercice_en_cours', '-')), styles['OkapiValue'])],
        [Paragraph("Taux comptable:", styles['OkapiLabel']), Paragraph(f"{amort.get('taux_comptable', 0):.1f}%", styles['OkapiValue']),
         Paragraph("Taux fiscal:", styles['OkapiLabel']), Paragraph(f"{amort.get('taux_fiscal', 0):.1f}%", styles['OkapiValue'])],
        [Paragraph("Durée comptable:", styles['OkapiLabel']), Paragraph(f"{amort.get('duree_vie_comptable_ans', 0)} ans", styles['OkapiValue']),
         Paragraph("Durée fiscale:", styles['OkapiLabel']), Paragraph(f"{amort.get('duree_vie_fiscale_ans', 0)} ans", styles['OkapiValue'])],
    ]
    
    params_table = _create_info_table(params_data, [doc.width*0.22, doc.width*0.28, doc.width*0.22, doc.width*0.28])
    elements.append(params_table)
    elements.append(Spacer(1, 10))
    
    # 3. SITUATION ACTUELLE
    elements.append(Paragraph("3. SITUATION ACTUELLE", styles['OkapiSection']))
    
    # Cartes de synthèse
    synth_data = [
        [Paragraph("<b>Valeur d'origine</b>", styles['OkapiLabel']),
         Paragraph(f"<b>{amort.get('valeur_origine', 0):,.0f} FCFA</b>", styles['OkapiValue']),
         Paragraph("<b>Valeur résiduelle</b>", styles['OkapiLabel']),
         Paragraph(f"<b>{amort.get('valeur_residuelle', 0):,.0f} FCFA</b>", styles['OkapiValue'])],
        [Paragraph("<b>Cumul amorti</b>", styles['OkapiLabel']),
         Paragraph(f"<b>{amort.get('cumul_amorti', 0):,.0f} FCFA</b>", styles['OkapiValue']),
         Paragraph("<b>VNC actuelle</b>", styles['OkapiLabel']),
         Paragraph(f"<b>{amort.get('vnc_actuelle', 0):,.0f} FCFA</b>", styles['OkapiValue'])],
        [Paragraph("<b>Date début</b>", styles['OkapiLabel']),
         Paragraph(amort.get('date_debut', '-'), styles['OkapiValue']),
         Paragraph("<b>Statut</b>", styles['OkapiLabel']),
         Paragraph(amort.get('statut', 'EN_COURS'), styles['OkapiValue'])],
    ]
    
    synth_table = Table(synth_data, colWidths=[doc.width*0.22, doc.width*0.28, doc.width*0.22, doc.width*0.28])
    synth_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f0fdf4')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#dcfce7')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
    ]))
    elements.append(synth_table)
    
    # Barre de progression
    pourcentage = stats.get('pourcentage_amorti', 0)
    elements.append(Spacer(1, 10))
    
    progress_data = [
        [Paragraph(f"Progression de l'amortissement: {pourcentage:.1f}%", styles['OkapiLabel']),
         Paragraph(f"Années restantes: {stats.get('annees_restantes', 0)}", styles['OkapiLabel'])]
    ]
    progress_table = Table(progress_data, colWidths=[doc.width/2, doc.width/2])
    progress_table.setStyle(TableStyle([
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    elements.append(progress_table)
    
    elements.append(Spacer(1, 15))
    
    # 4. PLAN D'AMORTISSEMENT
    elements.append(Paragraph("4. PLAN D'AMORTISSEMENT PRÉVISIONNEL", styles['OkapiSection']))
    
    if plan:
        plan_data = [["Année", "VNC début (FCFA)", "Annuité (FCFA)", "Cumul (FCFA)", "VNC fin (FCFA)"]]
        
        for p in plan:
            plan_data.append([
                str(p['annee']),
                f"{p['vnc_debut']:,.0f}",
                f"{p['annuite']:,.0f}",
                f"{p['cumul']:,.0f}",
                f"{p['vnc_fin']:,.0f}"
            ])
        
        col_widths = [doc.width*0.12, doc.width*0.22, doc.width*0.22, doc.width*0.22, doc.width*0.22]
        plan_table = Table(plan_data, colWidths=col_widths)
        
        style_commands = [
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1b5e20')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 8),
            ('ALIGN', (1, 1), (-1, -1), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ]
        
        # Mise en évidence de l'année en cours
        for idx, p in enumerate(plan):
            if p.get('est_annee_courante'):
                style_commands.append(('BACKGROUND', (0, idx+1), (-1, idx+1), colors.HexColor('#fef3c7')))
            if idx < len(plan) - 1:
                style_commands.append(('LINEBELOW', (0, idx+1), (-1, idx+1), 0.5, colors.HexColor('#e5e7eb')))
        
        plan_table.setStyle(TableStyle(style_commands))
        elements.append(plan_table)
        
        elements.append(Spacer(1, 8))
        note_text = f"Plan établi sur {stats.get('duree_totale_ans', 0)} ans • Annuité moyenne: {stats.get('annuite_moyenne', 0):,.0f} FCFA"
        elements.append(Paragraph(note_text, styles['OkapiNote']))
    else:
        elements.append(Paragraph("Aucun plan d'amortissement disponible.", styles['OkapiValue']))
    
    elements.append(Spacer(1, 15))
    
    # 5. DERNIÈRES ÉCRITURES COMPTABLES
    if ecritures:
        elements.append(Paragraph("5. DERNIÈRES ÉCRITURES COMPTABLES", styles['OkapiSection']))
        
        ecrit_data = [["Date", "Type", "Comptes", "Montant (FCFA)", "Statut"]]
        for e in ecritures[:5]:
            ecrit_data.append([
                e.get('date', '-'),
                e.get('type', '-'),
                f"{e.get('compte_debit', '')} / {e.get('compte_credit', '')}",
                f"{e.get('montant', 0):,.0f}",
                "Validée" if e.get('validee') else "En attente"
            ])
        
        col_widths = [doc.width*0.15, doc.width*0.15, doc.width*0.30, doc.width*0.20, doc.width*0.20]
        ecrit_table = Table(ecrit_data, colWidths=col_widths)
        ecrit_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1b5e20')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('ALIGN', (3, 1), (3, -1), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('LINEBELOW', (0, 0), (-1, 0), 1, colors.HexColor('#d1d5db')),
        ]))
        for i in range(1, len(ecrit_data)):
            ecrit_table.setStyle(TableStyle([('LINEBELOW', (0, i), (-1, i), 0.5, colors.HexColor('#e5e7eb'))]))
        elements.append(ecrit_table)
    
    # 6. SIGNATURES
    elements.append(Spacer(1, 35))
    sig_data = [
        ["Le Comptable", "Le Responsable Financier", "Le Directeur Général"],
        [" ", " ", " "],
        ["(Cachet et signature)", "(Cachet et signature)", "(Cachet et signature)"]
    ]
    sig_table = Table(sig_data, colWidths=[doc.width/3, doc.width/3, doc.width/3])
    sig_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#4b5563')),
        ('FONTSIZE', (0, 2), (-1, 2), 7),
        ('TEXTCOLOR', (0, 2), (-1, 2), colors.HexColor('#9ca3af')),
        ('TOPPADDING', (0, 1), (-1, 1), 40),
        ('BOTTOMPADDING', (0, 1), (-1, 1), 10),
    ]))
    elements.append(sig_table)
    
    _add_footer(elements, doc)
    
    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()


def generate_etat_besoin_pdf(data: Dict[str, Any]) -> bytes:
    """Génère le PDF de l'état de sortie pour une demande de besoin."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=1.8 * cm,
        leftMargin=1.8 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
    )
    styles = _get_styles()
    elements = []

    besoin = data["besoin"]
    panne = data.get("panne") or {}
    bien = data.get("bien") or {}
    lignes = data.get("lignes", [])
    circuit = data.get("circuit_validation", [])

    titre = "ÉTAT DE SORTIE — DEMANDE DE BESOIN"
    sous_titre = f"Panne #{panne.get('id_panne', 'N/A')} • {bien.get('designation', '')}"
    _add_header(
        elements, doc, titre, sous_titre, besoin.get("numero_demande"),
        logo_path=_get_etat_besoin_logo_path(),
    )

    # 1. INFORMATIONS DE LA DEMANDE
    elements.append(Paragraph("1. INFORMATIONS DE LA DEMANDE", styles["OkapiSection"]))
    demande_data = [
        [
            Paragraph("N° demande:", styles["OkapiLabel"]),
            Paragraph(besoin.get("numero_demande", "-"), styles["OkapiValue"]),
            Paragraph("Date création:", styles["OkapiLabel"]),
            Paragraph(besoin.get("date_creation", "-"), styles["OkapiValue"]),
        ],
        [
            Paragraph("Statut:", styles["OkapiLabel"]),
            Paragraph(besoin.get("statut", "-"), styles["OkapiValue"]),
            Paragraph("Montant total:", styles["OkapiLabel"]),
            Paragraph(f"{besoin.get('montant_total', 0):,.0f} USD", styles["OkapiValue"]),
        ],
        [
            Paragraph("Technicien:", styles["OkapiLabel"]),
            Paragraph(data.get("technicien", "N/A"), styles["OkapiValue"]),
            Paragraph("Panne:", styles["OkapiLabel"]),
            Paragraph(f"#{panne.get('id_panne', '-')}", styles["OkapiValue"]),
        ],
    ]
    if besoin.get("observations"):
        demande_data.append([
            Paragraph("Observations:", styles["OkapiLabel"]),
            Paragraph(besoin.get("observations", ""), styles["OkapiValue"]),
            Paragraph("", styles["OkapiLabel"]),
            Paragraph("", styles["OkapiValue"]),
        ])
    elements.append(_create_info_table(demande_data, [doc.width * 0.22, doc.width * 0.28, doc.width * 0.22, doc.width * 0.28]))
    elements.append(Spacer(1, 10))

    # 2. BIEN CONCERNÉ
    if bien:
        elements.append(Paragraph("2. BIEN CONCERNÉ", styles["OkapiSection"]))
        bien_data = [
            [
                Paragraph("QR Code:", styles["OkapiLabel"]),
                Paragraph(bien.get("qr_code", "-"), styles["OkapiValue"]),
                Paragraph("Type:", styles["OkapiLabel"]),
                Paragraph(bien.get("type_bien", "-"), styles["OkapiValue"]),
            ],
            [
                Paragraph("Désignation:", styles["OkapiLabel"]),
                Paragraph(bien.get("designation", "-"), styles["OkapiValue"]),
                Paragraph("Localisation:", styles["OkapiLabel"]),
                Paragraph(bien.get("localisation", "-"), styles["OkapiValue"]),
            ],
        ]
        elements.append(_create_info_table(bien_data, [doc.width * 0.22, doc.width * 0.28, doc.width * 0.22, doc.width * 0.28]))
        elements.append(Spacer(1, 10))

    # 3. PIÈCES À SORTIR DU STOCK
    elements.append(Paragraph("3. PIÈCES À SORTIR DU STOCK", styles["OkapiSection"]))
    table_data = [
        [
            Paragraph("<b>Référence</b>", styles["OkapiLabel"]),
            Paragraph("<b>Désignation</b>", styles["OkapiLabel"]),
            Paragraph("<b>Qté</b>", styles["OkapiLabel"]),
            Paragraph("<b>Stock</b>", styles["OkapiLabel"]),
            Paragraph("<b>P.U.</b>", styles["OkapiLabel"]),
            Paragraph("<b>Total</b>", styles["OkapiLabel"]),
        ]
    ]
    for ligne in lignes:
        table_data.append([
            Paragraph(ligne.get("reference", "-"), styles["OkapiValue"]),
            Paragraph(ligne.get("designation", "-"), styles["OkapiValue"]),
            Paragraph(str(ligne.get("quantite", 0)), styles["OkapiValue"]),
            Paragraph(str(ligne.get("stock_actuel", 0)), styles["OkapiValue"]),
            Paragraph(f"{ligne.get('prix_unitaire', 0):,.0f}", styles["OkapiValue"]),
            Paragraph(f"{ligne.get('prix_total', 0):,.0f}", styles["OkapiValue"]),
        ])
    table_data.append([
        Paragraph("", styles["OkapiValue"]),
        Paragraph("", styles["OkapiValue"]),
        Paragraph("", styles["OkapiValue"]),
        Paragraph("", styles["OkapiValue"]),
        Paragraph("<b>TOTAL</b>", styles["OkapiLabel"]),
        Paragraph(f"<b>{besoin.get('montant_total', 0):,.0f} USD</b>", styles["OkapiValue"]),
    ])
    pieces_table = Table(
        table_data,
        colWidths=[doc.width * 0.14, doc.width * 0.30, doc.width * 0.08, doc.width * 0.10, doc.width * 0.16, doc.width * 0.16],
    )
    pieces_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f0fdf4")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e5e7eb")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("ALIGN", (2, 0), (3, -1), "CENTER"),
        ("ALIGN", (4, 0), (-1, -1), "RIGHT"),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#f9fafb")),
    ]))
    elements.append(pieces_table)
    elements.append(Spacer(1, 12))

    # 4. CIRCUIT DE VALIDATION
    elements.append(Paragraph("4. CIRCUIT DE VALIDATION", styles["OkapiSection"]))
    val_data = [
        [
            Paragraph("<b>Étape</b>", styles["OkapiLabel"]),
            Paragraph("<b>Validateur</b>", styles["OkapiLabel"]),
            Paragraph("<b>Décision</b>", styles["OkapiLabel"]),
            Paragraph("<b>Date</b>", styles["OkapiLabel"]),
        ]
    ]
    for etape in circuit:
        decision = etape.get("decision", "EN_ATTENTE")
        decision_style = styles["OkapiValueAlert"] if decision == "REJETE" else styles["OkapiValue"]
        val_data.append([
            Paragraph(etape.get("libelle", etape.get("ordre", "")), styles["OkapiValue"]),
            Paragraph(etape.get("validateur") or "—", styles["OkapiValue"]),
            Paragraph(decision, decision_style),
            Paragraph(etape.get("date") or "—", styles["OkapiValue"]),
        ])
    val_table = Table(val_data, colWidths=[doc.width * 0.28, doc.width * 0.30, doc.width * 0.20, doc.width * 0.22])
    val_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f0fdf4")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e5e7eb")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    elements.append(val_table)
    elements.append(Spacer(1, 20))

    # 5. SIGNATURES
    elements.append(Paragraph("5. SIGNATURES DE SORTIE", styles["OkapiSection"]))
    sig_data = [
        [
            Paragraph("<b>Technicien demandeur</b>", styles["OkapiLabel"]),
            Paragraph("<b>Magasinier</b>", styles["OkapiLabel"]),
            Paragraph("<b>Date de sortie</b>", styles["OkapiLabel"]),
        ],
        [
            Paragraph(f"<br/><br/>{data.get('technicien', '')}<br/>_____________________", styles["OkapiValue"]),
            Paragraph("<br/><br/><br/>_____________________", styles["OkapiValue"]),
            Paragraph("<br/><br/><br/>____ / ____ / ______", styles["OkapiValue"]),
        ],
    ]
    sig_table = Table(sig_data, colWidths=[doc.width / 3, doc.width / 3, doc.width / 3])
    sig_table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e5e7eb")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 1), (-1, 1), 30),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
    ]))
    elements.append(sig_table)

    _add_footer(elements, doc)
    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()