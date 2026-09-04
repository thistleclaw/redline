from __future__ import annotations

import json
from dataclasses import replace

import pytest

from redline.ai import GeminiResult
from redline.config import Config
from redline.database import Database
from redline.models import CountermeasureEvidence
from redline.ui import (
    CommandSuggester,
    RedlineApp,
    markdown_to_plain_text,
    parse_timelapse_duration,
)


class FakeGemini:
    configured = True

    async def generate(self, prompt, *, system_instruction, response_schema=None):
        if response_schema is not None:
            if "SEIR MODEL" in prompt:
                return GeminiResult(
                    json.dumps(
                        {
                            "title": "Synthetic local model",
                            "disease": "Anthrax",
                            "duration_days": 84,
                            "rationale": "Synthetic UI fixture",
                            "parameters": {
                                "r0": 1.8,
                                "latent_days": 3.0,
                                "infectious_days": 7.0,
                                "asymptomatic_fraction": 0.0,
                                "asymptomatic_relative_infectiousness": 0.0,
                                "hospitalization_fraction": 0.2,
                                "hospital_stay_days": 10.0,
                                "infection_fatality_ratio": 0.05,
                                "immunity_waning_days": 0.0,
                                "vaccine_start_day": 30,
                                "vaccination_per_1000_per_day": 0.0,
                                "vaccine_effectiveness": 0.0,
                                "vaccine_waning_days": 0.0,
                                "seasonal_amplitude": 0.0,
                                "seasonal_peak_day": 0,
                                "mobility_rate": 0.1,
                                "mobility_distance_km": 2000.0,
                                "uncertainty_fraction": 0.0,
                            },
                            "locations": [
                                {
                                    "name": "Eurasia test node",
                                    "latitude": 50.0,
                                    "longitude": 50.0,
                                    "population": 1_000_000,
                                    "initial_exposed": 30,
                                    "initial_infectious": 5,
                                    "initial_recovered_fraction": 0.0,
                                    "initial_vaccinated_fraction": 0.0,
                                    "daily_importations": 0.0,
                                    "travel_weight": 1.0,
                                }
                            ],
                            "interventions": [],
                        }
                    ),
                    "gemini-3.5-flash-lite",
                )
            if "TIMELAPSE" in prompt:
                return GeminiResult(
                    json.dumps(
                        {
                            "title": "Synthetic weekly spread",
                            "duration_weeks": 2,
                            "events": [
                                {
                                    "title": f"Synthetic weekly outbreak {index}",
                                    "disease": "Anthrax",
                                    "territory": f"Eurasia sector {index}",
                                    "latitude": 45.0 + index,
                                    "longitude": 40.0 + index * 10,
                                    "evidence": "confirmed",
                                    "emergency": "regional",
                                    "summary": "Synthetic weekly test data only.",
                                    "week": index // 2,
                                }
                                for index in range(6)
                            ],
                        }
                    ),
                    "gemini-3.5-flash-lite",
                )
            return GeminiResult(
                json.dumps(
                    {
                        "title": "Synthetic anthrax scenario",
                        "events": [
                            {
                                "title": f"Synthetic anthrax outbreak {index}",
                                "disease": "Anthrax",
                                "territory": f"Eurasia sector {index}",
                                "latitude": 45.0 + index,
                                "longitude": 50.0 + index * 20,
                                "evidence": "confirmed",
                                "emergency": "regional",
                                "summary": "Synthetic test data only.",
                            }
                            for index in range(3)
                        ],
                    }
                ),
                "gemini-3.5-flash-lite",
            )
        assert "MONITOR_CONTEXT" in prompt
        return GeminiResult(
            "## Context **answer**\n- [WHO](https://who.int/source_path)",
            "gemini-3.5-flash-lite",
        )


class RecordingGemini:
    configured = True

    def __init__(self):
        self.requests = []

    async def generate(self, prompt, *, system_instruction, response_schema=None):
        self.requests.append((prompt, system_instruction, response_schema))
        return GeminiResult("Conditional scenario output", "gemini-3.5-flash-lite")


def test_crt_tick_is_safe_before_widgets_mount() -> None:
    app = RedlineApp(config=Config(crt_effects=True, translation_enabled=False))

    app.tick_crt()


