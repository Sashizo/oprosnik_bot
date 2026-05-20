"""Загрузчик StudyDefinition из YAML-файла.

Пример вызова:
    sd = load_from_yaml(Path("study.yaml"))
    errors = validate(sd)
"""

from pathlib import Path

import yaml

from app.researcher.schema import QuestionDef, StudyDefinition, StudyTexts


def load_from_yaml(path: Path) -> StudyDefinition:
    """Читает YAML-файл и возвращает StudyDefinition.

    Не выполняет валидацию — вызовите validate() отдельно.
    Поднимает FileNotFoundError / yaml.YAMLError при проблемах с файлом.
    """
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        raise ValueError(f"YAML-файл должен содержать словарь верхнего уровня, получено: {type(data)}")

    raw_questions = data.get("questions") or []
    questions = tuple(
        QuestionDef(
            question_id=str(q.get("id", "")).strip(),
            text=str(q.get("text", "")).strip(),
        )
        for q in raw_questions
        if isinstance(q, dict)
    )

    raw_texts = data.get("texts") or {}
    texts = StudyTexts(
        greeting=str(raw_texts.get("greeting", "")).strip(),
        closing=str(raw_texts.get("closing", "")).strip(),
        redirect=str(raw_texts.get("redirect", "")).strip(),
        help=str(raw_texts.get("help", "")).strip(),
        already_done=str(raw_texts.get("already_done", "")).strip(),
    )

    return StudyDefinition(
        title=str(data.get("title", "")).strip(),
        description=str(data.get("description", "")).strip(),
        questions=questions,
        texts=texts,
    )
