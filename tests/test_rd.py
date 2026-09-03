from dataclasses import replace

from redline.rd import (
    WHO_PRIORITY_FRAMEWORK,
    WHO_ROADMAPS,
    WHO_TPP_DIRECTORY,
    extract_countermeasure_evidence,
)


def test_priority_framework_provides_curated_family_and_prototype_provenance(document):
    framework = replace(
        document,
        source_id="who_blueprint",
        canonical_url=WHO_PRIORITY_FRAMEWORK,
        title="Pathogens prioritization: a scientific framework",
        category="rd_blueprint",
    )

    records = extract_countermeasure_evidence(framework)
    filovirus = next(record for record in records if record.pathogen_key == "filoviruses")

    assert filovirus.pathogen_family == "Filoviridae"
    assert filovirus.kind == "prototype_pathogen"
    assert filovirus.status == "published"
    assert filovirus.url == WHO_PRIORITY_FRAMEWORK


def test_roadmap_status_is_scoped_to_the_correct_who_section(document):
    roadmap = replace(
        document,
        source_id="who_blueprint",
        canonical_url=WHO_ROADMAPS,
        title="WHO R&D roadmaps",
        original_text=(
            "Roadmaps are fully developed for Ebola and Marburg, Lassa fever and Nipah. "
            "Development of roadmaps are underway for Zika and Rift Valley fever."
        ),
        excerpt="WHO roadmap status by priority pathogen.",
        category="rd_blueprint",
    )

    records = extract_countermeasure_evidence(roadmap)
    statuses = {record.pathogen_key: record.status for record in records}

    assert statuses["filoviruses"] == "published"
    assert statuses["lassa"] == "published"
    assert statuses["nipah"] == "published"
    assert statuses["zika"] == "in_development"
    assert statuses["rift_valley_fever"] == "in_development"


def test_tpp_directory_overview_does_not_cross_assign_product_types(document):
    directory = replace(
        document,
        source_id="who_blueprint",
        canonical_url=WHO_TPP_DIRECTORY,
        title="Links to WHO TPPs and PPCs",
        original_text="MERS vaccines. Zika vaccines. Zika diagnostics.",
        excerpt="WHO TPP directory.",
        category="rd_blueprint",
    )
    mers_vaccine = replace(
        directory,
        canonical_url="https://www.who.int/publications/m/item/mers-vaccine-tpp",
        title="WHO MERS coronavirus vaccines TPP",
        original_text="WHO MERS coronavirus vaccines TPP",
        excerpt="WHO MERS coronavirus vaccines TPP",
    )

    assert extract_countermeasure_evidence(directory) == ()
    records = extract_countermeasure_evidence(mers_vaccine)
    assert [(record.pathogen_key, record.kind) for record in records] == [("mers_sars", "vaccines")]


def test_family_roadmap_does_not_claim_each_domain_mentioned_in_its_body(document):
    roadmap = replace(
        document,
        source_id="who_blueprint",
        canonical_url="https://www.who.int/publications/m/item/filovirus-roadmap",
        title="Filovirus research and development roadmap",
        original_text="Priorities include diagnostics, vaccines, therapeutics and CORE protocols.",
        excerpt="Filovirus research priorities.",
        category="rd_blueprint",
    )

    records = extract_countermeasure_evidence(roadmap)

    assert {record.kind for record in records} == {"roadmap"}
    assert {record.status for record in records} == {"published"}