@pytest.mark.asyncio
async def test_initialized_tui_starts_background_sync(tmp_path):
    calls = []
    app = RedlineApp(
        config=Config(initialized=True, crt_effects=False, translation_enabled=False),
        database=Database(tmp_path / "redline.sqlite3"),
        auto_sync=True,
    )
    app.run_sync = lambda **kwargs: calls.append(kwargs)

    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()

    assert calls == [{"force": False, "retry_failed": True}]


@pytest.mark.parametrize(
    ("value", "weeks"),
    [("90d", 13), ("26w", 26), ("18m", 78), ("3y", 156), ("10y", 520)],
)
def test_timelapse_duration_units(value, weeks):
    assert parse_timelapse_duration(value) == weeks


def test_gemini_markdown_is_converted_to_terminal_plain_text():
    source = "# Heading\n\n- **Alert** from [WHO](https://who.int/a_b)\n`code` and _note_."

    result = markdown_to_plain_text(source)

    assert result == "Heading\n\n• Alert from WHO (https://who.int/a_b)\ncode and note."


@pytest.mark.asyncio
async def test_forecast_autocomplete_exposes_concrete_argument_values():
    suggester = CommandSuggester()

    assert await suggester.get_suggestion(":forecast ai b") == ":forecast ai bad"
    assert await suggester.get_suggestion(":forecast ai g") == ":forecast ai good"


@pytest.mark.asyncio
async def test_exit_command_closes_the_tui(tmp_path):
    app = RedlineApp(
        config=Config(initialized=True, crt_effects=False, translation_enabled=False),
        database=Database(tmp_path / "redline.sqlite3"),
    )

    async with app.run_test(size=(150, 45)) as pilot:
        app.execute_command(":exit")
        await pilot.pause()
        assert app._exit is True

    assert app.return_value is None
    assert app.is_running is False


@pytest.mark.asyncio
@pytest.mark.parametrize("terminal_size", [(96, 28), (120, 40), (160, 45), (200, 55)])
async def test_braille_map_rescales_at_supported_terminal_sizes(tmp_path, terminal_size):
    terminal_width, terminal_height = terminal_size
    database = Database(tmp_path / f"redline-{terminal_width}-{terminal_height}.sqlite3")
    config = Config(initialized=True, crt_effects=False, translation_enabled=False)
    app = RedlineApp(config=config, database=database)

    async with app.run_test(size=terminal_size) as pilot:
        await pilot.pause()
        map_widget = app.query_one("#braille-map")
        lines = map_widget.renderable.plain.splitlines()

        assert lines
        assert len(lines) == map_widget.size.height
        assert all(len(line) == map_widget.size.width for line in lines)
        assert any(
            label in app.query_one("#map-title").renderable.plain
            for label in ("БЕРЕГОВАЯ ЛИНИЯ", "СУША")
        )


@pytest.mark.asyncio
async def test_braille_map_reflows_after_live_terminal_resize(tmp_path):
    app = RedlineApp(
        config=Config(initialized=True, crt_effects=False, translation_enabled=False),
        database=Database(tmp_path / "redline.sqlite3"),
    )

    async with app.run_test(size=(160, 45)) as pilot:
        initial_width = app.query_one("#braille-map").size.width
        await pilot.resize_terminal(108, 30)
        await pilot.pause()
        map_widget = app.query_one("#braille-map")
        lines = map_widget.renderable.plain.splitlines()

        assert map_widget.size.width < initial_width
        assert len(lines) == map_widget.size.height
        assert all(len(line) == map_widget.size.width for line in lines)


