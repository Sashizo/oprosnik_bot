from dataclasses import dataclass

from app.services.session_store import SessionStore
from app.services.prompt_engine import InterviewContext, PromptEngine, StaticPromptEngine

# ── DialogResult ──────────────────────────────────────────────────────────────

_KINDS = frozenset({"question", "closing", "already_done", "redirect", "clarify"})


@dataclass
class DialogResult:
    """Результат обработки одного шага диалога.

    text — текст ответа бота (для отправки участнику).
    kind — тип ответа; используется Telegram-слоем для выбора reply_markup:
      "question"    — следующий вопрос (кнопок нет)
      "closing"     — финальное сообщение (кнопка «Пройти ещё раз»)
      "already_done"— повторный вход после завершения (кнопка «Пройти ещё раз»)
      "redirect"    — редирект при уклонении (кнопок нет)

    __str__ реализован для обратной совместимости:
    существующие assert X in reply работают без изменений.
    """

    text: str
    kind: str

    def __post_init__(self) -> None:
        if self.kind not in _KINDS:
            raise ValueError(f"Неизвестный kind: {self.kind!r}. Допустимые: {_KINDS}")

    def __str__(self) -> str:
        return self.text

    def __contains__(self, item: str) -> bool:  # поддержка «x in result»
        return item in self.text


class DialogManager:
    """Управляет состоянием диалога.

    PromptEngine — единственный источник правды о вопросах.
    DialogManager не импортирует interview_script напрямую
    и не хранит StudyDefinition отдельно: вся логика вопросов
    делегируется engine.questions() и engine.total_questions().
    """

    def __init__(self, store: SessionStore, engine: PromptEngine | None = None) -> None:
        self._store = store
        self._engine: PromptEngine = engine if engine is not None else StaticPromptEngine()

    def start(self, user_id: int) -> DialogResult:
        """Обрабатывает /start: сбрасывает сессию и сразу начинает интервью.

        Возвращает приветствие + первый вопрос единым сообщением.
        Используется только напрямую (например, из тестов); в боте /start
        сначала показывает приветственный экран, затем begin() стартует интервью.
        """
        self._store.reset(user_id)
        ctx = InterviewContext(question_index=0, previous_answers={})
        text = self._engine.intro() + "\n\n" + self._engine.question(ctx)
        return DialogResult(text=text, kind="question")

    def welcome(self) -> str:
        """Приветственный текст для /start-экрана.

        Берётся из engine.intro() — учитывает активное исследование
        (study.texts.greeting при LLM/Static с study, иначе script.GREETING).
        Не привязан к конкретному user_id: одинаков для всех пользователей.
        """
        return self._engine.intro() + "\n\nНажмите кнопку ниже, чтобы начать."

    def begin(self, user_id: int) -> DialogResult:
        """Сбрасывает сессию и возвращает первый вопрос без приветствия.

        Вызывается при нажатии кнопки «Начать интервью» — после того как
        пользователь уже видел приветственный экран (/start или /help).
        Не дублирует intro(), чтобы не перегружать чат.
        """
        self._store.reset(user_id)
        ctx = InterviewContext(question_index=0, previous_answers={})
        return DialogResult(text=self._engine.question(ctx), kind="question")

    def process(self, user_id: int, text: str) -> DialogResult:
        """Обрабатывает текстовый ответ, возвращает следующий ответ бота."""
        session = self._store.get_or_create(user_id)

        if session.finished:
            return DialogResult(text=self._engine.already_done(), kind="already_done")

        current_idx = session.current_question_index
        ctx_current = InterviewContext(
            question_index=current_idx,
            previous_answers=dict(session.answers),
            last_user_text=text.strip(),
        )

        # Если участник уклоняется — возвращаем к текущему вопросу без продвижения.
        # LLMPromptEngine использует LLM-классификатор, StaticPromptEngine — keyword-эвристику.
        if self._engine.is_off_topic(text, ctx_current):
            return DialogResult(text=self._engine.redirect(ctx_current), kind="redirect")

        # Если участник задаёт уточняющий вопрос о формулировке — даём разъяснение
        # и повторяем вопрос без продвижения и без сохранения ответа.
        if self._engine.is_clarifying_question(text, ctx_current):
            return DialogResult(text=self._engine.clarify(ctx_current), kind="clarify")

        # Сохраняем ответ на текущий вопрос.
        # question_id берётся из engine.questions() — единственный источник правды.
        current_q = self._engine.questions()[current_idx]
        session.answers[current_q.question_id] = text.strip()
        session.current_question_index += 1

        ctx = InterviewContext(
            question_index=session.current_question_index,
            previous_answers=dict(session.answers),
            last_user_text=text.strip(),
        )

        # Есть ли следующий вопрос?
        if session.current_question_index < self._engine.total_questions():
            self._store.save(session)
            return DialogResult(text=self._engine.question(ctx), kind="question")

        # Все вопросы пройдены.
        session.finished = True
        self._store.save(session)
        return DialogResult(text=self._engine.closing(ctx), kind="closing")
