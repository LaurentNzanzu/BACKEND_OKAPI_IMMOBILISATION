import unicodedata
from typing import Optional


# Caractères invisibles fréquemment copiés depuis Word/PDF/Navigateur
ZERO_WIDTH_CHARS = {
    "\u200b",  # ZERO WIDTH SPACE
    "\u200c",  # ZERO WIDTH NON-JOINER
    "\u200d",  # ZERO WIDTH JOINER
    "\u2060",  # WORD JOINER
    "\ufeff",  # ZERO WIDTH NO-BREAK SPACE (BOM)
    "\u00a0",  # NO-BREAK SPACE
    "\u2028",  # LINE SEPARATOR
    "\u2029",  # PARAGRAPH SEPARATOR
}


def normalize_email(email: Optional[str]) -> str:
    """
    Normalise un email pour la recherche en base.
    - Trim
    - Lowercase (emails sont insensibles à la casse)
    - Suppression des caractères invisibles
    - Normalisation Unicode NFC
    """
    if not email:
        return ""
    # Trim + retirer caractères invisibles
    clean = "".join(c for c in email.strip() if c not in ZERO_WIDTH_CHARS)
    # Lowercase (RFC 5321 : la partie locale peut être sensible, mais en pratique
    # on normalise pour l'UX — la plupart des serveurs le font)
    clean = clean.lower()
    # Normalisation Unicode
    clean = unicodedata.normalize("NFC", clean)
    return clean


def normalize_password(password: Optional[str]) -> str:
    """
    Normalise un mot de passe SANS altérer son contenu sémantique.

    ✅ On fait :
    - Trim des espaces en début/fin (copier-coller fréquent)
    - Suppression des caractères invisibles (BOM, zero-width)
    - Normalisation Unicode NFC (accents)

    ❌ On ne fait PAS :
    - Remplacer O par 0 ou l par 1 (le mot de passe est EXACT)
    - Changer la casse
    - Supprimer des caractères légitimes
    """
    if not password:
        return ""
    # Trim + retirer caractères invisibles
    clean = "".join(c for c in password.strip() if c not in ZERO_WIDTH_CHARS)
    # Normalisation Unicode (é vs é sont sémantiquement équivalents en NFC)
    clean = unicodedata.normalize("NFC", clean)
    return clean


def detect_ambiguous_chars(text: str) -> dict:
    """
    Détecte la présence de caractères ambigus dans un texte.
    Utilisé pour générer des messages d'aide.
    """
    if not text:
        return {"has_ambiguous": False, "types": []}

    types = []
    if "O" in text or "o" in text:
        types.append("O (lettre majuscule)")
    if "0" in text:
        types.append("0 (chiffre zéro)")
    if "l" in text:
        types.append("l (L minuscule)")
    if "1" in text:
        types.append("1 (chiffre un)")
    if "I" in text:
        types.append("I (i majuscule)")

    return {
        "has_ambiguous": len(types) > 0,
        "types": types,
        "count": len(types),
    }