@pytest.mark.asyncio
async def test_portrait_terminal_places_map_above_side_by_side_information_panels(tmp_path):
    app = RedlineApp(
        config=Config(initialized=True, crt_effects=False, translation_enabled=False),
        database=Database(tmp_path / "redline.sqlite3"),
    )

    async with app.run_test(size=(58, 44)) as pilot:
        await pilot.pause()
        map_panel = app.query_one("#map-panel")
        right_panel = app.query_one("#right-panel")
        feed_box = app.query_one("#feed-box")
        detail_box = app.query_one("#detail-box")

        assert app.portrait_layout is True
        assert map_panel.region.width == right_panel.region.width
        assert map_panel.region.y < right_panel.region.y
        assert feed_box.region.y == detail_box.region.y
        assert feed_box.region.x < detail_box.region.x
        assert app.query_one("#notice").display is False
        assert "PHEIC:" in app.query_one("#topline").renderable.plain
        assert "ALERT:" in app.query_one("#topline").renderable.plain
        assert "ВЫМ." in app.query_one("#map-title").renderable.plain

        await pilot.resize_terminal(140, 35)
        await pilot.pause()
        assert app.portrait_layout is False
        assert map_panel.region.y == right_panel.region.y
        assert feed_box.region.x == detail_box.region.x
        assert feed_box.region.y < detail_box.region.y
        assert app.query_one("#notice").display is True


@pytest.mark.asyncio
async def test_first_run_setup_fits_a_narrow_termux_screen(tmp_path):
    app = RedlineApp(
        config=Config(initialized=False, crt_effects=False, translation_enabled=False),
        database=Database(tmp_path / "redline.sqlite3"),
    )

    async with app.run_test(size=(48, 32)) as pilot:
        await pilot.pause()
        setup = app.screen.query_one("#setup")
        assert setup.region.width <= app.screen.region.width
        assert setup.region.height <= app.screen.region.height


@pytest.mark.asyncio
async def test_touch_selects_wrapped_feed_event_and_activates_panels(tmp_path, document, event):
    database = Database(tmp_path / "redline.sqlite3")
    for index in range(2):
        current_document = replace(
            document,
            canonical_url=f"{document.canonical_url}-touch-{index}",
            content_hash=f"touch-document-{index}",
            title=(
                f"Touch {index}: deliberately long official event title "
                "that wraps inside a portrait feed panel"
            ),
        )
        document_id, _ = database.save_document(current_document)
        database.save_event(
            replace(
                event,
                event_id=f"touch-event-{index}",
                document_url=current_document.canonical_url,
                situation_key=f"touch-situation-{index}",
            ),
            document_id,
        )
    app = RedlineApp(
        config=Config(initialized=True, crt_effects=False, translation_enabled=False),
        database=database,
    )

    async with app.run_test(size=(80, 45)) as pilot:
        await pilot.pause()
        app.selected_index = 1
        app.refresh_view()
        await pilot.pause()
        assert await pilot.click("#event-feed", offset=(2, 1))
        await pilot.pause()
        assert app.selected_index == 0
        assert app.active_tui_field == "feed"

        assert await pilot.click("#detail-title", offset=(1, 0))
        await pilot.pause()
        assert app.active_tui_field == "details"

        assert await pilot.click("#command-input", offset=(1, 0))
        await pilot.pause()
        assert app.active_tui_field == "command"
        assert app.query_one("#command-input").has_focus


@pytest.mark.asyncio
async def test_tui_renders_map_commands_and_export(tmp_path, document, event):
    database = Database(tmp_path / "redline.sqlite3")
    document_id, _ = database.save_document(document)
    database.save_event(event, document_id)
    config = Config(initialized=True, crt_effects=False, translation_enabled=False)
    app = RedlineApp(config=config, database=database)
    export_path = tmp_path / "events.json"
    async with app.run_test(size=(150, 45)) as pilot:
        await pilot.pause()
        assert "REDLINE" in app.query_one("#topline").renderable.plain
        map_text = app.query_one("#braille-map").renderable
        assert any("\u2800" <= character <= "\u28ff" for character in map_text.plain)
        assert any("#ff334f" in str(span.style) for span in map_text.spans)
        app.execute_command(":focus africa")
        assert app.focus == "africa"
        app.execute_command(f":export json {export_path}")
        assert export_path.exists()


