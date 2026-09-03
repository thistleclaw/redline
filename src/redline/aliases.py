from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DiseaseAlias:
    key: str
    label: str
    aliases: tuple[str, ...]
    blueprint_key: str | None = None


DISEASES: tuple[DiseaseAlias, ...] = (
    DiseaseAlias("ebola", "Ebola virus disease", ("ebola", "bundibugyo"), "filoviruses"),
    DiseaseAlias("marburg", "Marburg virus disease", ("marburg",), "filoviruses"),
    DiseaseAlias("mpox", "Mpox", ("mpox", "monkeypox"), None),
    DiseaseAlias("cholera", "Cholera", ("cholera",), None),
    DiseaseAlias("cchf", "Crimean-Congo haemorrhagic fever", ("crimean-congo", "cchf"), "cchf"),
    DiseaseAlias("lassa", "Lassa fever", ("lassa",), "lassa"),
    DiseaseAlias("nipah", "Nipah and henipaviral disease", ("nipah", "henipavirus"), "nipah"),
    DiseaseAlias("mers_sars", "MERS/SARS", ("mers", "sars-cov", "sars"), "mers_sars"),
    DiseaseAlias("rvf", "Rift Valley fever", ("rift valley", "rvf"), "rift_valley_fever"),
    DiseaseAlias("zika", "Zika", ("zika",), "zika"),
    DiseaseAlias("avian_influenza", "Avian influenza", ("avian influenza", "h5n1", "h5"), None),
    DiseaseAlias("measles", "Measles", ("measles",), None),
    DiseaseAlias("oropouche", "Oropouche", ("oropouche",), None),
    DiseaseAlias("salmonella", "Salmonella", ("salmonella",), None),
    DiseaseAlias("listeria", "Listeria", ("listeria",), None),
    DiseaseAlias("ecoli", "Shiga toxin-producing E. coli", ("e. coli", "e coli", "ecoli"), None),
    DiseaseAlias("botulism", "Botulism", ("botulism",), None),
)

BLUEPRINT_EVIDENCE = {
    "filoviruses": (
        (
            "roadmap",
            "WHO R&D roadmap for Ebola and Marburg",
            "https://www.who.int/observatories/global-observatory-on-health-research-and-development/analyses-and-syntheses/who-r-d-blueprint/who-r-d-roadmaps",
        ),
    ),
    "cchf": (
        (
            "roadmap",
            "WHO R&D roadmap for CCHF",
            "https://www.who.int/observatories/global-observatory-on-health-research-and-development/analyses-and-syntheses/who-r-d-blueprint/who-r-d-roadmaps",
        ),
    ),
    "lassa": (
        (
            "roadmap",
            "WHO R&D roadmap for Lassa fever",
            "https://www.who.int/observatories/global-observatory-on-health-research-and-development/analyses-and-syntheses/who-r-d-blueprint/who-r-d-roadmaps",
        ),
    ),
    "nipah": (
        (
            "roadmap",
            "WHO R&D roadmap for Nipah",
            "https://www.who.int/observatories/global-observatory-on-health-research-and-development/analyses-and-syntheses/who-r-d-blueprint/who-r-d-roadmaps",
        ),
    ),
}


def find_disease(text: str) -> DiseaseAlias | None:
    lowered = text.casefold()
    matches = [
        (len(alias), item)
        for item in DISEASES
        for alias in item.aliases
        if re.search(rf"(?<!\w){re.escape(alias.casefold())}(?!\w)", lowered)
    ]
    return max(matches, key=lambda match: match[0])[1] if matches else None


def disease_by_key(key: str | None) -> DiseaseAlias | None:
    return next((item for item in DISEASES if item.key == key), None)
