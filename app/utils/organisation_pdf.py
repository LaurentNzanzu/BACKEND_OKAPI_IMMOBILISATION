"""Shared institutional header. Never substitute the user's organisation."""
import io
from urllib.parse import urlsplit
from xml.sax.saxutils import escape
import urllib3
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Image, Paragraph, Spacer, Table, TableStyle
from ..core.config import settings


def logo_image(url):
    if not url:
        return None
    parsed = urlsplit(url)
    cloud = settings.CLOUDINARY_CLOUD_NAME
    # Logos only come from our configured Cloudinary account; no arbitrary URL fetching.
    if not cloud or parsed.scheme != "https" or parsed.netloc != "res.cloudinary.com" or not parsed.path.startswith(f"/{cloud}/image/upload/"):
        return None
    try:
        with urllib3.PoolManager(timeout=urllib3.Timeout(connect=2, read=3), retries=False) as http:
            response = http.request("GET", url, preload_content=False, redirect=False)
            try:
                if response.status != 200:
                    return None
                content = bytearray()
                for chunk in response.stream(65536):
                    content.extend(chunk)
                    if len(content) > 2 * 1024 * 1024:
                        return None
            finally:
                response.close()
        from ..services.organisation_profil_service import OrganisationProfilService
        OrganisationProfilService.validate_logo(bytes(content))
        image = Image(io.BytesIO(content))
        scale = min(48 / image.imageWidth, 48 / image.imageHeight)
        image.drawWidth = image.imageWidth * scale
        image.drawHeight = image.imageHeight * scale
        return image
    except Exception:
        return None


def add_organisation_header(elements, width, organisation):
    if not organisation:
        return
    styles = getSampleStyleSheet()
    text = lambda value: escape(str(value))
    lines = []
    if organisation.get("nom"):
        lines.append(f'<font size="13"><b>{text(organisation["nom"])}</b></font>')
    for field in ("sigle", "forme_juridique"):
        if organisation.get(field):
            lines.append(text(organisation[field]))
    legal = [f"{label}: {text(organisation[field])}" for field, label in
             (("rccm", "RCCM"), ("id_national", "ID national"), ("numero_impot", "N° impôt")) if organisation.get(field)]
    if legal:
        lines.append(" | ".join(legal))
    for fields in (("adresse", "ville", "province", "pays"), ("telephone", "email_contact", "site_web")):
        values = [text(organisation[field]) for field in fields if organisation.get(field)]
        if values:
            lines.append(" | ".join(values))
    paragraph = Paragraph("<br/>".join(lines), styles["Normal"])
    logo = logo_image(organisation.get("logo_url"))
    if logo:
        header = Table([[logo, paragraph]], colWidths=[60, width - 60])
        header.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP')]))
        elements.append(header)
    else:
        elements.append(paragraph)
    elements.append(Spacer(1, 12))
