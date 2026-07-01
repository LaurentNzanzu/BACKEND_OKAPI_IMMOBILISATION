# backend/app/utils/pdf_generator.py
import io
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch, cm
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from typing import List, Dict, Any


def generer_pdf_rapport(
    titre: str,
    en_tetes: List[str],
    donnees: List[List[Any]],
    sous_titre: str = None,
    format_paysage: bool = False
) -> bytes:
    """
    Génère un rapport PDF à partir des données fournies.
    
    Args:
        titre: Titre principal du rapport
        en_tetes: Liste des colonnes
        donnees: Liste des lignes de données
        sous_titre: Sous-titre optionnel
        format_paysage: True pour format paysage, False pour portrait
    
    Returns:
        bytes: Contenu du fichier PDF
    """
    buffer = io.BytesIO()
    
    # Choix du format
    page_size = landscape(A4) if format_paysage else A4
    
    # Création du document
    doc = SimpleDocTemplate(
        buffer,
        pagesize=page_size,
        rightMargin=0.5*cm,
        leftMargin=0.5*cm,
        topMargin=0.5*cm,
        bottomMargin=0.5*cm
    )
    
    # Styles
    styles = getSampleStyleSheet()
    style_titre = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=16,
        alignment=TA_CENTER,
        spaceAfter=20
    )
    style_sous_titre = ParagraphStyle(
        'CustomSubtitle',
        parent=styles['Normal'],
        fontSize=10,
        alignment=TA_CENTER,
        textColor=colors.grey,
        spaceAfter=15
    )
    style_date = ParagraphStyle(
        'DateStyle',
        parent=styles['Normal'],
        fontSize=8,
        alignment=TA_RIGHT,
        textColor=colors.grey
    )
    style_entete = ParagraphStyle(
        'HeaderStyle',
        parent=styles['Normal'],
        fontSize=9,
        alignment=TA_CENTER,
        textColor=colors.white,
        fontName='Helvetica-Bold'
    )
    style_cellule = ParagraphStyle(
        'CellStyle',
        parent=styles['Normal'],
        fontSize=8
    )
    
    # Éléments du document
    elements = []
    
    # Titre
    elements.append(Paragraph(titre, style_titre))
    
    # Sous-titre
    if sous_titre:
        elements.append(Paragraph(sous_titre, style_sous_titre))
    
    # Date de génération
    date_str = f"Généré le : {datetime.now().strftime('%d/%m/%Y à %H:%M')}"
    elements.append(Paragraph(date_str, style_date))
    elements.append(Spacer(1, 10))
    
    # Construction du tableau
    if donnees and len(donnees) > 0:
        # En-têtes formatées
        header_cells = [Paragraph(h, style_entete) for h in en_tetes]
        
        # Données formatées
        data_cells = []
        for ligne in donnees:
            row = []
            for cell in ligne:
                # Conversion des nombres
                if isinstance(cell, float):
                    cell_str = f"{cell:,.2f}"
                elif isinstance(cell, int):
                    cell_str = f"{cell:,}"
                elif cell is None:
                    cell_str = ""
                else:
                    cell_str = str(cell)
                row.append(Paragraph(cell_str, style_cellule))
            data_cells.append(row)
        
        # Tableau complet
        table_data = [header_cells] + data_cells
        
        # Largeurs des colonnes (auto)
        col_count = len(en_tetes)
        available_width = page_size[0] - doc.leftMargin - doc.rightMargin
        col_widths = [available_width / col_count] * col_count
        
        table = Table(table_data, colWidths=col_widths, repeatRows=1)
        
        # Style du tableau
        table.setStyle(TableStyle([
            # En-têtes
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a56db')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('TOPPADDING', (0, 0), (-1, 0), 8),
            
            # Lignes alternées
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('BACKGROUND', (0, 2), (-1, -1), colors.HexColor('#f9fafb')),
            
            # Bordures
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e5e7eb')),
            
            # Alignement des cellules
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            
            # Padding
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 1), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
        ]))
        
        elements.append(table)
    else:
        # Aucune donnée
        elements.append(Paragraph("Aucune donnée disponible pour la période sélectionnée.", styles['Normal']))
    
    # Construction du PDF
    doc.build(elements)
    
    # Récupération du contenu
    buffer.seek(0)
    return buffer.getvalue()