@pytest.mark.asyncio
async def test_inspector_links_outbreak_to_structured_blueprint_profile(tmp_path, document, event):
    database = Database(tmp_path / "redline.sqlite3")
    event_document_id, _ = database.save_document(document)
    database.save_event(event, event_document_id)
    rd_document = replace(
        document,
        source_id="who_blueprint",
        canonical_url="https://www.who.int/publications/m/item/filovirus-roadmap",
        content_hash="filovirus-roadmap",
        title="Filovirus research and development roadmap",
        category="rd_blueprint",
    )
    rd_document_id, _ = database.save_document(rd_document)
    database.save_countermeasure_evidence(
        CountermeasureEvidence(
            pathogen_key="filoviruses",
            pathogen_family="Filoviridae",
            kind="roadmap",
            label=rd_document.title,
            url=rd_document.canonical_url,
            status="published",
            published_at=rd_document.published_at,
            checked_at=rd_document.fetched_at,
        ),
        rd_document_id,
    )
    app = RedlineApp(
        config=Config(
            initialized=True, language="ru", crt_effects=False, translation_enabled=False
        ),
        database=database,
    )

    async with app.run_test(size=(150, 45)) as pilot:
        await pilot.pause()
        inspector = app.query_one("#details").renderable.plain

        assert "R&D BLUEPRINT // профиль контрмер WHO" in inspector
        assert "Семейство: Filoviridae" in inspector
        assert "Прототип: Orthoebolavirus zairense" in inspector
        assert "Roadmap: [ОПУБЛИКОВАНО] Filovirus research" in inspector
        assert "Диагностика: —" in inspector


@pytest.mark.asyncio
async def test_language_command_localizes_ui_and_source_text(
    tmp_path, document, event, monkeypatch
):
    database = Database(tmp_path / "redline.sqlite3")
    document_id, _ = database.save_document(document)
    database.save_event(event, document_id)
    config = Config(initialized=True, language="ru", crt_effects=False, translation_enabled=False)
    monkeypatch.setattr(Config, "save", lambda self, path=None: tmp_path / "config.toml")
    app = RedlineApp(config=config, database=database)

    async with app.run_test(size=(150, 45)) as pilot:
        await pilot.pause()
        app.execute_command(":language en")

        assert config.language == "en"
        assert str(app.query_one("#feed-title").renderable) == "EVENT FEED"
        assert any(
            label in app.query_one("#map-title").renderable.plain for label in ("COASTLINE", "LAND")
        )
        assert document.title in app.query_one("#event-feed").renderable.plain


@pytest.mark.asyncio
async def test_test_mode_is_isolated_and_ai_scenario_command_populates_it(
    tmp_path, document, event
):
    database = Database(tmp_path / "redline.sqlite3")
    document_id, _ = database.save_document(document)
    database.save_event(event, document_id)
    config = Config(initialized=True, crt_effects=False, translation_enabled=False)
    app = RedlineApp(config=config, database=database, gemini_client=FakeGemini())

    async with app.run_test(size=(150, 45)) as pilot:
        await pilot.pause()
        app.execute_command(":test")
        assert app.test_mode
        assert app.database.events() == []

        app.execute_command(":test ai глобальная эпидемия сибирской язвы в Евразии")
        await app.workers.wait_for_complete()
        assert len(app.database.events()) == 3
        assert "Synthetic anthrax" in app.query_one("#event-feed").renderable.plain

        app.execute_command(":test off")
        assert not app.test_mode
        assert app.database.events()[0]["event_id"] == event.event_id


@pytest.mark.asyncio
async def test_ask_ai_command_uses_monitor_context(tmp_path):
    app = RedlineApp(
        config=Config(initialized=True, crt_effects=False, translation_enabled=False),
        database=Database(tmp_path / "redline.sqlite3"),
        gemini_client=FakeGemini(),
    )

    async with app.run_test(size=(150, 45)) as pilot:
        await pilot.pause()
        app.execute_command(":ask ai what is active")
        await app.workers.wait_for_complete()

        details = app.query_one("#details").renderable.plain
        assert "Context answer" in details
        assert "gemini-3.5-flash-lite" in details
        assert "**" not in details
        assert "[WHO]" not in details
        assert "https://who.int/source_path" in details

        await pilot.resize_terminal(130, 35)
        await pilot.pause()
        assert "Context answer" in app.query_one("#details").renderable.plain


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("direction", "trajectory", "heading"),
    [
        ("bad", "adverse", "НЕБЛАГОПРИЯТНЫЙ СЦЕНАРИЙ"),
        ("good", "favourable", "БЛАГОПРИЯТНЫЙ СЦЕНАРИЙ"),
    ],
)
async def test_forecast_ai_builds_a_labelled_conditional_scenario(
    tmp_path, direction, trajectory, heading
):
    gemini = RecordingGemini()
    app = RedlineApp(
        config=Config(initialized=True, language="ru", crt_effects=False),
        database=Database(tmp_path / f"redline-{direction}.sqlite3"),
        gemini_client=gemini,
    )

    async with app.run_test(size=(150, 45)):
        app.execute_command(f":forecast ai {direction}")
        await app.workers.wait_for_complete()

        prompt, system, schema = gemini.requests[0]
        assert trajectory in prompt
        assert trajectory in system
        assert "MONITOR_CONTEXT" in prompt
        assert "not a prediction" in system
        assert schema is None
        details = app.query_one("#details").renderable.plain
        assert heading in details
        assert "НЕ ПРОГНОЗ WHO" in details
        assert "Conditional scenario output" in details


