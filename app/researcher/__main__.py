"""CLI для управления сценариями исследования.

Использование:
    py -m app.researcher validate <file.yaml>
    py -m app.researcher create <file.yaml>
    py -m app.researcher list
    py -m app.researcher show <id>
    py -m app.researcher activate <id> [--force]
    py -m app.researcher status
"""

import sys
from pathlib import Path


def _get_repo():
    """Возвращает StudyRepository, подключённый к prod-БД из settings."""
    from app.core.config import settings
    from app.db.database import build_engine, build_session_factory, init_db
    from app.researcher.repository import StudyRepository

    engine = build_engine(settings.database_url)
    init_db(engine)
    return StudyRepository(build_session_factory(engine))


def cmd_validate(args: list[str]) -> int:
    if not args:
        print("Использование: py -m app.researcher validate <file.yaml>")
        return 1

    path = Path(args[0])
    if not path.exists():
        print(f"✗ Файл не найден: {path}")
        return 1

    from app.researcher.loader import load_from_yaml
    from app.researcher.schema import validate
    import yaml

    try:
        sd = load_from_yaml(path)
    except yaml.YAMLError as exc:
        print(f"✗ Ошибка YAML: {exc}")
        return 1
    except Exception as exc:
        print(f"✗ Ошибка загрузки: {exc}")
        return 1

    errors = validate(sd)
    if errors:
        print(f"✗ Найдено ошибок: {len(errors)}")
        for e in errors:
            print(f"  • {e}")
        return 1

    print(f"✓ Файл валиден: {len(sd.questions)} вопросов, все тексты заполнены.")
    return 0


def cmd_create(args: list[str]) -> int:
    if not args:
        print("Использование: py -m app.researcher create <file.yaml>")
        return 1

    path = Path(args[0])
    if not path.exists():
        print(f"✗ Файл не найден: {path}")
        return 1

    from app.researcher.loader import load_from_yaml
    from app.researcher.schema import validate
    import yaml

    try:
        sd = load_from_yaml(path)
    except yaml.YAMLError as exc:
        print(f"✗ Ошибка YAML: {exc}")
        return 1
    except Exception as exc:
        print(f"✗ Ошибка загрузки: {exc}")
        return 1

    errors = validate(sd)
    if errors:
        print(f"✗ Конфигурация невалидна ({len(errors)} ошибок). Исправьте и повторите.")
        for e in errors:
            print(f"  • {e}")
        return 1

    repo = _get_repo()
    created = repo.create(sd)
    print(f'✓ Study #{created.study_id} "{created.title}" создан.')
    print(f'  Для активации: py -m app.researcher activate {created.study_id}')
    return 0


def cmd_list(args: list[str]) -> int:
    repo = _get_repo()
    studies = repo.list_all()

    if not studies:
        print("Сценариев исследования пока нет. Создайте: py -m app.researcher create study.yaml")
        return 0

    # Получаем id активного
    active_id = repo.get_active_orm_id()

    print(f"{'ID':<4}  {'Active':<7}  {'Title'}")
    print("-" * 60)
    for s in studies:
        active_mark = "★ ДА" if s.study_id == active_id else "—"
        print(f"{s.study_id:<4}  {active_mark:<7}  {s.title}")
    return 0


def cmd_show(args: list[str]) -> int:
    if not args:
        print("Использование: py -m app.researcher show <id>")
        return 1

    try:
        study_id = int(args[0])
    except ValueError:
        print(f"✗ id должен быть числом, получено: {args[0]!r}")
        return 1

    repo = _get_repo()
    sd = repo.get_by_id(study_id)
    if sd is None:
        print(f"✗ Study #{study_id} не найден.")
        return 1

    active_id = repo.get_active_orm_id()
    is_active = sd.study_id == active_id

    print(f"Study #{sd.study_id}  [{' АКТИВЕН ' if is_active else ' не активен '}]")
    print(f"Название:    {sd.title}")
    print(f"Описание:    {sd.description or '(нет)'}")
    print()
    print(f"Вопросы ({len(sd.questions)}):")
    for i, q in enumerate(sd.questions, 1):
        print(f"  {i}. [{q.question_id}] {q.text}")
    print()
    print("Тексты:")
    print(f"  greeting:    {sd.texts.greeting[:80]}{'...' if len(sd.texts.greeting) > 80 else ''}")
    print(f"  closing:     {sd.texts.closing[:80]}{'...' if len(sd.texts.closing) > 80 else ''}")
    print(f"  redirect:    {sd.texts.redirect[:80]}{'...' if len(sd.texts.redirect) > 80 else ''}")
    print(f"  help:        {sd.texts.help[:80]}{'...' if len(sd.texts.help) > 80 else ''}")
    print(f"  already_done:{sd.texts.already_done[:80]}{'...' if len(sd.texts.already_done) > 80 else ''}")
    return 0


def cmd_activate(args: list[str]) -> int:
    force = "--force" in args
    id_args = [a for a in args if not a.startswith("--")]

    if not id_args:
        print("Использование: py -m app.researcher activate <id> [--force]")
        return 1

    try:
        study_id = int(id_args[0])
    except ValueError:
        print(f"✗ id должен быть числом, получено: {id_args[0]!r}")
        return 1

    repo = _get_repo()

    # Проверяем существование
    sd = repo.get_by_id(study_id)
    if sd is None:
        print(f"✗ Study #{study_id} не найден.")
        return 1

    # Проверяем незавершённые сессии текущего активного
    current_active_id = repo.get_active_orm_id()
    if current_active_id is not None and current_active_id != study_id:
        unfinished = repo.count_unfinished(current_active_id)
        if unfinished > 0 and not force:
            print(f"! Незавершённых сессий в текущем активном исследовании: {unfinished}.")
            print(f"  Продолжить принудительно? Используйте: --force")
            ans = input("  Продолжить? [y/N]: ").strip().lower()
            if ans != "y":
                print("Отменено.")
                return 0

    ok = repo.activate(study_id)
    if not ok:
        print(f"✗ Study #{study_id} не найден.")
        return 1

    print(f'✓ Study #{study_id} "{sd.title}" активирован.')
    print("  Перезапустите бота для применения изменений.")
    return 0


def cmd_status(args: list[str]) -> int:
    repo = _get_repo()
    sd = repo.get_active()

    if sd is None:
        print("Активного исследования нет. Бот работает в legacy-режиме (interview_script.py).")
        return 0

    total = repo.count_unfinished(sd.study_id) if sd.study_id else 0
    print(f'Активное исследование: #{sd.study_id} "{sd.title}"')
    print(f"Незавершённых сессий:  {total}")
    return 0


COMMANDS = {
    "validate": cmd_validate,
    "create": cmd_create,
    "list": cmd_list,
    "show": cmd_show,
    "activate": cmd_activate,
    "status": cmd_status,
}


def main() -> None:
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print("Использование: py -m app.researcher <команда> [аргументы]")
        print()
        print("Команды:")
        print("  validate <file.yaml>   — проверить конфигурацию")
        print("  create <file.yaml>     — создать Study в БД")
        print("  list                   — показать все Study")
        print("  show <id>              — показать конфигурацию Study (preview)")
        print("  activate <id>          — сделать Study активным")
        print("  status                 — показать активный Study")
        sys.exit(0)

    cmd_name = args[0]
    cmd_args = args[1:]

    if cmd_name not in COMMANDS:
        print(f"✗ Неизвестная команда: {cmd_name!r}")
        print(f"  Доступные: {', '.join(COMMANDS)}")
        sys.exit(1)

    exit_code = COMMANDS[cmd_name](cmd_args)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
