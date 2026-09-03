from __future__ import annotations

SUPPORTED_LANGUAGES = ("ru", "en")

TEXT: dict[str, dict[str, str]] = {
    "setup.title": {"ru": "REDLINE / первичная настройка", "en": "REDLINE / initial setup"},
    "setup.note": {
        "ru": "Данные, журнал и настройки хранятся локально. Google Translate получает заголовки и выдержки, когда перевод включён. Gemini получает контекст только после явной AI-команды.",
        "en": "Data, logs and settings stay local. Google Translate receives titles and excerpts when translation is enabled. Gemini receives monitor context only after an explicit AI command.",
    },
    "setup.watch": {"ru": "Watch-регионы", "en": "Watch regions"},
    "setup.watch_placeholder": {
        "ru": "например: Russia, Europe, Africa",
        "en": "for example: Russia, Europe, Africa",
    },
    "setup.language": {"ru": "Язык интерфейса: ru или en", "en": "Interface language: ru or en"},
    "setup.theme": {"ru": "Тема", "en": "Theme"},
    "setup.save": {"ru": "Сохранить и синхронизировать", "en": "Save and synchronize"},
    "setup.later": {"ru": "Позже", "en": "Later"},
    "auth.title": {"ru": "GEMINI / ПОСТОЯННЫЙ API-КЛЮЧ", "en": "GEMINI / PERSISTENT API KEY"},
    "auth.note": {
        "ru": "Ключ хранится локально в ~/.config/redline/gemini.key с правами 0600. REDLINE никогда не показывает и не журналирует его.",
        "en": "The key is stored locally in ~/.config/redline/gemini.key with 0600 permissions. REDLINE never displays or logs it.",
    },
    "auth.placeholder": {"ru": "Вставьте Gemini API key", "en": "Paste Gemini API key"},
    "auth.save": {"ru": "Сохранить", "en": "Save"},
    "auth.remove": {"ru": "Удалить сохранённый", "en": "Remove saved key"},
    "auth.cancel": {"ru": "Отмена", "en": "Cancel"},
    "auth.saved": {
        "ru": "GEMINI // ключ сохранён локально; AI-команды готовы.",
        "en": "GEMINI // key saved locally; AI commands are ready.",
    },
    "auth.removed": {
        "ru": "GEMINI // сохранённый ключ удалён.",
        "en": "GEMINI // stored key removed.",
    },
    "auth.error": {
        "ru": "GEMINI // ключ не сохранён: {error}",
        "en": "GEMINI // key not saved: {error}",
    },
    "panel.feed": {"ru": "ПОТОК СОБЫТИЙ", "en": "EVENT FEED"},
    "panel.inspector": {"ru": "ИНСПЕКТОР", "en": "INSPECTOR"},
    "panel.map": {"ru": "КАРТА / BRAILLE", "en": "MAP / BRAILLE"},
    "panel.coastline": {"ru": "БЕРЕГОВАЯ ЛИНИЯ", "en": "COASTLINE"},
    "panel.land": {"ru": "СУША", "en": "LAND"},
    "panel.outbreak": {"ru": "ВСПЫШКА", "en": "OUTBREAK"},
    "panel.spread": {"ru": "РАСПР.", "en": "SPREAD"},
    "panel.extinction": {"ru": "ВЫМИР.", "en": "EXTINCT."},
    "panel.command": {"ru": "КОМАНДА >", "en": "COMMAND >"},
    "top.title": {
        "ru": "REDLINE  //  ОФИЦИАЛЬНЫЙ ЭПИДЕМИОЛОГИЧЕСКИЙ РАДАР",
        "en": "REDLINE  //  OFFICIAL EPIDEMIOLOGICAL RADAR",
    },
    "notice": {
        "ru": "информационный радар · не медицинская рекомендация",
        "en": "information radar · not medical advice",
    },
    "sources.empty": {
        "ru": "ИСТОЧНИКИ // ещё не синхронизированы. :sync",
        "en": "SOURCES // not synchronized yet. :sync",
    },
    "sources.label": {"ru": "ИСТОЧНИКИ // ", "en": "SOURCES // "},
    "sources.ok": {"ru": "НОРМА", "en": "OK"},
    "sources.stale": {"ru": "УСТАРЕЛ", "en": "STALE"},
    "events.empty": {
        "ru": "Нет событий по текущему фильтру.\n\nВведите :sync для первой проверки источников.",
        "en": "No events match the current filter.\n\nEnter :sync to check sources.",
    },
    "field.source": {"ru": "Источник", "en": "Source"},
    "field.territory": {"ru": "Территория", "en": "Territory"},
    "field.status": {"ru": "Статус", "en": "Status"},
    "field.map_status": {"ru": "Слой карты", "en": "Map layer"},
    "field.map_scope": {"ru": "Масштаб", "en": "Coverage"},
    "field.date": {"ru": "Дата", "en": "Date"},
    "field.unknown": {"ru": "не указана", "en": "not stated"},
    "field.active_alert": {"ru": "АКТИВНЫЙ ALERT", "en": "ACTIVE ALERT"},
    "rd.heading": {
        "ru": "R&D BLUEPRINT // профиль контрмер WHO",
        "en": "R&D BLUEPRINT // WHO countermeasure profile",
    },
    "rd.family": {"ru": "Семейство", "en": "Pathogen family"},
    "rd.prototype": {"ru": "Прототип", "en": "Prototype pathogen"},
    "rd.updated": {"ru": "Последнее обновление", "en": "Last update"},
    "rd.checked": {"ru": "Последняя проверка", "en": "Last checked"},
    "rd.roadmap": {"ru": "Roadmap", "en": "Roadmap"},
    "rd.diagnostics": {"ru": "Диагностика", "en": "Diagnostics"},
    "rd.vaccines": {"ru": "Вакцины", "en": "Vaccines"},
    "rd.therapeutics": {"ru": "Терапевтика", "en": "Therapeutics"},
    "rd.clinical_protocols": {"ru": "Клинические протоколы", "en": "Clinical protocols"},
    "rd.status.published": {"ru": "ОПУБЛИКОВАНО", "en": "PUBLISHED"},
    "rd.status.in_development": {"ru": "В РАЗРАБОТКЕ", "en": "IN DEVELOPMENT"},
    "rd.status.reference": {"ru": "ССЫЛКА WHO", "en": "WHO REFERENCE"},
    "rd.not_synced": {"ru": "не синхронизировано", "en": "not synchronized"},
    "rd.not_stated": {"ru": "не указано WHO", "en": "not stated by WHO"},
    "rd.catalogued": {"ru": "каталог WHO-2024", "en": "WHO-2024 catalogue"},
    "rd.sync_hint": {
        "ru": "Артефакты появятся после :sync who_blueprint",
        "en": "Artifacts will appear after :sync who_blueprint",
    },
    "selected.actions": {
        "ru": "Enter: встроенный viewer   R: отметить alert прочитанным",
        "en": "Enter: built-in viewer   R: mark alert as read",
    },
    "viewer.loading": {
        "ru": "VIEWER // загрузка локальной копии...",
        "en": "VIEWER // loading local copy...",
    },
    "viewer.not_found": {
        "ru": "Документ для события не найден.",
        "en": "No document was found for this event.",
    },
    "viewer.pdf_missing": {
        "ru": "Для извлечения PDF установите REDLINE с дополнением 'documents'.",
        "en": "PDF extraction requires REDLINE's 'documents' extra.",
    },
    "viewer.original": {"ru": "ОРИГИНАЛ", "en": "ORIGINAL"},
    "command.prefix": {
        "ru": "Команды начинаются с :. Введите :help.",
        "en": "Commands start with :. Enter :help.",
    },
    "command.syntax_error": {"ru": "Ошибка синтаксиса: {error}", "en": "Syntax error: {error}"},
    "command.unknown": {
        "ru": "Неизвестная команда: {command}. Введите :help.",
        "en": "Unknown command: {command}. Enter :help.",
    },
    "command.error": {"ru": "Ошибка команды: {error}", "en": "Command error: {error}"},
    "command.sync_usage": {"ru": "Использование: :sync [source]", "en": "Usage: :sync [source]"},
    "command.focus_usage": {
        "ru": "Использование: :focus <world|region|country>",
        "en": "Usage: :focus <world|region|country>",
    },
    "command.focus_unknown": {
        "ru": "Неизвестный регион или страна.",
        "en": "Unknown region or country.",
    },
    "command.filter_usage": {
        "ru": "Использование: :filter key=value или :filter clear",
        "en": "Usage: :filter key=value or :filter clear",
    },
    "command.filter_fields": {
        "ru": "Допустимы source, disease, region, status, emergency",
        "en": "Allowed fields: source, disease, region, status, emergency",
    },
    "command.export_usage": {
        "ru": "Использование: :export <json|markdown> [path]",
        "en": "Usage: :export <json|markdown> [path]",
    },
    "command.export_done": {"ru": "EXPORT // создан {path}", "en": "EXPORT // created {path}"},
    "command.ask_usage": {
        "ru": "Использование: :ask ai <вопрос>",
        "en": "Usage: :ask ai <question>",
    },
    "command.advice_usage": {
        "ru": "Использование: :advice или :advice ai",
        "en": "Usage: :advice or :advice ai",
    },
    "command.test_usage": {
        "ru": "Использование: :test, :test off, :test ai <сценарий>, :test ai timelapse [duration=3y] [speed=1w/s] <сценарий>, :test pause|play|step",
        "en": "Usage: :test, :test off, :test ai <scenario>, :test ai timelapse [duration=3y] [speed=1w/s] <scenario>, :test pause|play|step",
    },
    "command.language_usage": {
        "ru": "Использование: :language <ru|en>",
        "en": "Usage: :language <ru|en>",
    },
    "command.language_changed": {
        "ru": "LANGUAGE // интерфейс переключён на русский",
        "en": "LANGUAGE // interface switched to English",
    },
    "history.status": {
        "ru": "HISTORY // окно: {days} дней. Архив хранится 12 месяцев.",
        "en": "HISTORY // window: {days} days. The archive is retained for 12 months.",
    },
    "timeline": {
        "ru": "HISTORY {days}D  ━━━━━━━━━━━━━━━━━━━━━  {count} событий  // фокус: {focus}",
        "en": "HISTORY {days}D  ━━━━━━━━━━━━━━━━━━━━━  {count} events  // focus: {focus}",
    },
    "sync.running": {
        "ru": "SYNC // проверка официальных источников...",
        "en": "SYNC // checking official sources...",
    },
    "sync.partial": {
        "ru": "SYNC // часть источников недоступна",
        "en": "SYNC // some sources unavailable",
    },
    "sync.done": {
        "ru": "SYNC // событий: {events}; R&D-артефактов: {artifacts}; alert: {alerts}",
        "en": "SYNC // events: {events}; R&D artifacts: {artifacts}; alerts: {alerts}",
    },
    "settings.translation_on": {"ru": "googletrans (онлайн)", "en": "googletrans (online)"},
    "settings.disabled": {"ru": "отключён", "en": "disabled"},
    "settings.ai_ready": {"ru": "готов", "en": "ready"},
    "settings.ai_missing": {"ru": "нет ключа", "en": "API key missing"},
    "audit.empty": {"ru": "Пока пуст.", "en": "Empty."},
    "audit.heading": {"ru": "ЖУРНАЛ АУДИТА", "en": "AUDIT LOG"},
    "settings.heading": {"ru": "НАСТРОЙКИ", "en": "SETTINGS"},
    "ai.running": {
        "ru": "GEMINI // анализ контекста монитора...",
        "en": "GEMINI // analyzing monitor context...",
    },
    "ai.test_running": {
        "ru": "GEMINI // построение изолированного тестового сценария...",
        "en": "GEMINI // building an isolated test scenario...",
    },
    "ai.timelapse_running": {
        "ru": "GEMINI // построение синтетического таймлапса...",
        "en": "GEMINI // building a synthetic timelapse...",
    },
    "ai.error": {"ru": "GEMINI // ошибка: {error}", "en": "GEMINI // error: {error}"},
    "ai.answer_heading": {"ru": "GEMINI // ОТВЕТ", "en": "GEMINI // ANSWER"},
    "ai.advice_heading": {
        "ru": "GEMINI // АНАЛИТИЧЕСКИЕ СОВЕТЫ · НЕ ПОЗИЦИЯ WHO",
        "en": "GEMINI // ANALYTICAL ADVICE · NOT A WHO POSITION",
    },
    "ai.model": {"ru": "Модель", "en": "Model"},
    "ai.key_missing": {
        "ru": "Gemini API key не настроен. Введите :auth и сохраните его один раз.",
        "en": "Gemini API key is not configured. Enter :auth and save it once.",
    },
    "test.entered": {
        "ru": "TEST MODE // изолированная база активна. :test ai <сценарий> создаст синтетические данные; :test off вернёт live-режим.",
        "en": "TEST MODE // isolated database active. :test ai <scenario> creates synthetic data; :test off returns to live mode.",
    },
    "test.source_line": {
        "ru": "TEST DATA // SYNTHETIC · СИНХРОНИЗАЦИЯ ИСТОЧНИКОВ ОТКЛЮЧЕНА · :test off — возврат",
        "en": "TEST DATA // SYNTHETIC · SOURCE SYNC OFF · :test off to return",
    },
    "test.left": {
        "ru": "LIVE MODE // локальные официальные данные",
        "en": "LIVE MODE // local official data",
    },
    "test.sync_disabled": {
        "ru": "Синхронизация отключена в TEST MODE. Используйте :test off.",
        "en": "Synchronization is disabled in TEST MODE. Use :test off.",
    },
    "test.generated": {
        "ru": "TEST MODE // создан сценарий «{title}»: {count} синтетических событий\nМодель: {model}\nДанные существуют только до выхода из тестового режима.",
        "en": "TEST MODE // generated scenario “{title}”: {count} synthetic events\nModel: {model}\nData exist only until test mode is closed.",
    },
    "test.timelapse_generated": {
        "ru": "TIMELAPSE // «{title}» · {weeks} нед. · скорость {speed}\nМодель: {model}\nСобытия синтетические и существуют только в памяти.",
        "en": "TIMELAPSE // “{title}” · {weeks} weeks · speed {speed}\nModel: {model}\nEvents are synthetic and exist only in memory.",
    },
    "test.timelapse_status": {
        "ru": "TIMELAPSE · неделя {week}/{total} · {speed} · {state}",
        "en": "TIMELAPSE · week {week}/{total} · {speed} · {state}",
    },
    "test.timelapse_playing": {"ru": "ВОСПРОИЗВЕДЕНИЕ", "en": "PLAYING"},
    "test.timelapse_paused": {"ru": "ПАУЗА", "en": "PAUSED"},
    "test.timelapse_complete": {"ru": "ЗАВЕРШЁН", "en": "COMPLETE"},
    "test.timelapse_missing": {
        "ru": "Сначала создайте :test ai timelapse <сценарий>",
        "en": "Create :test ai timelapse <scenario> first",
    },
    "test.timelapse_speed_error": {
        "ru": "Скорость: speed=1w/s, speed=2w/s или speed=1w/2s",
        "en": "Speed syntax: speed=1w/s, speed=2w/s or speed=1w/2s",
    },
    "test.timelapse_duration_error": {
        "ru": "Длительность: duration=90d, duration=26w, duration=18m или duration=3y; максимум 10 лет",
        "en": "Duration syntax: duration=90d, duration=26w, duration=18m or duration=3y; maximum 10 years",
    },
    "top.test": {"ru": "TEST MODE / SYNTHETIC", "en": "TEST MODE / SYNTHETIC"},
    "who.heading": {
        "ru": "WHO // АТРИБУТИРОВАННЫЕ РЕКОМЕНДАЦИИ",
        "en": "WHO // ATTRIBUTED GUIDANCE",
    },
    "who.notice": {
        "ru": "Только выдержки из локально сохранённых документов WHO; не медицинская рекомендация REDLINE.",
        "en": "Only excerpts from locally stored WHO documents; not medical advice from REDLINE.",
    },
    "who.empty": {
        "ru": "В локальных документах WHO явные рекомендации не найдены. Выполните :sync.",
        "en": "No explicit guidance was found in local WHO documents. Run :sync.",
    },
    "brief.heading": {"ru": "СВОДКА ИЗМЕНЕНИЙ", "en": "CHANGE BRIEF"},
    "brief.notice": {
        "ru": "Информационный радар. Не медицинская рекомендация и не полный реестр угроз.",
        "en": "Information radar. Not medical advice or a complete threat registry.",
    },
    "brief.alerts": {"ru": "Новые alert: {count}", "en": "New alerts: {count}"},
    "brief.empty": {
        "ru": "Пока нет локально сохранённых официальных событий. Выполните :sync.",
        "en": "No official events are stored locally yet. Run :sync.",
    },
}


