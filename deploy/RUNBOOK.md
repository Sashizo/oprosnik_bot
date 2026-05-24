# Operations Runbook — Interview Bot

Этот документ описывает **операционные процедуры** для уже задеплоенной системы.  
Для первоначальной установки — см. [README.md](README.md).

---

## Быстрый старт: проверить статус

```bash
# Всё в одной команде:
bash /srv/interview/scripts/smoke_check.sh
```

Если всё зелёное — система работает. Если нет — см. раздел «Диагностика».

---

## Deploy Procedure (обновление кода)

### Pre-deploy checklist

Выполнить ДО `git pull`:

- [ ] Убедиться, что тесты проходят (CI зелёный на GitHub Actions или `pytest tests/ -q` локально)
- [ ] Создать ручной backup БД:
  ```bash
  sudo -u user1 /usr/bin/sqlite3 /srv/interview/interview.db \
    ".backup '/srv/interview/backups/interview_predeploy_$(date +%Y%m%d_%H%M).db'"
  ```
- [ ] Записать текущий commit (на случай rollback):
  ```bash
  git -C /srv/interview rev-parse HEAD
  # Сохрани этот хеш — понадобится при откате
  ```
- [ ] Убедиться, что есть SSH-доступ к VM

### Deploy steps

```bash
# 1. Перейти в директорию проекта
cd /srv/interview

# 2. Подтянуть изменения
git pull

# 3. Обновить зависимости (только если изменился requirements.txt)
source .venv/bin/activate && pip install -r requirements.txt

# 4. Перезапустить сервисы
sudo systemctl restart interview-web interview-bot

# 5. Подождать 3–5 секунд и проверить
sleep 4
bash scripts/smoke_check.sh
```

Если `smoke_check.sh` вернул `[OK] All checks passed` — деплой успешен.

---

## Rollback Procedure

Используется когда после деплоя что-то сломалось и нужно быстро вернуться назад.

```bash
cd /srv/interview

# 1. Вернуться к предыдущему коммиту (хеш из pre-deploy checklist)
git checkout <previous-commit-hash>

# 2. Перезапустить сервисы
sudo systemctl restart interview-web interview-bot

# 3. Проверить
sleep 4
bash scripts/smoke_check.sh

# 4. Если нужно восстановить БД из pre-deploy backup:
#    (только если данные были повреждены — в большинстве случаев НЕ нужно)
sudo systemctl stop interview-web interview-bot
cp /srv/interview/backups/interview_predeploy_YYYYMMDD_HHMM.db /srv/interview/interview.db
sudo systemctl start interview-web interview-bot
bash scripts/smoke_check.sh
```

После стабилизации — разобрать причину сбоя и выпустить fix.

---

## Диагностика

### Посмотреть логи

```bash
# Последние 50 строк логов web-сервиса
journalctl -u interview-web -n 50

# Последние 50 строк логов бота
journalctl -u interview-bot -n 50

# Следить за логами в реальном времени
journalctl -u interview-web -f
journalctl -u interview-bot -f

# Логи за последние 10 минут
journalctl -u interview-web --since "10 minutes ago"

# Только ошибки
journalctl -u interview-web -p err -n 30
```

### Проверить статус сервисов

```bash
systemctl status interview-web interview-bot
```

Ожидаемый результат: `Active: active (running)` для обоих.

### nginx

```bash
# Тест конфига
sudo nginx -t

# Статус
systemctl status nginx

# Логи nginx
sudo journalctl -u nginx -n 20
sudo tail -n 30 /var/log/nginx/error.log
```

### Если бот не отвечает на Telegram

1. Проверить `systemctl status interview-bot` — должен быть `active`
2. Проверить логи: `journalctl -u interview-bot -n 30`
3. Убедиться, что Cloudflare Worker работает (telegram бот работает через него)
4. Проверить `.env`: `TELEGRAM_BOT_TOKEN` и `TELEGRAM_BASE_URL` заданы

### Если web-admin не открывается

1. Проверить `systemctl status interview-web` — должен быть `active`
2. Проверить nginx: `sudo nginx -t && systemctl status nginx`
3. Убедиться, что сертификат не истёк: `sudo certbot renew --dry-run`

---

## Частые операции

### Ручной backup БД

```bash
sudo -u user1 /usr/bin/sqlite3 /srv/interview/interview.db \
  ".backup '/srv/interview/backups/interview_manual_$(date +%Y%m%d_%H%M).db'"

# Проверить целостность
sqlite3 /srv/interview/backups/interview_manual_*.db "PRAGMA integrity_check;"
# → ok
```

### Проверить автоматические backup'ы

```bash
ls -lh /srv/interview/backups/
# Ожидаемо: файлы interview_YYYYMMDD.db за последние дни
```

### Перезапустить только один сервис

```bash
sudo systemctl restart interview-web   # только web-admin
sudo systemctl restart interview-bot   # только бот
```

### Обновить nginx конфиг

```bash
sudo nano /etc/nginx/sites-available/interview
sudo nginx -t          # проверить синтаксис
sudo systemctl reload nginx  # применить без простоя
```

### Продление TLS сертификата (автоматическое)

```bash
# Проверить статус автообновления
sudo systemctl status certbot.timer   # должен быть active (waiting)

# Тест-прогон (без реального продления)
sudo certbot renew --dry-run
```

---

## Контакты и ресурсы

- Репозиторий: `github.com/Sashizo/oprosnik_bot`
- Бот: `@soc_oprosnik_bot`
- Web-панель: `https://soc-oprosnik.duckdns.org/admin`
- Health check: `https://soc-oprosnik.duckdns.org/health`
- Документация: `SYSTEM_DESCRIPTION.md`, `deploy/OPS_REFERENCE.md`
