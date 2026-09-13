"""Canonical geo place tags spanning both covered countries.

This is a stub with the canonical tag set only, so sources.yaml's geo_tags
can be validated against something real. Full bilingual alias lists and the
match_geo() scoring function land in Milestone 6 (relevance filter).
"""

GEO_PLACES: dict[str, list[str]] = {
    # Bulgaria
    "shabla": ["Шабла"],
    "durankulak": ["Дуранкулак"],
    "krapets": ["Крапец"],
    "tyulenovo": ["Тюленово"],
    "kavarna": ["Каварна"],
    "balchik": ["Балчик"],
    "dobrich": ["Добрич"],
    "general_toshevo": ["Генерал Тошево"],
    "tervel": ["Тервел"],
    "varna": ["Варна"],
    "silistra": ["Силистра"],
    "dulovo": ["Дулово"],
    "tutrakan": ["Тутракан"],
    # Romania
    "constanta": ["Constanța"],
    "mamaia": ["Mamaia"],
    "eforie": ["Eforie"],
    "costinesti": ["Costinești"],
    "doi_mai": ["2 Mai"],
    "vama_veche": ["Vama Veche"],
    "mangalia": ["Mangalia"],
    "limanu": ["Limanu"],
}
