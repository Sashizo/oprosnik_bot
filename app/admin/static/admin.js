/**
 * admin.js — Редактор вопросов (M13).
 *
 * Управляет динамическим списком вопросов в форме исследования.
 * Функции: добавить, удалить, переместить вверх/вниз.
 *
 * HTML-ожидания:
 *   #question-list       — <ul> с элементами вопросов
 *   #add-question-btn    — кнопка «+ Добавить вопрос»
 *   data-allow-changes   — атрибут на #question-list ("true"/"false")
 *   data-next-index      — следующий числовой суффикс для q{n}
 */

(function () {
  "use strict";

  const list = document.getElementById("question-list");
  if (!list) return;                         // страница без редактора — выходим

  const allowChanges = list.dataset.allowChanges === "true";
  let nextIndex = parseInt(list.dataset.nextIndex || "1", 10);

  // ── Обновить номера вопросов в DOM ───────────────────────────────────────

  function renumber() {
    const items = list.querySelectorAll(".question-item");
    items.forEach((item, i) => {
      const numEl = item.querySelector(".q-num");
      if (numEl) numEl.textContent = i + 1 + ".";
    });
  }

  // ── Создать элемент нового вопроса ────────────────────────────────────────

  function makeItem(qid, text) {
    const li = document.createElement("li");
    li.className = "question-item";

    const numSpan = document.createElement("span");
    numSpan.className = "q-num";
    numSpan.textContent = "?";

    const badge = document.createElement("span");
    badge.className = "q-id-badge";
    badge.textContent = qid;

    // Скрытое поле с question_id
    const hiddenId = document.createElement("input");
    hiddenId.type = "hidden";
    hiddenId.name = "q_id";
    hiddenId.value = qid;

    const textarea = document.createElement("textarea");
    textarea.name = "q_text";
    textarea.rows = 3;
    textarea.placeholder = "Текст вопроса…";
    textarea.value = text || "";
    textarea.required = true;

    li.appendChild(numSpan);
    li.appendChild(badge);
    li.appendChild(hiddenId);
    li.appendChild(textarea);

    if (allowChanges) {
      const actions = document.createElement("div");
      actions.className = "q-actions";

      const btnUp = document.createElement("button");
      btnUp.type = "button";
      btnUp.title = "Вверх";
      btnUp.textContent = "↑";
      btnUp.addEventListener("click", () => {
        const prev = li.previousElementSibling;
        if (prev) list.insertBefore(li, prev);
        renumber();
      });

      const btnDown = document.createElement("button");
      btnDown.type = "button";
      btnDown.title = "Вниз";
      btnDown.textContent = "↓";
      btnDown.addEventListener("click", () => {
        const next = li.nextElementSibling;
        if (next) list.insertBefore(next, li);
        renumber();
      });

      const btnDel = document.createElement("button");
      btnDel.type = "button";
      btnDel.title = "Удалить";
      btnDel.textContent = "✕";
      btnDel.style.color = "#dc2626";
      btnDel.addEventListener("click", () => {
        li.remove();
        renumber();
      });

      actions.appendChild(btnUp);
      actions.appendChild(btnDown);
      actions.appendChild(btnDel);
      li.appendChild(actions);
    }

    return li;
  }

  // ── Кнопка «+ Добавить вопрос» ───────────────────────────────────────────

  const addBtn = document.getElementById("add-question-btn");
  if (addBtn && allowChanges) {
    addBtn.addEventListener("click", () => {
      const qid = "q" + nextIndex;
      nextIndex++;
      const item = makeItem(qid, "");
      list.appendChild(item);
      renumber();
      item.querySelector("textarea")?.focus();
    });
  } else if (addBtn) {
    addBtn.style.display = "none";
  }

  // Инициализация: вешаем слушатели на уже существующие элементы
  // (серверно-рендеренные вопросы). Если allowChanges=false — кнопки скрыты.
  if (!allowChanges) {
    list.querySelectorAll(".q-actions").forEach((el) => {
      el.style.display = "none";
    });
  }

  renumber();
})();