def generer_pdf_rapport_avec_sections(
    titre: str,
    sections: List[Dict[str, Any]],
    format_paysage: bool = False
) -> bytes:
    """
    Génère un rapport PDF avec plusieurs sections.
    
    Args:
        titre: Titre principal
        sections: Liste de dict avec 'titre', 'en_tetes', 'donnees'
        format_paysage: True pour paysage
    
    Returns:
        bytes: Contenu du fichier PDF
    """
    buffer = io.BytesIO()
    page_size = landscape(A4) if format_paysage else A4
    
    doc = SimpleDocTemplate(
        buffer,
        pagesize=page_size,
        rightMargin=0.5*cm,
        leftMargin=0.5*cm,
        topMargin=0.5*cm,
        bottomMargin=0.5*cm
    )
    
    styles = getSampleStyleSheet()
    style_titre = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=16,
        alignment=TA_CENTER,
        spaceAfter=20
    )
    style_section = ParagraphStyle(
        'SectionTitle',
        parent=styles['Heading2'],
        fontSize=12,
        spaceAfter=10,
        spaceBefore=15
    )
    style_date = ParagraphStyle(
        'DateStyle',
        parent=styles['Normal'],
        fontSize=8,
        alignment=TA_RIGHT,
        textColor=colors.grey
    )
    style_entete = ParagraphStyle(
        'HeaderStyle',
        parent=styles['Normal'],
        fontSize=9,
        alignment=TA_CENTER,
        textColor=colors.white,
        fontName='Helvetica-Bold'
    )
    style_cellule = ParagraphStyle(
        'CellStyle',
        parent=styles['Normal'],
        fontSize=8
    )
    
    elements = []
    
    # Titre principal
    elements.append(Paragraph(titre, style_titre))
    elements.append(Paragraph(f"Généré le : {datetime.now().strftime('%d/%m/%Y à %H:%M')}", style_date))
    elements.append(Spacer(1, 10))
    
    # Sections
    for idx, section in enumerate(sections):
        elements.append(Paragraph(section.get('titre', 'Section'), style_section))
        
        en_tetes = section.get('en_tetes', [])
        donnees = section.get('donnees', [])
        
        if donnees and len(donnees) > 0:
            # Construction du tableau
            header_cells = [Paragraph(h, style_entete) for h in en_tetes]
            
            data_cells = []
            for ligne in donnees:
                row = []
                for cell in ligne:
                    if isinstance(cell, float):
                        cell_str = f"{cell:,.2f}"
                    elif isinstance(cell, int):
                        cell_str = f"{cell:,}"
                    elif cell is None:
                        cell_str = ""
                    else:
                        cell_str = str(cell)
                    row.append(Paragraph(cell_str, style_cellule))
                data_cells.append(row)
            
            table_data = [header_cells] + data_cells
            col_count = len(en_tetes)
            available_width = page_size[0] - doc.leftMargin - doc.rightMargin
            col_widths = [available_width / col_count] * col_count
            
            table = Table(table_data, colWidths=col_widths, repeatRows=1)
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a56db')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 9),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e5e7eb')),
                ('BACKGROUND', (0, 1), (-1, -1), colors.white),
                ('BACKGROUND', (0, 2), (-1, -1), colors.HexColor('#f9fafb')),
                ('LEFTPADDING', (0, 0), (-1, -1), 6),
                ('RIGHTPADDING', (0, 0), (-1, -1), 6),
                ('TOPPADDING', (0, 1), (-1, -1), 6),
                ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
            ]))
            
            elements.append(table)
        else:
            elements.append(Paragraph("Aucune donnée disponible.", styles['Normal']))
        
        elements.append(Spacer(1, 10))
    
    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()


