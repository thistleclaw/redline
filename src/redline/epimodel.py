from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, replace
from typing import Any

import numpy as np

MIN_MODEL_DAYS = 42
MAX_MODEL_DAYS = 3650
MAX_MODEL_LOCATIONS = 12
MAX_MODEL_EVENTS = 40

S, E, A, INF, H, R, V, D, C = range(9)


class ModelInputError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ModelLocation:
    name: str
    latitude: float
    longitude: float
    population: float
    initial_exposed: float
    initial_infectious: float
    initial_recovered_fraction: float
    initial_vaccinated_fraction: float
    daily_importations: float
    travel_weight: float


@dataclass(frozen=True, slots=True)
class ModelIntervention:
    start_day: int
    end_day: int
    transmission_multiplier: float
    mobility_multiplier: float
    vaccination_multiplier: float
    label: str


@dataclass(frozen=True, slots=True)
class ModelSpec:
    title: str
    disease: str
    duration_days: int
    r0: float
    latent_days: float
    infectious_days: float
    asymptomatic_fraction: float
    asymptomatic_relative_infectiousness: float
    hospitalization_fraction: float
    hospital_stay_days: float
    infection_fatality_ratio: float
    immunity_waning_days: float
    vaccine_start_day: int
    vaccination_per_1000_per_day: float
    vaccine_effectiveness: float
    vaccine_waning_days: float
    seasonal_amplitude: float
    seasonal_peak_day: int
    mobility_rate: float
    mobility_distance_km: float
    uncertainty_fraction: float
    locations: tuple[ModelLocation, ...]
    interventions: tuple[ModelIntervention, ...]


@dataclass(frozen=True, slots=True)
class ModelRun:
    title: str
    duration_weeks: int
    events: tuple[dict[str, object], ...]
    summary: str
    ensemble_size: int


@dataclass(frozen=True, slots=True)
class _Trajectory:
    state: np.ndarray
    rt: np.ndarray


def parse_model_spec(raw: object, *, duration_days: int | None = None) -> ModelSpec:
    if not isinstance(raw, dict):
        raise ModelInputError("Model parameters are not an object")
    parameters = raw.get("parameters")
    if not isinstance(parameters, dict):
        raise ModelInputError("Model parameters are missing")
    raw_locations = raw.get("locations")
    if not isinstance(raw_locations, list) or not 1 <= len(raw_locations) <= MAX_MODEL_LOCATIONS:
        raise ModelInputError(f"Model requires 1 to {MAX_MODEL_LOCATIONS} locations")
    locations = tuple(_parse_location(item) for item in raw_locations)
    raw_interventions = raw.get("interventions", [])
    if not isinstance(raw_interventions, list) or len(raw_interventions) > 12:
        raise ModelInputError("Model interventions must be a list of at most 12 items")
    interventions = tuple(_parse_intervention(item) for item in raw_interventions)
    requested_days = duration_days if duration_days is not None else raw.get("duration_days")
    spec = ModelSpec(
        title=_text(raw.get("title"), 120, "Synthetic SEIR scenario"),
        disease=_text(raw.get("disease"), 100, "Synthetic pathogen"),
        duration_days=_integer(requested_days, MIN_MODEL_DAYS, MAX_MODEL_DAYS, "duration_days"),
        r0=_number(parameters.get("r0"), 0.05, 25.0, "r0"),
        latent_days=_number(parameters.get("latent_days"), 0.1, 60.0, "latent_days"),
        infectious_days=_number(parameters.get("infectious_days"), 0.1, 90.0, "infectious_days"),
        asymptomatic_fraction=_number(
            parameters.get("asymptomatic_fraction"), 0.0, 0.99, "asymptomatic_fraction"
        ),
        asymptomatic_relative_infectiousness=_number(
            parameters.get("asymptomatic_relative_infectiousness"),
            0.0,
            2.0,
            "asymptomatic_relative_infectiousness",
        ),
        hospitalization_fraction=_number(
            parameters.get("hospitalization_fraction"),
            0.0,
            0.95,
            "hospitalization_fraction",
        ),
        hospital_stay_days=_number(
            parameters.get("hospital_stay_days"), 0.5, 120.0, "hospital_stay_days"
        ),
        infection_fatality_ratio=_number(
            parameters.get("infection_fatality_ratio"),
            0.0,
            0.95,
            "infection_fatality_ratio",
        ),
        immunity_waning_days=_number(
            parameters.get("immunity_waning_days"), 0.0, 3650.0, "immunity_waning_days"
        ),
        vaccine_start_day=_integer(
            parameters.get("vaccine_start_day"), 0, MAX_MODEL_DAYS, "vaccine_start_day"
        ),
        vaccination_per_1000_per_day=_number(
            parameters.get("vaccination_per_1000_per_day"),
            0.0,
            100.0,
            "vaccination_per_1000_per_day",
        ),
        vaccine_effectiveness=_number(
            parameters.get("vaccine_effectiveness"), 0.0, 1.0, "vaccine_effectiveness"
        ),
        vaccine_waning_days=_number(
            parameters.get("vaccine_waning_days"), 0.0, 3650.0, "vaccine_waning_days"
        ),
        seasonal_amplitude=_number(
            parameters.get("seasonal_amplitude"), -0.5, 0.5, "seasonal_amplitude"
        ),
        seasonal_peak_day=_integer(
            parameters.get("seasonal_peak_day"), 0, 365, "seasonal_peak_day"
        ),
        mobility_rate=_number(parameters.get("mobility_rate"), 0.0, 0.75, "mobility_rate"),
        mobility_distance_km=_number(
            parameters.get("mobility_distance_km"),
            25.0,
            20_000.0,
            "mobility_distance_km",
        ),
        uncertainty_fraction=_number(
            parameters.get("uncertainty_fraction"), 0.0, 0.6, "uncertainty_fraction"
        ),
        locations=locations,
        interventions=interventions,
    )
    _validate_initial_state(spec)
    return spec


