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