def generer_bon_decaissement_pdf(amortissement, bien, dg_user, motif: str = "") -> bytes:
    """
    Génère un bon de décaissement officiel au format PDF signé par la Direction Générale.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=1.5*cm,
        leftMargin=1.5*cm,
        topMargin=1.5*cm,
        bottomMargin=1.5*cm
    )
    
    styles = getSampleStyleSheet()
    style_titre = ParagraphStyle(
        'BonTitle',
        parent=styles['Heading1'],
        fontSize=20,
        leading=24,
        alignment=TA_CENTER,
        textColor=colors.HexColor('#1e3a8a'),
        spaceAfter=15
    )
    style_label = ParagraphStyle('BonLabel', parent=styles['Normal'], fontSize=11, fontName='Helvetica-Bold')
    style_val = ParagraphStyle('BonVal', parent=styles['Normal'], fontSize=11)
    style_stamp = ParagraphStyle(
        'Stamp',
        parent=styles['Normal'],
        fontSize=12,
        fontName='Helvetica-Bold',
        alignment=TA_CENTER,
        textColor=colors.HexColor('#15803d')
    )

    elements = []
    
    # En-tête
    elements.append(Paragraph("OKAPI IMMOBILISATIONS", ParagraphStyle('SubHeader', parent=styles['Heading2'], alignment=TA_CENTER, textColor=colors.HexColor('#475569'))))
    elements.append(Paragraph("BON DE DÉCAISSEMENT OFFICIEL", style_titre))
    elements.append(Paragraph(f"Réf: BD-AMORT-{amortissement.id_amortissement:05d} | Date: {datetime.now().strftime('%d/%m/%Y')}", ParagraphStyle('Ref', parent=styles['Normal'], alignment=TA_CENTER, textColor=colors.gray)))
    elements.append(Spacer(1, 20))

    # Détails
    nom_bien = getattr(bien, 'nom_bien', None) or getattr(bien, 'designation', None) or f"Bien #{bien.id_bien}"
    montant_str = f"{amortissement.annuite_comptable:,.2f} USD"
    
    table_data = [
        [Paragraph("ID Amortissement:", style_label), Paragraph(str(amortissement.id_amortissement), style_val)],
        [Paragraph("Bien Immobilisé:", style_label), Paragraph(f"{nom_bien} (ID: #{bien.id_bien})", style_val)],
        [Paragraph("Exercice Comptable:", style_label), Paragraph(str(amortissement.exercice), style_val)],
        [Paragraph("Méthode d'Amortissement:", style_label), Paragraph(str(amortissement.methode.value if hasattr(amortissement.methode, 'value') else amortissement.methode), style_val)],
        [Paragraph("Montant de la Dotation (Verrouillé):", style_label), Paragraph(montant_str, ParagraphStyle('Mnt', parent=style_val, fontName='Helvetica-Bold', textColor=colors.HexColor('#b91c1c')))],
    ]
    
    t = Table(table_data, colWidths=[6*cm, 11*cm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('PADDING', (0, 0), (-1, -1), 8),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 25))

    # Section Validation DG
    dg_name = getattr(dg_user, 'nom_complet', None) or getattr(dg_user, 'username', 'Direction Générale')
    validation_box = [
        [Paragraph("VISA DE LA DIRECTION GÉNÉRALE", ParagraphStyle('VHead', parent=styles['Normal'], fontName='Helvetica-Bold', alignment=TA_CENTER, textColor=colors.white))],
        [Paragraph(f"<b>Validé par :</b> {dg_name}", style_val)],
        [Paragraph(f"<b>Instructions / Motif :</b> {motif or 'Décaissement et dotation autorisés sous réserve des pièces comptables.'}", style_val)],
        [Spacer(1, 10)],
        [Paragraph("✔ APPROUVÉ & SIGNÉ NUMÉRIQUEMENT", style_stamp)]
    ]
    t_val = Table(validation_box, colWidths=[17*cm])
    t_val.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, 0), colors.HexColor('#1e3a8a')),
        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f0fdf4')),
        ('BOX', (0, 0), (-1, -1), 1.5, colors.HexColor('#16a34a')),
        ('PADDING', (0, 0), (-1, -1), 10),
    ]))
    elements.append(t_val)
    
    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()


def generer_bec_pdf(mouvement, caissier_nom: str = "", dg_nom: str = "") -> bytes:
    """Génère un Bon d'Entrée en Caisse (BEC) au format PDF."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=1.5*cm,
        leftMargin=1.5*cm,
        topMargin=1.5*cm,
        bottomMargin=1.5*cm
    )
    styles = getSampleStyleSheet()
    style_titre = ParagraphStyle(
        'BecTitle',
        parent=styles['Heading1'],
        fontSize=20,
        leading=24,
        alignment=TA_CENTER,
        textColor=colors.HexColor('#15803d'),
        spaceAfter=15
    )
    style_label = ParagraphStyle('BecLabel', parent=styles['Normal'], fontSize=11, fontName='Helvetica-Bold')
    style_val = ParagraphStyle('BecVal', parent=styles['Normal'], fontSize=11)
    
    elements = []
    elements.append(Paragraph("OKAPI IMMOBILISATIONS", ParagraphStyle('SubHeader', parent=styles['Heading2'], alignment=TA_CENTER, textColor=colors.HexColor('#475569'))))
    elements.append(Paragraph("BON D'ENTRÉE EN CAISSE", style_titre))
    elements.append(Paragraph(f"N° : {mouvement.numero_piece} | Date : {mouvement.date_mouvement.strftime('%d/%m/%Y')}", ParagraphStyle('Ref', parent=styles['Normal'], alignment=TA_CENTER, textColor=colors.gray)))
    elements.append(Spacer(1, 20))
    
    table_data = [
        [Paragraph("Montant en chiffres :", style_label), Paragraph(f"{mouvement.montant:,.2f} {mouvement.caisse.devise if mouvement.caisse else 'USD'}", ParagraphStyle('Mnt', parent=style_val, fontName='Helvetica-Bold'))],
        [Paragraph("Versé par / Payeur :", style_label), Paragraph(mouvement.beneficiaire or "Non spécifié", style_val)],
        [Paragraph("Motif de la rentrée :", style_label), Paragraph(mouvement.motif, style_val)],
        [Paragraph("Mode de règlement :", style_label), Paragraph(mouvement.mode_reglement, style_val)],
        [Paragraph("Pièce justificative :", style_label), Paragraph(mouvement.piece_jointe_url or "Aucune", style_val)],
    ]
    t = Table(table_data, colWidths=[6*cm, 11*cm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('PADDING', (0, 0), (-1, -1), 8),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 25))
    
    # Signatures
    sig_caissier = "En attente..."
    sig_dg = "En attente..."
    if mouvement.statut in ['VALIDE', 'VALIDEE']:
        sig_caissier = f"Signé par : {caissier_nom or 'Caissier'}"
    if mouvement.piece_justificative and mouvement.piece_justificative.signature_dg:
        sig_dg = f"Signé par : {dg_nom or 'DG'}"
        
    signatures = [
        [Paragraph("Signature du Caissier", style_label), Paragraph("Signature du DG", style_label)],
        [Paragraph(sig_caissier, style_val), Paragraph(sig_dg, style_val)]
    ]
    tsig = Table(signatures, colWidths=[8.5*cm, 8.5*cm])
    tsig.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('PADDING', (0, 0), (-1, -1), 10),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#cbd5e1')),
    ]))
    elements.append(tsig)
    
    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()


