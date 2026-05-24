# Operational Reference — Interview Bot

Краткий справочник по операционным командам. Для развёрнутых процедур — см. [RUNBOOK.md](RUNBOOK.md).

---

## Systemd сервисы

```bash
# Статус
systemctl status interview-web interview-bot

# Перезапуск
sudo systemctl restart interview-web interview-bot

# Остановка / запуск
sudo systemctl stop interview-web
sudo systemctl start interview-web

# Включить/выключить автозапуск при загрузке
sudo systemctl enable interview-web
sudo systemctl disable interview-web

# Перечитать unit-файлы (после их изменения)
sudo systemctl daemon-reload
```

---

## Логи (journalctl)

```bash
# Последние N строк
journalctl -u interview-web -n 50
journalctl -u interview-bot -n 50

# Следить в реальном времени
journalctl -u interview-web -f
journalctl -u interview-bot -f

# За последние N минут
journalctl -u interview-web --since "10 minutes ago"

# За конкретный период
journalctl -u interview-web --since "2025-05-20 10:00" --until "2025-05-20 10:30"

# Только ошибки (priority: err и выше)
journalctl -u interview-web -p err -n 30

# Audit события
journalctl -u interview-web | grep '\[AUDIT\]'
journalctl -u interview-bot | grep '\[AUDIT\]'

# Guardrail события (off-topic, suspicious input)
journalctl -u interview-bot | grep '\[GUARDRAIL\]'

# Размер журнала
journalctl --disk-usage
```

---

## nginx

```bash
# Проверить конфиг
sudo nginx -t

# Применить изменения (без простоя)
sudo systemctl reload nginx

# Перезапустить
sudo systemctl restart nginx

# Статус
systemctl status nginx

# Логи nginx
sudo journalctl -u nginx -n 30
sudo tail -n 30 /var/log/nginx/error.log
sudo tail -n 30 /var/log/nginx/access.log

# Конфиг Interview Bot
sudo nano /etc/nginx/sites-available/interview
sudo cat /etc/nginx/sites-available/interview
```

---

## TLS / Certbot

```bash
# Тест-прогон автопродления (без реального продления)
sudo certbot renew --dry-run

# Статус таймера автопродления (раз в 12 часов)
sudo systemctl status certbot.timer

# Ручное продление
sudo certbot renew

# Посмотреть срок действия сертификата
echo | openssl s_client -servername soc-oprosnik.duckdns.org \
  -connect soc-oprosnik.duckdns.org:443 2>/dev/null \
  | openssl x509 -noout -enddate
```

---

## SQLite / База данных

```bash
# Открыть консоль SQLite
sqlite3 /srv/interview/interview.db

# Полезные команды внутри sqlite3:
# .tables                          — список таблиц
# .schema interview_sessions       — структура таблицы
# SELECT count(*) FROM interview_sessions;
# SELECT count(*) FROM interview_sessions WHERE status='done';
# SELECT count(*) FROM studies;
# .quit

# Проверить целостность БД
sqlite3 /srv/interview/interview.db "PRAGMA integrity_check;"
# → ok

# Размер файла БД
ls -lh /srv/interview/interview.db

# WAL mode (должен быть включён)
sqlite3 /srv/interview/interview.db "PRAGMA journal_mode;"
# → wal
```

---

## Backup

```bash
# Посмотреть список backup'ов
ls -lh /srv/interview/backups/

# Создать ручной backup
sudo -u user1 /usr/bin/sqlite3 /srv/interview/interview.db \
  ".backup '/srv/interview/backups/interview_manual_$(date +%Y%m%d_%H%M).db'"

# Проверить целостность backup'а
sqlite3 /srv/interview/backups/interview_YYYYMMDD.db "PRAGMA integrity_check;"
# → ok

# Посмотреть данные из backup'а (не трогая основную БД)
sqlite3 /srv/interview/backups/interview_YYYYMMDD.db \
  "SELECT count(*) FROM interview_sessions;"

# Восстановить из backup'а (ОСТОРОЖНО — остановить сервисы!)
sudo systemctl stop interview-web interview-bot
cp /srv/interview/backups/interview_YYYYMMDD.db /srv/interview/interview.db
sudo systemctl start interview-web interview-bot

# Cron задание backup'а
sudo cat /etc/cron.d/interview-backup
```

---

## Переменные окружения

```bash
# Посмотреть .env (содержит секреты — только для администратора)
cat /srv/interview/.env    # права 600 — только владелец

# Права .env
ls -la /srv/interview/.env
# → -rw------- 1 deploy deploy ... .env

# Применить изменения в .env — нужен перезапуск сервисов
sudo systemctl restart interview-web interview-bot
```

---

## Smoke Check

```bash
# Запустить проверку всех компонентов (после деплоя)
bash /srv/interview/scripts/smoke_check.sh

# Запустить с другим URL (например, локально)
BASE_URL=http://127.0.0.1:8000 bash /srv/interview/scripts/smoke_check.sh
```

---

## Git / Деплой

```bash
# Текущий коммит
git -C /srv/interview rev-parse HEAD
git -C /srv/interview log --oneline -5

# Обновить код
cd /srv/interview && git pull

# Проверить есть ли изменения в requirements.txt
git -C /srv/interview diff HEAD~1 requirements.txt

# История деплоев (через git log на VM)
git -C /srv/interview log --oneline --since="1 month ago"
```

---

## Ресурсы

| Ресурс | Адрес |
|---|---|
| Бот | `@soc_oprosnik_bot` |
| Web-панель | `https://soc-oprosnik.duckdns.org/admin` |
| Health check | `https://soc-oprosnik.duckdns.org/health` |
| Репозиторий | `github.com/Sashizo/oprosnik_bot` |
| Deploy guide | `deploy/README.md` |
| Runbook | `deploy/RUNBOOK.md` |
| Системное описание | `SYSTEM_DESCRIPTION.md` |