COMMANDS = (
    (":help", "cmd.help"),
    (":exit", "cmd.exit"),
    (":auth", "cmd.auth"),
    (":language <ru|en>", "cmd.language"),
    (":focus <world|region|country>", "cmd.focus"),
    (":filter key=value", "cmd.filter"),
    (":sync [source]", "cmd.sync"),
    (":history [days]", "cmd.history"),
    (":brief", "cmd.brief"),
    (":advice [ai]", "cmd.advice"),
    (":ask ai <question>", "cmd.ask"),
    (":test [off]", "cmd.test"),
    (":test ai <scenario>", "cmd.test_ai"),
    (":test ai timelapse [duration=3y] [speed=1w/s] <scenario>", "cmd.test_timelapse"),
    (":test pause|play|step", "cmd.test_controls"),
    (":export <json|markdown> [path]", "cmd.export"),
    (":log", "cmd.log"),
    (":settings", "cmd.settings"),
)

TEXT.update(
    {
        "cmd.help": {"ru": "список команд", "en": "command reference"},
        "cmd.exit": {"ru": "закрыть REDLINE", "en": "close REDLINE"},
        "cmd.auth": {
            "ru": "сохранить или удалить Gemini API key",
            "en": "save or remove Gemini API key",
        },
        "cmd.language": {"ru": "сменить язык интерфейса", "en": "change interface language"},
        "cmd.focus": {"ru": "фокус карты", "en": "focus map"},
        "cmd.filter": {"ru": "фильтры событий", "en": "event filters"},
        "cmd.sync": {"ru": "синхронизация официальных источников", "en": "sync official sources"},
        "cmd.history": {"ru": "окно истории", "en": "history window"},
        "cmd.brief": {"ru": "сводка изменений", "en": "change brief"},
        "cmd.advice": {"ru": "рекомендации WHO или анализ AI", "en": "WHO guidance or AI analysis"},
        "cmd.ask": {
            "ru": "вопрос Gemini с контекстом монитора",
            "en": "ask Gemini with monitor context",
        },
        "cmd.test": {"ru": "включить/выключить тестовый режим", "en": "enter/leave test mode"},
        "cmd.test_ai": {
            "ru": "синтетический сценарий через Gemini",
            "en": "synthetic scenario via Gemini",
        },
        "cmd.test_timelapse": {
            "ru": "AI-таймлапс; по умолчанию одна неделя в секунду",
            "en": "AI timelapse; defaults to one week per second",
        },
        "cmd.test_controls": {
            "ru": "пауза, продолжение или один недельный шаг",
            "en": "pause, resume or advance by one week",
        },
        "cmd.export": {"ru": "экспорт", "en": "export"},
        "cmd.log": {"ru": "локальный audit log", "en": "local audit log"},
        "cmd.settings": {"ru": "текущая конфигурация", "en": "current configuration"},
    }
)


def normalize_language(language: str) -> str:
    return language.casefold() if language.casefold() in SUPPORTED_LANGUAGES else "ru"


def tr(language: str, key: str, **values: object) -> str:
    language = normalize_language(language)
    translations = TEXT.get(key)
    if translations is None:
        return key
    return translations.get(language, translations["ru"]).format(**values)


def command_help(language: str) -> dict[str, str]:
    return {syntax: tr(language, key) for syntax, key in COMMANDS}