def generer_bsc_pdf(mouvement, caissier_nom: str = "", dg_nom: str = "") -> bytes:
    """Génère un Bon de Sortie de Caisse (BSC) au format PDF."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=1.5*cm,
        leftMargin=1.5*cm,
        topMargin=1.5*cm,
        bottomMargin=1.5*cm
    )
    styles = getSampleStyleSheet()
    style_titre = ParagraphStyle(
        'BscTitle',
        parent=styles['Heading1'],
        fontSize=20,
        leading=24,
        alignment=TA_CENTER,
        textColor=colors.HexColor('#b91c1c'),
        spaceAfter=15
    )
    style_label = ParagraphStyle('BscLabel', parent=styles['Normal'], fontSize=11, fontName='Helvetica-Bold')
    style_val = ParagraphStyle('BscVal', parent=styles['Normal'], fontSize=11)
    
    elements = []
    elements.append(Paragraph("OKAPI IMMOBILISATIONS", ParagraphStyle('SubHeader', parent=styles['Heading2'], alignment=TA_CENTER, textColor=colors.HexColor('#475569'))))
    elements.append(Paragraph("BON DE SORTIE DE CAISSE", style_titre))
    elements.append(Paragraph(f"N° : {mouvement.numero_piece} | Date : {mouvement.date_mouvement.strftime('%d/%m/%Y')}", ParagraphStyle('Ref', parent=styles['Normal'], alignment=TA_CENTER, textColor=colors.gray)))
    elements.append(Spacer(1, 20))
    
    table_data = [
        [Paragraph("Montant en chiffres :", style_label), Paragraph(f"{mouvement.montant:,.2f} {mouvement.caisse.devise if mouvement.caisse else 'USD'}", ParagraphStyle('Mnt', parent=style_val, fontName='Helvetica-Bold', textColor=colors.HexColor('#b91c1c')))],
        [Paragraph("Bénéficiaire / Fournisseur :", style_label), Paragraph(mouvement.beneficiaire or "Non spécifié", style_val)],
        [Paragraph("Motif de la sortie :", style_label), Paragraph(mouvement.motif, style_val)],
        [Paragraph("Origine :", style_label), Paragraph(mouvement.origine_type, style_val)],
        [Paragraph("Référence origine :", style_label), Paragraph(str(mouvement.origine_id), style_val)],
        [Paragraph("Pièce justificative :", style_label), Paragraph(mouvement.piece_jointe_url or "Aucune", style_val)],
    ]
    t = Table(table_data, colWidths=[6*cm, 11*cm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('PADDING', (0, 0), (-1, -1), 8),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 25))
    
    # Signatures
    sig_caissier = "En attente..."
    sig_dg = "En attente..."
    if mouvement.statut in ['VALIDE', 'VALIDEE']:
        sig_caissier = f"Signé par : {caissier_nom or 'Caissier'}"
    if mouvement.piece_justificative and mouvement.piece_justificative.signature_dg:
        sig_dg = f"Approuvé par : {dg_nom or 'DG'}"
        
    signatures = [
        [Paragraph("Signature du Caissier", style_label), Paragraph("Signature du DG", style_label)],
        [Paragraph(sig_caissier, style_val), Paragraph(sig_dg, style_val)]
    ]
    tsig = Table(signatures, colWidths=[8.5*cm, 8.5*cm])
    tsig.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('PADDING', (0, 0), (-1, -1), 10),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#cbd5e1')),
    ]))
    elements.append(tsig)
    
    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()