def simulate_model(spec: ModelSpec, *, language: str = "en") -> ModelRun:
    base = _simulate(spec)
    ensemble = _simulate_ensemble(spec)
    events = _events_from_trajectory(spec, base, ensemble, language)
    totals = base.state.sum(axis=1)
    active = totals[:, A] + totals[:, INF]
    peak_day = int(np.argmax(active))
    final_cases = float(np.median([item.state[-1, :, C].sum() for item in ensemble]))
    final_deaths = float(np.median([item.state[-1, :, D].sum() for item in ensemble]))
    final_ranges = _final_ranges(ensemble)
    intervention_labels = ", ".join(item.label for item in spec.interventions) or "none"
    if language == "ru":
        summary = (
            f"Локальный NumPy SEAIRHDV · узлов: {len(spec.locations)} · "
            f"R0={spec.r0:.2f} · латентный период={spec.latent_days:.2f} дн. · "
            f"инфекционный период={spec.infectious_days:.2f} дн.\n"
            f"Бессимптомные={spec.asymptomatic_fraction:.1%} (заразность ×"
            f"{spec.asymptomatic_relative_infectiousness:.2f}); "
            f"госпитализация={spec.hospitalization_fraction:.1%}; "
            f"IFR={spec.infection_fatality_ratio:.2%}; мобильность={spec.mobility_rate:.2f}; "
            f"сезонность={spec.seasonal_amplitude:+.2f}; вмешательства: {intervention_labels}.\n"
            f"Пик активных инфекций: день {peak_day}, {_count(active[peak_day])}. "
            f"Медианный итог: {_count(final_cases)} инфекций и {_count(final_deaths)} смертей. "
            f"Ансамбль n={len(ensemble)}: инфекции {final_ranges['cases']}, "
            f"смерти {final_ranges['deaths']} (P10–P90).\n"
            "Это синтетический сценарный расчёт, не прогноз, не PHEIC и не позиция WHO."
        )
    else:
        summary = (
            f"Local NumPy SEAIRHDV · nodes: {len(spec.locations)} · "
            f"R0={spec.r0:.2f} · latent={spec.latent_days:.2f}d · "
            f"infectious={spec.infectious_days:.2f}d\n"
            f"Asymptomatic={spec.asymptomatic_fraction:.1%} (infectivity ×"
            f"{spec.asymptomatic_relative_infectiousness:.2f}); "
            f"hospitalization={spec.hospitalization_fraction:.1%}; "
            f"IFR={spec.infection_fatality_ratio:.2%}; mobility={spec.mobility_rate:.2f}; "
            f"seasonality={spec.seasonal_amplitude:+.2f}; interventions: "
            f"{intervention_labels}.\n"
            f"Peak active infections: day {peak_day}, {_count(active[peak_day])}. "
            f"Median outcome: {_count(final_cases)} infections and {_count(final_deaths)} deaths. "
            f"Ensemble n={len(ensemble)}: infections {final_ranges['cases']}, "
            f"deaths {final_ranges['deaths']} (P10–P90).\n"
            "Synthetic scenario calculation; not a forecast, PHEIC, or WHO position."
        )
    return ModelRun(
        title=spec.title,
        duration_weeks=math.ceil(spec.duration_days / 7),
        events=events,
        summary=summary,
        ensemble_size=len(ensemble),
    )


