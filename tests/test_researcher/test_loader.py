"""Тесты для app/researcher/loader.py — load_from_yaml()."""

import pytest
import yaml

from app.researcher.loader import load_from_yaml
from app.researcher.schema import validate


VALID_YAML = """
title: "Тестовое исследование"
description: "Описание"

questions:
  - id: q1
    text: "Первый вопрос?"
  - id: q2
    text: "Второй вопрос?"

texts:
  greeting: "Здравствуйте!"
  closing: "Спасибо!"
  redirect: "Понимаю вас.\\n\\n"
  help: "Просто отвечайте."
  already_done: "Интервью завершено."
"""


def test_load_valid_yaml(tmp_path):
    path = tmp_path / "study.yaml"
    path.write_text(VALID_YAML, encoding="utf-8")
    sd = load_from_yaml(path)
    assert sd.title == "Тестовое исследование"
    assert sd.description == "Описание"
    assert len(sd.questions) == 2
    assert sd.questions[0].question_id == "q1"
    assert sd.questions[1].text == "Второй вопрос?"
    assert sd.texts.greeting == "Здравствуйте!"
    assert sd.texts.closing == "Спасибо!"
    assert sd.study_id is None  # не записан в БД


def test_load_valid_yaml_passes_validation(tmp_path):
    path = tmp_path / "study.yaml"
    path.write_text(VALID_YAML, encoding="utf-8")
    sd = load_from_yaml(path)
    assert validate(sd) == []


def test_load_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_from_yaml(tmp_path / "nonexistent.yaml")


def test_load_invalid_yaml_raises(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text("{ invalid yaml: [", encoding="utf-8")
    with pytest.raises(yaml.YAMLError):
        load_from_yaml(path)


def test_load_non_dict_yaml_raises(tmp_path):
    path = tmp_path / "list.yaml"
    path.write_text("- item1\n- item2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="словарь"):
        load_from_yaml(path)


def test_load_optional_description_defaults_to_empty(tmp_path):
    yaml_no_desc = """
title: "Без описания"
questions:
  - id: q1
    text: "Вопрос?"
texts:
  greeting: "Привет"
  closing: "Пока"
  redirect: "Ответьте.\\n\\n"
  help: "Помощь"
  already_done: "Готово."
"""
    path = tmp_path / "study.yaml"
    path.write_text(yaml_no_desc, encoding="utf-8")
    sd = load_from_yaml(path)
    assert sd.description == ""


def test_load_strips_whitespace_from_texts(tmp_path):
    yaml_with_spaces = """
title: "Тест"
questions:
  - id: q1
    text: "  Вопрос с пробелами  "
texts:
  greeting: "  Привет  "
  closing: "Пока"
  redirect: "Ответьте.\\n\\n"
  help: "Помощь"
  already_done: "Готово."
"""
    path = tmp_path / "study.yaml"
    path.write_text(yaml_with_spaces, encoding="utf-8")
    sd = load_from_yaml(path)
    assert sd.questions[0].text == "Вопрос с пробелами"
    assert sd.texts.greeting == "Привет"
