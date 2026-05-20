"""Telegram-интерфейс исследователя.

Отдельный UX-слой поверх StudyRepository и analysis/export.
Не знает про DialogManager; не изменяет состояние интервью.

Публичный интерфейс модуля:
    register_researcher_handlers(app)  — регистрирует CommandHandler + CallbackQueryHandler.

Архитектурное ограничение:
    Этот модуль зависит от bot_data, который заполняется в build_application():
        bot_data["researcher_ids"]  — frozenset[int] авторизованных user_id
        bot_data["study_repo"]      — StudyRepository | None
        bot_data["session_factory"] — sessionmaker | None

Callback data namespace: "r:<action>" — не пересекается с "action:<name>" responder-кнопок.
"""

import io
import logging
from datetime import date

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler

logger = logging.getLogger(__name__)


# ── Callback data константы ───────────────────────────────────────────────────

R_MENU            = "r:menu"
R_LIST            = "r:list"
R_ACTIVATE        = "r:activate"
R_ACTIVATE_PREFIX = "r:activate:"   # r:activate:<study_id>
R_STATS           = "r:stats"
R_EXPORT          = "r:export"


# ── Keyboard builders ─────────────────────────────────────────────────────────

def _kb_main() -> InlineKeyboardMarkup:
    """Главное меню исследователя — 4 действия в 2 ряда."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📋 Список",      callback_data=R_LIST),
            InlineKeyboardButton("✅ Активировать", callback_data=R_ACTIVATE),
        ],
        [
            InlineKeyboardButton("📊 Статистика", callback_data=R_STATS),
            InlineKeyboardButton("📤 Экспорт",    callback_data=R_EXPORT),
        ],
    ])


def _kb_back() -> InlineKeyboardMarkup:
    """Кнопка возврата в главное меню."""
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("↩ Меню", callback_data=R_MENU)
    ]])


# ── Авторизация ───────────────────────────────────────────────────────────────

def _is_researcher(user_id: int, context) -> bool:
    """Проверяет, входит ли user_id в whitelist исследователей."""
    return user_id in context.bot_data.get("researcher_ids", frozenset())


# ── Форматтеры ────────────────────────────────────────────────────────────────

def _fmt_active_card(study) -> str:
    """Карточка активного исследования для главного меню."""
    if study is None:
        return (
            "⚠️ Нет активного исследования.\n"
            "Загрузите исследование через CLI и активируйте здесь."
        )
    return (
        f"📌 Активное исследование: «{study.title}» (id: {study.study_id})\n"
        f"   Вопросов: {len(study.questions)}"
    )


# ── Вспомогательные функции ───────────────────────────────────────────────────

def _count_sessions_for_study(session_factory, study_id: int) -> tuple[int, int]:
    """Считает (всего, завершено) сессий для study_id через session_factory."""
    from app.db.models import InterviewSession
    with session_factory() as db:
        total = (
            db.query(InterviewSession)
            .filter_by(study_id=study_id)
            .count()
        )
        finished = (
            db.query(InterviewSession)
            .filter_by(study_id=study_id, finished=True)
            .count()
        )
    return total, finished


def _generate_csv_bytes(sessions: list) -> bytes:
    """Генерирует CSV-содержимое в памяти (io.StringIO → bytes).

    Использует публичные функции из analysis/export — без записи на диск.
    """
    import csv
    from app.analysis.export import CSV_HEADERS, duration_minutes, question_text_map

    # Строим кэш question_text_map: один раз на уникальный study_id
    q_map_cache: dict = {}
    for s in sessions:
        if s.study_id not in q_map_cache:
            q_map_cache[s.study_id] = question_text_map(s.study_id)

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=CSV_HEADERS)
    writer.writeheader()

    for s in sessions:
        q_map = q_map_cache[s.study_id]
        dur = duration_minutes(s)
        base = {
            "session_id":       s.session_id,
            "user_id":          s.user_id,
            "started_at":       s.started_at.isoformat(),
            "finished_at":      s.finished_at.isoformat() if s.finished_at else "",
            "finished":         s.finished,
            "duration_minutes": dur if dur is not None else "",
        }
        if s.answers:
            for a in s.answers:
                writer.writerow({
                    **base,
                    "question_id":         a.question_id,
                    "question_text":        q_map.get(a.question_id, ""),
                    "answer_text":          a.text,
                    "answered_at":          a.answered_at.isoformat(),
                    "answer_length_chars":  len(a.text),
                })
        else:
            writer.writerow({
                **base,
                "question_id": "", "question_text": "",
                "answer_text": "", "answered_at": "", "answer_length_chars": "",
            })

    return buf.getvalue().encode("utf-8")


# ── Handler'ы ─────────────────────────────────────────────────────────────────

async def _cmd_researcher(update: Update, context) -> None:
    """Точка входа /researcher — показывает карточку + главное меню.

    Тихо игнорирует неавторизованных пользователей:
    обычные участники не должны знать о существовании этой команды.
    """
    if not _is_researcher(update.effective_user.id, context):
        return

    repo = context.bot_data.get("study_repo")
    active = repo.get_active() if repo is not None else None
    text = _fmt_active_card(active)

    await update.message.reply_text(text, reply_markup=_kb_main())


async def _handle_researcher_callback(update: Update, context) -> None:
    """Роутер всех r:* callback_data.

    Авторизация: неавторизованный — тихий выход после query.answer().
    Роутинг: по точному совпадению или по prefix.
    """
    query = update.callback_query
    data = query.data

    # Экспорт — отвечаем с toast-уведомлением до начала генерации.
    if data == R_EXPORT:
        await query.answer(text="⏳ Генерирую CSV…")
    else:
        await query.answer()

    if not _is_researcher(query.from_user.id, context):
        return

    repo = context.bot_data.get("study_repo")

    if data == R_MENU:
        active = repo.get_active() if repo is not None else None
        await query.message.edit_text(_fmt_active_card(active), reply_markup=_kb_main())

    elif data == R_LIST:
        await _show_list(query, repo)

    elif data == R_ACTIVATE:
        await _show_activate_menu(query, repo)

    elif data.startswith(R_ACTIVATE_PREFIX):
        study_id_str = data[len(R_ACTIVATE_PREFIX):]
        await _do_activate(query, repo, study_id_str)

    elif data == R_STATS:
        await _show_stats(query, repo, context)

    elif data == R_EXPORT:
        await _do_export(query, context)

    # else: неизвестный r:* action — молча игнорируем (forward compatibility)


async def _show_list(query, repo) -> None:
    """Показывает все исследования; активное помечено."""
    logger.info("[AUDIT] action=researcher_list user_id=%d", query.from_user.id)
    if repo is None:
        await query.message.edit_text(
            "❌ StudyRepository недоступен.", reply_markup=_kb_back()
        )
        return

    studies = repo.list_all()
    active = repo.get_active()
    active_id = active.study_id if active is not None else None

    if not studies:
        text = (
            "📋 Исследований нет.\n"
            "Загрузите через CLI: python -m app.researcher"
        )
    else:
        lines = ["Все исследования:\n"]
        for s in studies:
            marker = "✅" if s.study_id == active_id else "  "
            suffix = " (активное)" if s.study_id == active_id else ""
            lines.append(f"{marker} [{s.study_id}] {s.title}{suffix}")
        text = "\n".join(lines)

    await query.message.edit_text(text, reply_markup=_kb_back())


async def _show_activate_menu(query, repo) -> None:
    """Показывает список исследований для активации (кнопка на каждое)."""
    if repo is None:
        await query.message.edit_text(
            "❌ StudyRepository недоступен.", reply_markup=_kb_back()
        )
        return

    studies = repo.list_all()
    if not studies:
        await query.message.edit_text(
            "📋 Нет исследований для активации.\nСначала загрузите через CLI.",
            reply_markup=_kb_back(),
        )
        return

    buttons = [
        [InlineKeyboardButton(
            f"[{s.study_id}] {s.title}",
            callback_data=f"{R_ACTIVATE_PREFIX}{s.study_id}",
        )]
        for s in studies
    ]
    buttons.append([InlineKeyboardButton("↩ Меню", callback_data=R_MENU)])

    await query.message.edit_text(
        "Выберите исследование для активации:",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def _do_activate(query, repo, study_id_str: str) -> None:
    """Активирует исследование по id."""
    try:
        study_id = int(study_id_str)
    except ValueError:
        await query.message.edit_text(
            "❌ Некорректный id исследования.", reply_markup=_kb_back()
        )
        return

    if repo is None:
        await query.message.edit_text(
            "❌ StudyRepository недоступен.", reply_markup=_kb_back()
        )
        return

    ok = repo.activate(study_id)
    if ok:
        logger.info(
            "[AUDIT] action=researcher_activate_study study_id=%d user_id=%d",
            study_id, query.from_user.id,
        )
        sd = repo.get_by_id(study_id)
        title = sd.title if sd is not None else str(study_id)
        text = (
            f"✅ Активировано: «{title}» (id: {study_id}).\n"
            "Новые сессии будут использовать это исследование."
        )
    else:
        text = f"❌ Исследование с id={study_id} не найдено."

    await query.message.edit_text(text, reply_markup=_kb_back())


async def _show_stats(query, repo, context) -> None:
    """Показывает краткую статистику по активному исследованию."""
    logger.info("[AUDIT] action=researcher_stats user_id=%d", query.from_user.id)
    if repo is None:
        await query.message.edit_text(
            "❌ StudyRepository недоступен.", reply_markup=_kb_back()
        )
        return

    active = repo.get_active()
    if active is None:
        await query.message.edit_text(
            "⚠️ Нет активного исследования — статистика недоступна.",
            reply_markup=_kb_back(),
        )
        return

    session_factory = context.bot_data.get("session_factory")
    if session_factory is None:
        await query.message.edit_text(
            "❌ session_factory недоступен.", reply_markup=_kb_back()
        )
        return

    total, finished = _count_sessions_for_study(session_factory, active.study_id)
    in_progress = total - finished
    pct = f" ({finished * 100 // total}%)" if total > 0 else ""

    text = (
        f"📊 Статистика: «{active.title}»\n\n"
        f"Всего сессий:    {total}\n"
        f"Завершено:       {finished}{pct}\n"
        f"В процессе:      {in_progress}"
    )

    await query.message.edit_text(text, reply_markup=_kb_back())


async def _do_export(query, context) -> None:
    """Генерирует CSV в памяти и отправляет как Telegram document."""
    logger.info("[AUDIT] action=researcher_export user_id=%d", query.from_user.id)
    session_factory = context.bot_data.get("session_factory")
    if session_factory is None:
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="❌ session_factory недоступен — экспорт невозможен.",
        )
        return

    from app.db.repository import get_all_sessions

    sessions = get_all_sessions(session_factory)
    csv_bytes = _generate_csv_bytes(sessions)

    total = len(sessions)
    finished = sum(1 for s in sessions if s.finished)
    filename = f"export_{date.today().isoformat()}.csv"

    await context.bot.send_document(
        chat_id=query.message.chat_id,
        document=io.BytesIO(csv_bytes),
        filename=filename,
        caption=f"📤 Экспорт завершён. {finished} завершённых сессий, {total} всего.",
    )


# ── Регистрация ───────────────────────────────────────────────────────────────

def register_researcher_handlers(app: Application) -> None:
    """Регистрирует researcher CommandHandler и CallbackQueryHandler.

    ВАЖНО: должна вызываться ДО регистрации универсального
    CallbackQueryHandler responder-кнопок ("action:*"), иначе responder-handler
    перехватит "r:*" callback'и раньше researcher-handler'а.

    Pattern r"^r:" обеспечивает изоляцию: только researcher-callback'и
    попадают в этот handler, responder-callback'и ("action:*") — нет.
    """
    app.add_handler(CommandHandler("researcher", _cmd_researcher))
    app.add_handler(
        CallbackQueryHandler(_handle_researcher_callback, pattern=r"^r:")
    )
