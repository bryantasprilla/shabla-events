"""Canonical geo place tags spanning both covered countries, with bilingual
alias lists for the relevance filter's geo gate (Milestone 6) and for
location matching in dedup.py (Milestone 8).
"""

GEO_PLACES: dict[str, list[str]] = {
    # Bulgaria
    "shabla": ["Шабла", "гр. Шабла", "община Шабла"],
    "durankulak": ["Дуранкулак"],
    "krapets": ["Крапец"],
    "tyulenovo": ["Тюленово"],
    "kavarna": ["Каварна", "община Каварна", "каварненски"],
    "balchik": ["Балчик", "община Балчик", "балчишки"],
    "dobrich": ["Добрич", "област Добрич", "добрички"],
    "general_toshevo": ["Генерал Тошево"],
    "tervel": ["Тервел"],
    "varna": ["Варна", "община Варна", "варненски", "гр. Варна", "Varna"],
    "silistra": ["Силистра", "област Силистра"],
    "dulovo": ["Дулово"],
    "tutrakan": ["Тутракан"],
    # Romania
    "constanta": ["Constanța", "Constanta", "județul Constanța", "judetul Constanta"],
    "mamaia": ["Mamaia"],
    "eforie": ["Eforie", "Eforie Nord", "Eforie Sud"],
    "costinesti": ["Costinești", "Costinesti"],
    "doi_mai": ["2 Mai", "Doi Mai"],
    "vama_veche": ["Vama Veche"],
    "mangalia": ["Mangalia"],
    "limanu": ["Limanu"],
}


def match_geo(text: str) -> list[str]:
    """Case-insensitive substring match against every alias. Returns the
    canonical tags found, in GEO_PLACES iteration order (Bulgaria first)."""
    text_lower = (text or "").lower()
    matched = []
    for tag, aliases in GEO_PLACES.items():
        if any(alias.lower() in text_lower for alias in aliases):
            matched.append(tag)
    return matched