def _simulate(spec: ModelSpec) -> _Trajectory:
    node_count = len(spec.locations)
    populations = np.array([location.population for location in spec.locations], dtype=float)
    state = np.zeros((spec.duration_days + 1, node_count, 9), dtype=float)
    state[0] = _initial_state(spec, populations)
    rt = np.zeros((spec.duration_days + 1, node_count), dtype=float)
    off_diagonal = _mobility_kernel(spec)
    dt = 0.25
    current = state[0].copy()
    for day in range(spec.duration_days + 1):
        rt[day] = _effective_rt(spec, current, float(day))
        if day == spec.duration_days:
            break
        for substep in range(4):
            time = day + substep * dt
            k1 = _derivative(spec, current, populations, off_diagonal, time)
            k2 = _derivative(
                spec, current + 0.5 * dt * k1, populations, off_diagonal, time + 0.5 * dt
            )
            k3 = _derivative(
                spec, current + 0.5 * dt * k2, populations, off_diagonal, time + 0.5 * dt
            )
            k4 = _derivative(spec, current + dt * k3, populations, off_diagonal, time + dt)
            current = current + dt * (k1 + 2 * k2 + 2 * k3 + k4) / 6
            current = _project_state(current, populations)
        state[day + 1] = current
    return _Trajectory(state=state, rt=rt)