@pytest.mark.asyncio
async def test_forecast_command_rejects_an_unknown_direction(tmp_path):
    gemini = RecordingGemini()
    app = RedlineApp(
        config=Config(initialized=True, language="ru", crt_effects=False),
        database=Database(tmp_path / "redline.sqlite3"),
        gemini_client=gemini,
    )

    async with app.run_test(size=(120, 35)):
        app.execute_command(":forecast ai neutral")
        assert "Использование: :forecast ai <bad|good>" in str(
            app.query_one("#details").renderable
        )
        assert gemini.requests == []


@pytest.mark.asyncio
async def test_page_keys_navigate_panels_and_command_input(tmp_path):
    app = RedlineApp(
        config=Config(initialized=True, crt_effects=False, translation_enabled=False),
        database=Database(tmp_path / "redline.sqlite3"),
    )

    async with app.run_test(size=(120, 30)) as pilot:
        details = app.query_one("#details")
        detail_scroll = app.query_one("#detail-scroll")
        details.update("\n".join(f"Inspector line {index}" for index in range(100)))
        app.viewer_open = True
        app.action_activate_inspector()
        await pilot.pause()

        await pilot.press("down")
        await pilot.pause()
        assert detail_scroll.scroll_y > 0

        await pilot.press("pageup")
        assert app.active_right_panel == "feed"
        await pilot.press("pagedown")
        assert app.active_right_panel == "details"
        await pilot.press("pagedown")
        command = app.query_one("#command-input")
        assert app.active_tui_field == "command"
        assert command.has_focus
        await pilot.press("pageup")
        assert app.active_tui_field == "details"
        assert not command.has_focus


@pytest.mark.asyncio
async def test_command_prompt_and_input_share_the_same_row(tmp_path):
    app = RedlineApp(
        config=Config(initialized=True, crt_effects=False, translation_enabled=False),
        database=Database(tmp_path / "redline.sqlite3"),
    )

    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        label = app.query_one("#command-label")
        command = app.query_one("#command-input")
        assert label.region.y == command.region.y
        assert label.region.height == command.region.height == 1


@pytest.mark.asyncio
async def test_command_history_uses_arrows_and_persists_between_runs(tmp_path):
    history_path = tmp_path / "command_history"
    app = RedlineApp(
        config=Config(initialized=True, crt_effects=False, translation_enabled=False),
        database=Database(tmp_path / "first.sqlite3"),
        command_history_path=history_path,
    )

    async with app.run_test(size=(120, 30)) as pilot:
        app.action_next_field()
        command = app.query_one("#command-input")
        command.value = ":help"
        await pilot.press("enter")
        app.action_next_field()
        command.value = ":history 30"
        await pilot.press("enter")
        app.action_next_field()
        command.value = ":unfinished draft"

        await pilot.press("up")
        assert command.value == ":history 30"
        await pilot.press("up")
        assert command.value == ":help"
        await pilot.press("down")
        assert command.value == ":history 30"
        await pilot.press("down")
        assert command.value == ":unfinished draft"

    restored = RedlineApp(
        config=Config(initialized=True, crt_effects=False, translation_enabled=False),
        database=Database(tmp_path / "second.sqlite3"),
        command_history_path=history_path,
    )
    assert restored.command_history == [":help", ":history 30"]
    assert history_path.stat().st_mode & 0o777 == 0o600
    restored.live_database.close()


