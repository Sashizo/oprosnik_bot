"""CLI для аналитики интервью.

Использование:
  py -m app.analysis export                → CSV в ./exports/
  py -m app.analysis export --format json  → JSON в ./exports/
  py -m app.analysis export --format both  → оба файла
  py -m app.analysis metrics               → текстовый отчёт в stdout

DATABASE_URL берётся из .env через app.core.config.settings.
Каталог ./exports/ создаётся автоматически.
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def cmd_export(args: argparse.Namespace) -> None:
    from app.core.config import settings
    from app.analysis.export import load_sessions, to_csv, to_json

    db_url = settings.database_url
    print(f"Загрузка данных из {db_url} …")
    sessions = load_sessions(db_url)
    print(f"Найдено сессий: {len(sessions)}")

    if not sessions:
        print("Нет данных для экспорта.")
        return

    output_dir = Path(args.output)
    ts = _timestamp()
    fmt = args.format

    if fmt in ("csv", "both"):
        path = output_dir / f"interviews_{ts}.csv"
        to_csv(sessions, path)
        print(f"CSV сохранён: {path}")

    if fmt in ("json", "both"):
        path = output_dir / f"interviews_{ts}.json"
        to_json(sessions, path)
        print(f"JSON сохранён: {path}")


def cmd_metrics(args: argparse.Namespace) -> None:
    from app.core.config import settings
    from app.analysis.export import load_sessions
    from app.analysis.metrics import print_report

    db_url = settings.database_url
    sessions = load_sessions(db_url)
    print_report(sessions)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="py -m app.analysis",
        description="Инструменты аналитики интервью для ВКР",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # export
    p_export = sub.add_parser("export", help="Экспорт данных в CSV или JSON")
    p_export.add_argument(
        "--format", choices=["csv", "json", "both"], default="csv",
        help="Формат экспорта (по умолчанию: csv)",
    )
    p_export.add_argument(
        "--output", default="exports",
        help="Папка для сохранения файлов (по умолчанию: ./exports/)",
    )

    # metrics
    sub.add_parser("metrics", help="Вывод базовых метрик в stdout")

    args = parser.parse_args()

    if args.command == "export":
        cmd_export(args)
    elif args.command == "metrics":
        cmd_metrics(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
