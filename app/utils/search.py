import re
from typing import Optional


def sanitize_search_term(term: Optional[str], max_length: int = 100) -> Optional[str]:
    """Nettoie une chaîne de recherche pour éviter les abus de wildcards LIKE/ILIKE."""
    if not term:
        return None
    cleaned = term.strip()[:max_length]
    cleaned = re.sub(r"[%_\\]", "", cleaned)
    return cleaned if cleaned else None


def ilike_pattern(term: Optional[str], max_length: int = 100) -> Optional[str]:
    """Retourne un motif ILIKE paramétré `%terme%` après nettoyage."""
    cleaned = sanitize_search_term(term, max_length)
    if not cleaned:
        return None
    return f"%{cleaned}%"
