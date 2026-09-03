from __future__ import annotations

import re
from dataclasses import dataclass

from redline.models import CountermeasureEvidence, SourceDocument

WHO_BLUEPRINT_HOME = "https://www.who.int/teams/blueprint"
WHO_PRIORITY_FRAMEWORK = (
    "https://www.who.int/publications/m/item/"
    "pathogens-prioritization-a-scientific-framework-for-epidemic-and-pandemic-research-preparedness"
)
WHO_ROADMAPS = (
    "https://www.who.int/observatories/global-observatory-on-health-research-and-development/"
    "analyses-and-syntheses/who-r-d-blueprint/who-r-d-roadmaps"
)
WHO_TPPS = (
    "https://www.who.int/observatories/global-observatory-on-health-research-and-development/"
    "analyses-and-syntheses/who-r-d-blueprint/who-target-product-profiles"
)
WHO_TPP_DIRECTORY = (
    "https://www.who.int/observatories/global-observatory-on-health-research-and-development/"
    "analyses-and-syntheses/target-product-profile/links-to-who-tpps-and-ppcs"
)
WHO_TRIAL_PROTOCOLS = (
    "https://www.who.int/observatories/global-observatory-on-health-research-and-development/"
    "analyses-and-syntheses/who-r-d-blueprint/"
    "who-recommendations-on-vaccine-and-treatment-evaluation"
)
WHO_BLUEPRINT_DOCUMENTS = (
    WHO_BLUEPRINT_HOME,
    WHO_PRIORITY_FRAMEWORK,
    WHO_ROADMAPS,
    WHO_TPPS,
    WHO_TPP_DIRECTORY,
    WHO_TRIAL_PROTOCOLS,
)


@dataclass(frozen=True, slots=True)
class BlueprintProfile:
    key: str
    family: str
    prototype_pathogens: tuple[str, ...]
    match_terms: tuple[str, ...]


# WHO's 2024 family/prototype framework is curated deliberately: fuzzy taxonomic inference would
# create the same class of semantic errors that REDLINE avoids in outbreak extraction.
BLUEPRINT_PROFILES: dict[str, BlueprintProfile] = {
    "filoviruses": BlueprintProfile(
        "filoviruses",
        "Filoviridae",
        ("Orthoebolavirus zairense",),
        (
            "filoviridae",
            "filovirus",
            "filoviruses",
            "ebola",
            "marburg",
            "bundibugyo",
            "sudan virus",
            "orthoebolavirus",
        ),
    ),
    "cchf": BlueprintProfile(
        "cchf",
        "Nairoviridae",
        ("Orthonairovirus haemorrhagiae",),
        ("nairoviridae", "crimean-congo", "crimean congo", "cchf"),
    ),
    "lassa": BlueprintProfile(
        "lassa",
        "Arenaviridae",
        ("Mammarenavirus lassaense",),
        ("arenaviridae", "arenavirus", "arenaviruses", "lassa"),
    ),
    "nipah": BlueprintProfile(
        "nipah",
        "Paramyxoviridae",
        ("Henipavirus nipahense",),
        ("paramyxoviridae", "paramyxovirus", "henipavirus", "nipah"),
    ),
    "mers_sars": BlueprintProfile(
        "mers_sars",
        "Coronaviridae",
        ("Subgenus Merbecovirus", "Subgenus Sarbecovirus"),
        ("coronaviridae", "mers coronavirus", "mers-cov", "mers cov", "sars-cov", "sars cov"),
    ),
    "rift_valley_fever": BlueprintProfile(
        "rift_valley_fever",
        "Phenuiviridae",
        ("Phlebovirus riftense",),
        ("phenuiviridae", "rift valley"),
    ),
    "zika": BlueprintProfile(
        "zika",
        "Flaviviridae",
        ("Orthoflavivirus zikaense",),
        ("flaviviridae", "flavivirus", "zika"),
    ),
    "mpox": BlueprintProfile(
        "mpox",
        "Poxviridae",
        ("Orthopoxvirus monkeypox",),
        ("poxviridae", "poxvirus", "mpox", "monkeypox"),
    ),
    "oropouche": BlueprintProfile(
        "oropouche",
        "Peribunyaviridae",
        ("Orthobunyavirus oropoucheense",),
        ("peribunyaviridae", "oropouche"),
    ),
    "avian_influenza": BlueprintProfile(
        "avian_influenza",
        "Orthomyxoviridae",
        ("Alphainfluenzavirus influenzae H5",),
        ("orthomyxoviridae", "avian influenza", "influenza h5", "h5n1"),
    ),
}


