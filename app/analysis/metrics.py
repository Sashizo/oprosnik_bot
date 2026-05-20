"""Расчёт базовых метрик по данным интервью.

Все функции принимают list[SessionRecord] — чистые, без БД, тестируемы без SQLite.

Метрики:
  completion_rate()        — доля завершённых сессий
  dropout_distribution()   — сколько участников бросили после каждого вопроса
  avg_answer_length()      — средняя длина ответа по каждому вопросу (в символах)
  duration_stats()         — мин/среднее/макс длительности завершённых интервью
  print_report()           — вывод всех метрик в stdout
"""

from app.analysis.export import SessionRecord, duration_minutes
from app.services import interview_script as script


def completion_rate(sessions: list[SessionRecord]) -> float:
    """Доля завершённых сессий (0.0 при пустом списке)."""
    if not sessions:
        return 0.0
    return len([s for s in sessions if s.finished]) / len(sessions)


def dropout_distribution(sessions: list[SessionRecord]) -> dict[int, int]:
    """Количество незавершённых сессий по точке отказа.

    Ключ — current_question_index в момент отказа (0 = не ответили ни на один вопрос).
    Возвращает только незавершённые сессии.
    """
    dist: dict[int, int] = {}
    for s in sessions:
        if not s.finished:
            dist[s.current_question_index] = dist.get(s.current_question_index, 0) + 1
    return dist


def avg_answer_length(sessions: list[SessionRecord]) -> dict[str, float]:
    """Средняя длина ответа в символах по каждому question_id.

    Возвращает словарь {question_id: среднее}. Вопросы без ответов не включаются.
    """
    totals: dict[str, list[int]] = {}
    for s in sessions:
        for a in s.answers:
            totals.setdefault(a.question_id, []).append(len(a.text))
    return {qid: round(sum(lengths) / len(lengths), 1) for qid, lengths in totals.items()}


def duration_stats(sessions: list[SessionRecord]) -> dict[str, float] | None:
    """Мин/среднее/макс длительности завершённых интервью (в минутах).

    Возвращает None если нет ни одной завершённой сессии.
    """
    durations = [
        d for s in sessions
        if (d := duration_minutes(s)) is not None
    ]
    if not durations:
        return None
    return {
        "min": round(min(durations), 2),
        "avg": round(sum(durations) / len(durations), 2),
        "max": round(max(durations), 2),
    }


def print_report(sessions: list[SessionRecord]) -> None:
    """Выводит полный отчёт по метрикам в stdout."""
    total = len(sessions)
    finished = len([s for s in sessions if s.finished])
    rate = completion_rate(sessions)

    print("=" * 50)
    print("  Метрики интервью")
    print("=" * 50)
    print(f"Сессий всего:        {total}")
    if total > 0:
        print(f"Завершённых:         {finished}  ({rate * 100:.1f}%)")
        print(f"Незавершённых:       {total - finished}  ({(1 - rate) * 100:.1f}%)")
    else:
        print("Данных нет.")
        return

    # Отказы
    dropout = dropout_distribution(sessions)
    if dropout:
        print("\nОтказы по вопросам (незавершённые сессии):")
        q_names = {q.question_id: q.text[:40] + "…" for q in script.QUESTIONS}
        for idx in sorted(dropout):
            if idx == 0:
                label = "До Q1 (0 ответов)"
            else:
                q = script.QUESTIONS[idx - 1]
                label = f"После {q.question_id.upper()} «{q.text[:30]}…»"
            print(f"  {label}: {dropout[idx]} чел.")

    # Средняя длина ответов
    avg = avg_answer_length(sessions)
    if avg:
        print("\nСредняя длина ответов (символов):")
        q_map = {q.question_id: q.text for q in script.QUESTIONS}
        for qid in [q.question_id for q in script.QUESTIONS]:
            if qid in avg:
                preview = q_map[qid][:45] + "…"
                print(f"  {qid.upper()} «{preview}»: {avg[qid]}")

    # Продолжительность
    dur = duration_stats(sessions)
    if dur:
        print(f"\nПродолжительность завершённых (мин):")
        print(f"  Среднее: {dur['avg']}   Мин: {dur['min']}   Макс: {dur['max']}")
    else:
        print("\nПродолжительность: нет завершённых сессий.")

    print("=" * 50)
