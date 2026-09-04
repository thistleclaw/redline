from __future__ import annotations

import argparse
import asyncio
import getpass
from pathlib import Path

from redline import __version__
from redline.config import Config
from redline.database import Database
from redline.reports import write_export
from redline.secrets import SecretStoreError, clear_gemini_api_key, save_gemini_api_key
from redline.services import SyncService
from redline.ui import RedlineApp


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(
        prog="redline", description="REDLINE local-first epidemiological radar"
    )
    command.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = command.add_subparsers(dest="subcommand")
    sync = sub.add_parser("sync", help="Synchronize official sources without opening the TUI")
    sync.add_argument("--source")
    export = sub.add_parser("export", help="Export the local normalized data")
    export.add_argument("kind", choices=("json", "markdown"))
    export.add_argument("path", type=Path)
    auth = sub.add_parser("auth", help="Persist a Gemini API key with user-only permissions")
    auth.add_argument("--clear", action="store_true", help="Remove the stored Gemini API key")
    sub.add_parser("setup", help="Reset setup state and open the first-run screen next time")
    return command


def main(argv: list[str] | None = None) -> None:
    args = parser().parse_args(argv)
    config = Config.load()
    if args.subcommand == "sync":
        database = Database()
        reports = asyncio.run(SyncService(database, config).sync(force=True, source_id=args.source))
        database.close()
        for report in reports:
            print(
                f"{report.source_id}: fetched={report.fetched} events={report.events_added} "
                f"artifacts={report.artifacts_added} alerts={report.alerts_added} "
                f"error={report.error or '-'}"
            )
        return
    if args.subcommand == "export":
        database = Database()
        target = write_export(database, args.kind, args.path, language=config.language)
        database.close()
        print(target)
        return
    if args.subcommand == "auth":
        try:
            if args.clear:
                removed = clear_gemini_api_key()
                print("Stored Gemini API key removed." if removed else "No stored Gemini API key.")
                return
            api_key = getpass.getpass("Gemini API key: ")
            target = save_gemini_api_key(api_key)
        except SecretStoreError as error:
            raise SystemExit(f"Cannot update Gemini API key: {error}") from error
        print(f"Gemini API key saved securely to {target} (mode 0600).")
        return
    if args.subcommand == "setup":
        config.initialized = False
        config.save()
        print("REDLINE setup will open on the next launch.")
        return
    RedlineApp(config=config).run()