def _derivative(
    spec: ModelSpec,
    state: np.ndarray,
    populations: np.ndarray,
    off_diagonal: np.ndarray,
    day: float,
) -> np.ndarray:
    safe = np.maximum(state, 0.0)
    transmission_factor, mobility_factor, vaccination_factor = _intervention_factors(spec, day)
    seasonal = 1 + spec.seasonal_amplitude * math.cos(
        2 * math.pi * (day - spec.seasonal_peak_day) / 365.0
    )
    weighted_duration = spec.infectious_days * (
        (1 - spec.asymptomatic_fraction)
        + spec.asymptomatic_fraction * spec.asymptomatic_relative_infectiousness
    )
    beta = spec.r0 / max(weighted_duration, 0.01) * seasonal * transmission_factor
    mobility = min(0.95, spec.mobility_rate * mobility_factor)
    mixing = (1 - mobility) * np.eye(len(populations)) + mobility * off_diagonal
    infectious_pressure = (
        safe[:, INF] + spec.asymptomatic_relative_infectiousness * safe[:, A]
    ) / populations
    force = np.maximum(0.0, beta * (mixing @ infectious_pressure))
    infections_s = force * safe[:, S]
    infections_v = force * (1 - spec.vaccine_effectiveness) * safe[:, V]
    imports = np.array([location.daily_importations for location in spec.locations])
    imported = np.minimum(safe[:, S], imports)
    vaccinations = np.zeros_like(populations)
    if day >= spec.vaccine_start_day:
        vaccinations = spec.vaccination_per_1000_per_day * vaccination_factor * populations / 1000.0
        vaccinations = np.minimum(vaccinations, safe[:, S])
    sigma = 1 / spec.latent_days
    gamma = 1 / spec.infectious_days
    eta = 1 / spec.hospital_stay_days
    waning_r = 0.0 if spec.immunity_waning_days <= 0 else 1 / spec.immunity_waning_days
    waning_v = 0.0 if spec.vaccine_waning_days <= 0 else 1 / spec.vaccine_waning_days
    exposed_exit = sigma * safe[:, E]
    asymptomatic_in = spec.asymptomatic_fraction * exposed_exit
    symptomatic_in = (1 - spec.asymptomatic_fraction) * exposed_exit
    asymptomatic_out = gamma * safe[:, A]
    infectious_out = gamma * safe[:, INF]
    hospital_fraction = max(spec.hospitalization_fraction, spec.infection_fatality_ratio)
    hospital_in = hospital_fraction * infectious_out
    direct_recovery = (1 - hospital_fraction) * infectious_out
    hospital_out = eta * safe[:, H]
    hospital_fatality = (
        spec.infection_fatality_ratio / hospital_fraction if hospital_fraction > 0 else 0.0
    )
    deaths = hospital_fatality * hospital_out
    hospital_recovery = hospital_out - deaths
    result = np.zeros_like(state)
    result[:, S] = (
        -infections_s - imported - vaccinations + waning_r * safe[:, R] + waning_v * safe[:, V]
    )
    result[:, E] = infections_s + infections_v + imported - exposed_exit
    result[:, A] = asymptomatic_in - asymptomatic_out
    result[:, INF] = symptomatic_in - infectious_out
    result[:, H] = hospital_in - hospital_out
    result[:, R] = asymptomatic_out + direct_recovery + hospital_recovery - waning_r * safe[:, R]
    result[:, V] = vaccinations - infections_v - waning_v * safe[:, V]
    result[:, D] = deaths
    result[:, C] = infections_s + infections_v + imported
    return result


def _initial_state(spec: ModelSpec, populations: np.ndarray) -> np.ndarray:
    state = np.zeros((len(spec.locations), 9), dtype=float)
    for index, location in enumerate(spec.locations):
        recovered = location.population * location.initial_recovered_fraction
        vaccinated = location.population * location.initial_vaccinated_fraction
        asymptomatic = location.initial_infectious * spec.asymptomatic_fraction
        infectious = location.initial_infectious - asymptomatic
        allocated = location.initial_exposed + asymptomatic + infectious + recovered + vaccinated
        state[index, S] = location.population - allocated
        state[index, E] = location.initial_exposed
        state[index, A] = asymptomatic
        state[index, INF] = infectious
        state[index, R] = recovered
        state[index, V] = vaccinated
        state[index, C] = location.initial_exposed + location.initial_infectious
    return state


def _project_state(state: np.ndarray, populations: np.ndarray) -> np.ndarray:
    projected = np.maximum(state, 0.0)
    projected[:, D] = np.minimum(projected[:, D], populations)
    living = [S, E, A, INF, H, R, V]
    living_total = projected[:, living].sum(axis=1)
    target = populations - projected[:, D]
    scale = np.divide(target, living_total, out=np.ones_like(target), where=living_total > 0)
    projected[:, living] *= scale[:, None]
    projected[:, C] = np.maximum(projected[:, C], 0.0)
    return projected


def _mobility_kernel(spec: ModelSpec) -> np.ndarray:
    count = len(spec.locations)
    if count == 1:
        return np.ones((1, 1))
    latitudes = np.radians([location.latitude for location in spec.locations])
    longitudes = np.radians([location.longitude for location in spec.locations])
    dlat = latitudes[:, None] - latitudes[None, :]
    dlon = longitudes[:, None] - longitudes[None, :]
    haversine = (
        np.sin(dlat / 2) ** 2
        + np.cos(latitudes[:, None]) * np.cos(latitudes[None, :]) * np.sin(dlon / 2) ** 2
    )
    distance = 6371.0 * 2 * np.arcsin(np.sqrt(np.clip(haversine, 0.0, 1.0)))
    weights = np.array([location.travel_weight for location in spec.locations])
    kernel = np.exp(-distance / spec.mobility_distance_km) * weights[None, :]
    np.fill_diagonal(kernel, 0.0)
    row_sum = kernel.sum(axis=1)
    return np.divide(kernel, row_sum[:, None], out=np.eye(count), where=row_sum[:, None] > 0)