def blueprint_profile(key: str | None) -> BlueprintProfile | None:
    return BLUEPRINT_PROFILES.get(key or "")


def extract_countermeasure_evidence(
    document: SourceDocument,
) -> tuple[CountermeasureEvidence, ...]:
    """Extract only explicitly scoped WHO Blueprint artifacts from a known canonical page."""
    text = " ".join((document.title, document.excerpt, document.original_text)).casefold()
    descriptor = f"{document.title} {document.canonical_url}".casefold()
    profiles = [
        profile
        for profile in BLUEPRINT_PROFILES.values()
        if any(_term_present(text, term) for term in profile.match_terms)
    ]
    url = document.canonical_url.rstrip("/")
    kinds: tuple[str, ...] = ()
    status = "reference"
    if url == WHO_PRIORITY_FRAMEWORK:
        # The publication is the provenance for all curated family/prototype mappings.
        profiles = list(BLUEPRINT_PROFILES.values())
        kinds = ("prototype_pathogen",)
        status = "published"
    elif url == WHO_BLUEPRINT_HOME:
        # The team landing page is discovery input, never product evidence by itself.
        kinds = ()
    elif url == WHO_ROADMAPS:
        kinds = ("roadmap",)
    elif url in {WHO_TPPS, WHO_TPP_DIRECTORY}:
        # Overview pages are provenance/index documents, not evidence that every listed pathogen
        # has every countermeasure type. The adapter emits one child record per explicit TPP/PPC.
        kinds = ()
    elif url == WHO_TRIAL_PROTOCOLS:
        kinds = ("clinical_protocols",)
        status = "published"
    else:
        # Product domains are asserted by the publication title/URL. A roadmap merely mentioning
        # vaccines or diagnostics in its body must not masquerade as those concrete artifacts.
        kinds = _specific_document_kinds(descriptor)
        status = (
            "in_development"
            if kinds and re.search(r"\b(?:draft|consultation|under development)\b", descriptor)
            else "published"
            if kinds
            else "reference"
        )

    records: list[CountermeasureEvidence] = []
    for profile in profiles:
        profile_status = _roadmap_status(text, profile) if url == WHO_ROADMAPS else status
        if url == WHO_ROADMAPS and profile_status is None:
            continue
        for kind in kinds:
            records.append(
                CountermeasureEvidence(
                    pathogen_key=profile.key,
                    pathogen_family=profile.family,
                    kind=kind,
                    label=document.title,
                    url=document.canonical_url,
                    status=profile_status or status,
                    published_at=document.published_at,
                    checked_at=document.fetched_at,
                )
            )
    return tuple(records)


def _term_present(text: str, term: str) -> bool:
    return bool(re.search(rf"(?<!\w){re.escape(term.casefold())}(?!\w)", text))


def _roadmap_status(text: str, profile: BlueprintProfile) -> str | None:
    positions = [text.find(term.casefold()) for term in profile.match_terms]
    position = min((item for item in positions if item >= 0), default=-1)
    if position < 0:
        return None
    developed = text.find("roadmaps are fully developed")
    underway = text.find("development of roadmaps are underway")
    if developed >= 0 and (underway < 0 or developed <= position < underway):
        return "published"
    if underway >= 0 and position >= underway:
        return "in_development"
    return "reference"


def _specific_document_kinds(text: str) -> tuple[str, ...]:
    kinds: list[str] = []
    for kind, terms in {
        "roadmap": ("roadmap",),
        "diagnostics": ("diagnostic",),
        "vaccines": ("vaccine",),
        "therapeutics": ("therapeutic", "treatment"),
        "clinical_protocols": ("clinical protocol", "trial protocol", "core protocol"),
    }.items():
        if any(term in text for term in terms):
            kinds.append(kind)
    return tuple(kinds)