@pytest.mark.asyncio
async def test_auth_command_opens_masked_editor_and_saves_without_restart(tmp_path, monkeypatch):
    saved: list[str] = []
    monkeypatch.setattr("redline.ui.save_gemini_api_key", lambda value: saved.append(value))
    app = RedlineApp(
        config=Config(initialized=True, crt_effects=False, translation_enabled=False),
        database=Database(tmp_path / "redline.sqlite3"),
        gemini_client=FakeGemini(),
    )

    async with app.run_test(size=(150, 45)) as pilot:
        app.execute_command(":auth")
        await pilot.pause()
        key_input = app.screen.query_one("#auth-key")
        assert key_input.password
        key_input.value = "test-ui-gemini-secret"
        key_input.focus()
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

        assert saved == ["test-ui-gemini-secret"]
        assert "ключ сохранён" in app.query_one("#details").renderable


@pytest.mark.asyncio
async def test_down_arrow_moves_exactly_one_event(tmp_path, document, event):
    database = Database(tmp_path / "redline.sqlite3")
    for index in range(3):
        current_document = replace(
            document,
            canonical_url=f"{document.canonical_url}-{index}",
            content_hash=f"document-hash-{index}",
            title=f"Event document {index}",
        )
        document_id, _ = database.save_document(current_document)
        database.save_event(
            replace(
                event,
                event_id=f"event-{index}",
                document_url=current_document.canonical_url,
                situation_key=f"situation-{index}",
            ),
            document_id,
        )
    app = RedlineApp(
        config=Config(initialized=True, crt_effects=False, translation_enabled=False),
        database=database,
    )

    async with app.run_test(size=(150, 45)) as pilot:
        assert app.selected_index == 0
        await pilot.press("pageup")
        await pilot.press("down")
        await pilot.pause()
        assert app.selected_index == 1


@pytest.mark.asyncio
async def test_ai_timelapse_reveals_events_week_by_week(tmp_path, document, event):
    live_database = Database(tmp_path / "redline.sqlite3")
    document_id, _ = live_database.save_document(document)
    live_database.save_event(event, document_id)
    app = RedlineApp(
        config=Config(initialized=True, crt_effects=False, translation_enabled=False),
        database=live_database,
        gemini_client=FakeGemini(),
    )

    async with app.run_test(size=(150, 45)):
        app.execute_command(":test ai timelapse speed=1w/60s вспышка в Евразии")
        await app.workers.wait_for_complete()

        assert app.test_mode
        assert app.timelapse_week == 0
        assert len(app.database.events()) == 2

        app.execute_command(":test pause")
        app.execute_command(":test step")

        assert app.timelapse_week == 1
        assert len(app.database.events()) == 4
        assert "неделя 1/2" in app.query_one("#details").renderable

        app.execute_command(":test off")
        assert len(app.database.events()) == 1


@pytest.mark.asyncio
async def test_ai_timelapse_command_accepts_duration_and_speed_in_any_order(tmp_path):
    app = RedlineApp(
        config=Config(initialized=True, crt_effects=False, translation_enabled=False),
        database=Database(tmp_path / "redline.sqlite3"),
        gemini_client=FakeGemini(),
    )

    async with app.run_test(size=(150, 45)):
        app.execute_command(":test ai timelapse duration=3y speed=2w/60s глобальная эпидемия")
        await app.workers.wait_for_complete()

        assert app.timelapse is not None
        assert app.timelapse.duration_weeks == 156
        assert app.timelapse_step_weeks == 2


@pytest.mark.asyncio
async def test_ai_model_command_calculates_local_events_and_enters_test_mode(tmp_path):
    app = RedlineApp(
        config=Config(initialized=True, crt_effects=False, translation_enabled=False),
        database=Database(tmp_path / "redline.sqlite3"),
        gemini_client=FakeGemini(),
    )

    async with app.run_test(size=(150, 45)):
        app.execute_command(":test ai model duration=20w speed=2w/60s эпидемия в Евразии")
        await app.workers.wait_for_complete()

        assert app.test_mode
        assert app.timelapse is not None
        assert app.timelapse.engine == "numpy_seir"
        assert app.timelapse.duration_weeks == 20
        assert app.timelapse_step_weeks == 2
        assert app.database.events()[0]["source_id"] == "redline_test_model"
        assert "не прогноз" in app.query_one("#details").renderable
