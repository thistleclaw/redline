from __future__ import annotations

from copy import deepcopy

import pytest

from redline.epimodel import C, ModelInputError, _simulate, parse_model_spec, simulate_model


def model_payload() -> dict:
    return {
        "title": "Two-node synthetic epidemic",
        "disease": "Test virus",
        "duration_days": 84,
        "rationale": "Synthetic fixture",
        "parameters": {
            "r0": 2.4,
            "latent_days": 4.0,
            "infectious_days": 6.0,
            "asymptomatic_fraction": 0.25,
            "asymptomatic_relative_infectiousness": 0.6,
            "hospitalization_fraction": 0.08,
            "hospital_stay_days": 9.0,
            "infection_fatality_ratio": 0.01,
            "immunity_waning_days": 0.0,
            "vaccine_start_day": 28,
            "vaccination_per_1000_per_day": 2.0,
            "vaccine_effectiveness": 0.8,
            "vaccine_waning_days": 0.0,
            "seasonal_amplitude": 0.1,
            "seasonal_peak_day": 20,
            "mobility_rate": 0.12,
            "mobility_distance_km": 2500.0,
            "uncertainty_fraction": 0.12,
        },
        "locations": [
            {
                "name": "West",
                "latitude": 50.0,
                "longitude": 20.0,
                "population": 1_000_000,
                "initial_exposed": 40,
                "initial_infectious": 10,
                "initial_recovered_fraction": 0.0,
                "initial_vaccinated_fraction": 0.0,
                "daily_importations": 0.0,
                "travel_weight": 1.0,
            },
            {
                "name": "East",
                "latitude": 50.0,
                "longitude": 60.0,
                "population": 2_000_000,
                "initial_exposed": 0,
                "initial_infectious": 0,
                "initial_recovered_fraction": 0.0,
                "initial_vaccinated_fraction": 0.0,
                "daily_importations": 0.0,
                "travel_weight": 1.0,
            },
        ],
        "interventions": [
            {
                "start_day": 35,
                "end_day": 70,
                "transmission_multiplier": 0.65,
                "mobility_multiplier": 0.4,
                "vaccination_multiplier": 1.5,
                "label": "Synthetic controls",
            }
        ],
    }


def test_numpy_model_is_reproducible_and_never_marks_epidemic_decline_as_extinction():
    spec = parse_model_spec(model_payload())

    first = simulate_model(spec, language="en")
    second = simulate_model(spec, language="en")

    assert first.events == second.events
    assert first.summary == second.summary
    assert first.ensemble_size >= 8
    assert first.duration_weeks == 12
    assert {event["map_status"] for event in first.events} <= {"outbreak", "spread"}
    assert all(event["emergency"] == "none" for event in first.events)
    assert any(event["map_status"] == "spread" for event in first.events)
    assert "P10–P90" in first.summary


def test_duration_override_and_strict_population_validation():
    payload = model_payload()
    spec = parse_model_spec(payload, duration_days=140)
    assert spec.duration_days == 140

    invalid = deepcopy(payload)
    invalid["locations"][0]["initial_recovered_fraction"] = 0.99
    invalid["locations"][0]["initial_vaccinated_fraction"] = 0.5
    with pytest.raises(ModelInputError, match="exceed population"):
        parse_model_spec(invalid)


def test_interventions_reduce_the_calculated_burden():
    controlled = model_payload()
    controlled["parameters"]["uncertainty_fraction"] = 0.0
    uncontrolled = deepcopy(controlled)
    uncontrolled["interventions"] = []

    controlled_run = _simulate(parse_model_spec(controlled))
    uncontrolled_run = _simulate(parse_model_spec(uncontrolled))

    controlled_final = controlled_run.state[-1, :, C].sum()
    uncontrolled_final = uncontrolled_run.state[-1, :, C].sum()
    assert controlled_final < uncontrolled_final