def _intervention_factors(spec: ModelSpec, day: float) -> tuple[float, float, float]:
    transmission = mobility = vaccination = 1.0
    for intervention in spec.interventions:
        if intervention.start_day <= day <= intervention.end_day:
            transmission *= intervention.transmission_multiplier
            mobility *= intervention.mobility_multiplier
            vaccination *= intervention.vaccination_multiplier
    return transmission, mobility, vaccination


def _effective_rt(spec: ModelSpec, state: np.ndarray, day: float) -> np.ndarray:
    transmission, _mobility, _vaccination = _intervention_factors(spec, day)
    seasonal = 1 + spec.seasonal_amplitude * math.cos(
        2 * math.pi * (day - spec.seasonal_peak_day) / 365.0
    )
    susceptible = state[:, S] + (1 - spec.vaccine_effectiveness) * state[:, V]
    populations = np.array([location.population for location in spec.locations])
    return np.maximum(0.0, spec.r0 * transmission * seasonal * susceptible / populations)


def _simulate_ensemble(spec: ModelSpec) -> tuple[_Trajectory, ...]:
    if spec.uncertainty_fraction <= 0:
        return (_simulate(spec),)
    work = spec.duration_days * len(spec.locations)
    size = max(8, min(32, 240_000 // max(work, 1)))
    seed_source = json.dumps(_spec_identity(spec), ensure_ascii=True, sort_keys=True)
    seed = int(hashlib.sha256(seed_source.encode()).hexdigest()[:16], 16)
    rng = np.random.default_rng(seed)
    trajectories: list[_Trajectory] = []
    for _index in range(size):
        sigma = spec.uncertainty_fraction

        def multiplier(scale: float = sigma) -> float:
            return float(np.clip(rng.lognormal(0.0, scale), 0.35, 2.5))

        locations = tuple(_perturb_location(location, multiplier) for location in spec.locations)
        sample = replace(
            spec,
            r0=float(np.clip(spec.r0 * multiplier(), 0.05, 25.0)),
            latent_days=float(np.clip(spec.latent_days * multiplier(), 0.1, 60.0)),
            infectious_days=float(np.clip(spec.infectious_days * multiplier(), 0.1, 90.0)),
            locations=locations,
        )
        _validate_initial_state(sample)
        trajectories.append(_simulate(sample))
    return tuple(trajectories)


def _events_from_trajectory(
    spec: ModelSpec,
    trajectory: _Trajectory,
    ensemble: tuple[_Trajectory, ...],
    language: str,
) -> tuple[dict[str, object], ...]:
    total_weeks = math.ceil(spec.duration_days / 7)
    points_per_week = min(3, len(spec.locations))
    sample_count = min(total_weeks + 1, max(2, MAX_MODEL_EVENTS // points_per_week))
    sample_weeks = np.unique(np.rint(np.linspace(0, total_weeks, sample_count)).astype(int))
    events: list[dict[str, object]] = []
    populations = np.array([location.population for location in spec.locations])
    for week in sample_weeks:
        day = min(spec.duration_days, int(week) * 7)
        current = trajectory.state[day]
        active = current[:, A] + current[:, INF]
        affected = active >= np.maximum(1.0, populations / 1_000_000)
        affected_count = int(affected.sum())
        total_active = float(active.sum())
        total_cases = float(current[:, C].sum())
        total_hospital = float(current[:, H].sum())
        total_deaths = float(current[:, D].sum())
        rt = float(np.average(trajectory.rt[day], weights=populations))
        sample_cases = np.array([item.state[day, :, C].sum() for item in ensemble])
        p10, p90 = np.quantile(sample_cases, [0.1, 0.9])
        spread = affected_count > 1
        scope = _scope(spec, affected)
        candidate_indices = np.flatnonzero(affected)
        if len(candidate_indices) == 0:
            candidate_indices = np.array([int(np.argmax(active))])
        selected_indices = candidate_indices[
            np.argsort(active[candidate_indices])[::-1][:points_per_week]
        ]
        for selected in selected_indices:
            location = spec.locations[int(selected)]
            if language == "ru":
                title = f"SEIR неделя {int(week)} // {spec.disease} // {location.name}"
                summary = (
                    f"Локальный расчёт, день {day}: активно {_count(total_active)}, "
                    f"накопленно {_count(total_cases)} (P10–P90: {_count(p10)}–{_count(p90)}), "
                    f"госпитализировано {_count(total_hospital)}, смертей {_count(total_deaths)}, "
                    f"Rt≈{rt:.2f}, затронуто узлов {affected_count}/{len(spec.locations)}."
                    f" Входы: R0={spec.r0:.2f}, L={spec.latent_days:.1f} дн., "
                    f"I={spec.infectious_days:.1f} дн., IFR={spec.infection_fatality_ratio:.2%}."
                )
            else:
                title = f"SEIR week {int(week)} // {spec.disease} // {location.name}"
                summary = (
                    f"Local calculation, day {day}: active {_count(total_active)}, "
                    f"cumulative {_count(total_cases)} (P10–P90: {_count(p10)}–{_count(p90)}), "
                    f"hospitalized {_count(total_hospital)}, deaths {_count(total_deaths)}, "
                    f"Rt≈{rt:.2f}, affected nodes {affected_count}/{len(spec.locations)}."
                    f" Inputs: R0={spec.r0:.2f}, L={spec.latent_days:.1f}d, "
                    f"I={spec.infectious_days:.1f}d, IFR={spec.infection_fatality_ratio:.2%}."
                )
            events.append(
                {
                    "title": title,
                    "disease": spec.disease,
                    "territory": location.name,
                    "latitude": location.latitude,
                    "longitude": location.longitude,
                    "evidence": "potential",
                    "emergency": "none",
                    "summary": summary,
                    "map_status": "spread" if spread else "outbreak",
                    "map_scope": scope,
                    "week": int(week),
                }
            )
    return tuple(events)


def _perturb_location(location: ModelLocation, multiplier: Any) -> ModelLocation:
    exposed = max(0.0, location.initial_exposed * multiplier())
    infectious = max(0.0, location.initial_infectious * multiplier())
    reserved = location.population * (
        location.initial_recovered_fraction + location.initial_vaccinated_fraction
    )
    available = max(0.0, location.population - reserved)
    seeded = exposed + infectious
    if seeded > available and seeded > 0:
        exposed *= available / seeded
        infectious *= available / seeded
    return replace(
        location,
        initial_exposed=exposed,
        initial_infectious=infectious,
        daily_importations=max(0.0, location.daily_importations * multiplier()),
    )


def _scope(spec: ModelSpec, affected: np.ndarray) -> str:
    count = int(affected.sum())
    if count <= 1:
        return "local"
    coordinates = np.array(
        [
            [item.latitude, item.longitude]
            for item, yes in zip(spec.locations, affected, strict=True)
            if yes
        ]
    )
    span = float(np.ptp(coordinates, axis=0).max()) if len(coordinates) else 0.0
    if span > 100 or (coordinates[:, 0].min() < -10 < coordinates[:, 0].max()):
        return "global"
    if span > 35:
        return "continent"
    if span > 8:
        return "region"
    return "country"


def _final_ranges(ensemble: tuple[_Trajectory, ...]) -> dict[str, str]:
    cases = np.array([item.state[-1, :, C].sum() for item in ensemble])
    deaths = np.array([item.state[-1, :, D].sum() for item in ensemble])
    return {
        "cases": "–".join(_count(value) for value in np.quantile(cases, [0.1, 0.9])),
        "deaths": "–".join(_count(value) for value in np.quantile(deaths, [0.1, 0.9])),
    }


def _parse_location(raw: object) -> ModelLocation:
    if not isinstance(raw, dict):
        raise ModelInputError("Location is not an object")
    return ModelLocation(
        name=_text(raw.get("name"), 100, "Synthetic location"),
        latitude=_number(raw.get("latitude"), -90.0, 90.0, "latitude"),
        longitude=_number(raw.get("longitude"), -180.0, 180.0, "longitude"),
        population=_number(raw.get("population"), 100.0, 2_000_000_000.0, "population"),
        initial_exposed=_number(raw.get("initial_exposed"), 0.0, 100_000_000.0, "initial_exposed"),
        initial_infectious=_number(
            raw.get("initial_infectious"), 0.0, 100_000_000.0, "initial_infectious"
        ),
        initial_recovered_fraction=_number(
            raw.get("initial_recovered_fraction"),
            0.0,
            0.99,
            "initial_recovered_fraction",
        ),
        initial_vaccinated_fraction=_number(
            raw.get("initial_vaccinated_fraction"),
            0.0,
            0.99,
            "initial_vaccinated_fraction",
        ),
        daily_importations=_number(
            raw.get("daily_importations"), 0.0, 1_000_000.0, "daily_importations"
        ),
        travel_weight=_number(raw.get("travel_weight"), 0.01, 100.0, "travel_weight"),
    )


def _parse_intervention(raw: object) -> ModelIntervention:
    if not isinstance(raw, dict):
        raise ModelInputError("Intervention is not an object")
    start = _integer(raw.get("start_day"), 0, MAX_MODEL_DAYS, "start_day")
    end = _integer(raw.get("end_day"), start, MAX_MODEL_DAYS, "end_day")
    return ModelIntervention(
        start_day=start,
        end_day=end,
        transmission_multiplier=_number(
            raw.get("transmission_multiplier"), 0.05, 3.0, "transmission_multiplier"
        ),
        mobility_multiplier=_number(
            raw.get("mobility_multiplier"), 0.0, 3.0, "mobility_multiplier"
        ),
        vaccination_multiplier=_number(
            raw.get("vaccination_multiplier"), 0.0, 10.0, "vaccination_multiplier"
        ),
        label=_text(raw.get("label"), 100, "Intervention"),
    )


def _validate_initial_state(spec: ModelSpec) -> None:
    total_seed = 0.0
    for location in spec.locations:
        allocated = (
            location.initial_exposed
            + location.initial_infectious
            + location.population
            * (location.initial_recovered_fraction + location.initial_vaccinated_fraction)
        )
        if allocated > location.population:
            raise ModelInputError(f"Initial compartments exceed population in {location.name}")
        total_seed += (
            location.initial_exposed + location.initial_infectious + location.daily_importations
        )
    if total_seed <= 0:
        raise ModelInputError("Model needs an initial exposure, infection, or importation")


def _spec_identity(spec: ModelSpec) -> dict[str, Any]:
    return {
        "title": spec.title,
        "disease": spec.disease,
        "duration": spec.duration_days,
        "r0": spec.r0,
        "locations": [
            [item.name, item.population, item.initial_exposed, item.initial_infectious]
            for item in spec.locations
        ],
    }


def _text(value: object, limit: int, fallback: str) -> str:
    return " ".join(str(value or fallback).split())[:limit] or fallback


def _number(value: object, minimum: float, maximum: float, name: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise ModelInputError(f"{name} is not numeric") from error
    if not math.isfinite(result) or not minimum <= result <= maximum:
        raise ModelInputError(f"{name} must be between {minimum:g} and {maximum:g}")
    return result


def _integer(value: object, minimum: int, maximum: int, name: str) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError) as error:
        raise ModelInputError(f"{name} is not an integer") from error
    if not minimum <= result <= maximum:
        raise ModelInputError(f"{name} must be between {minimum} and {maximum}")
    return result


def _count(value: float) -> str:
    rounded = int(round(float(value)))
    if rounded >= 1_000_000_000:
        return f"{rounded / 1_000_000_000:.2f}B"
    if rounded >= 1_000_000:
        return f"{rounded / 1_000_000:.2f}M"
    if rounded >= 1_000:
        return f"{rounded / 1_000:.1f}K"
    return str(max(0, rounded))
