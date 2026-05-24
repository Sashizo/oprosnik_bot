# Деплой на Cloud.ru VM (Ubuntu 22.04)

## Архитектура

```
Internet → [nginx :80/:443] → [uvicorn :8000]   (interview-web.service)
                              [bot polling]       (interview-bot.service)
                              [SQLite DB]         /srv/interview/interview.db
```

Два systemd-сервиса на одной ВМ, один общий файл SQLite.

---

## Требования к ВМ (Cloud.ru)

| Параметр | Значение |
|---|---|
| ОС | Ubuntu 22.04 LTS |
| vCPU | 2 |
| RAM | 4 GB |
| SSD | 20 GB |
| Security Group | SSH (22, ваш IP), HTTP (80), HTTPS (443) |

---

## Пошаговый деплой

### 1. Базовая настройка сервера

```bash
# Подключиться по SSH
ssh ubuntu@<IP>

# Обновить пакеты
sudo apt update && sudo apt upgrade -y

# Создать непривилегированного пользователя
sudo useradd -m -s /bin/bash deploy
sudo usermod -aG sudo deploy

# Установить зависимости
sudo apt install -y python3.11 python3.11-venv git nginx certbot python3-certbot-nginx

# Переключиться на пользователя deploy
sudo su - deploy
```

### 2. Перенос кода

```bash
git clone <URL_РЕПОЗИТОРИЯ> /srv/interview
cd /srv/interview
python3.11 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Создание .env на сервере

```bash
nano /srv/interview/.env
chmod 600 /srv/interview/.env
```

Минимальное содержимое (на основе .env.example):

```
APP_ENV=production
APP_HOST=127.0.0.1
APP_PORT=8000
DATABASE_URL=sqlite:////srv/interview/interview.db
TELEGRAM_BOT_TOKEN=<токен>
LLM_PROVIDER=gigachat
LLM_GIGACHAT_CREDENTIALS=<ключ>
RESEARCHER_TELEGRAM_IDS=<ваш_telegram_id>
ADMIN_USERNAME=researcher
ADMIN_PASSWORD=<надёжный_пароль>
```

**Важно:**
- `DATABASE_URL` — абсолютный путь (4 слеша после `sqlite:`).
- `APP_HOST=127.0.0.1` — uvicorn слушает только localhost; nginx — единственная точка входа снаружи.
- `ADMIN_PASSWORD` — обязательно задать перед запуском.

### 4. Перенос БД (если есть данные)

```bash
# С локальной машины
scp interview.db deploy@<IP>:/srv/interview/interview.db

# Проверить миграции на сервере
cd /srv/interview && source .venv/bin/activate
python -c "
from app.db.database import build_engine, init_db
from app.core.config import settings
init_db(build_engine(settings.database_url))
print('OK')
"
```

### 5. Установка systemd-сервисов

```bash
# Скопировать unit-файлы
sudo cp /srv/interview/deploy/interview-web.service /etc/systemd/system/
sudo cp /srv/interview/deploy/interview-bot.service /etc/systemd/system/

# Включить и запустить
sudo systemctl daemon-reload
sudo systemctl enable --now interview-web
sudo systemctl enable --now interview-bot

# Проверить статус
sudo systemctl status interview-web interview-bot
```

### 6. Настройка nginx

```bash
# Скопировать конфиг (отредактировать server_name под ваш IP/домен)
sudo cp /srv/interview/deploy/nginx.conf /etc/nginx/sites-available/interview
sudo nano /etc/nginx/sites-available/interview   # заменить server_name

# Активировать сайт
sudo ln -s /etc/nginx/sites-available/interview /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### 7. HTTPS через Duck DNS + Let's Encrypt (M17)

Бесплатный вариант без покупки домена:

**7.1 Зарегистрировать поддомен** (в браузере, без SSH):
1. Зайти на https://www.duckdns.org → войти через Google
2. Создать поддомен (например: `soc-oprosnik`) → указать IP сервера → «Update IP»
3. Проверить: `nslookup soc-oprosnik.duckdns.org` → должен вернуть IP сервера

**7.2 Открыть порт 443** в Cloud.ru Security Group (Входящий, TCP, 443, 0.0.0.0/0)

**7.3 Установить certbot и получить сертификат** (SSH):
```bash
sudo apt install -y certbot python3-certbot-nginx

# Проверить, что port 80 отвечает через домен
curl -I http://soc-oprosnik.duckdns.org/health   # → 200 OK

# Получить сертификат (certbot перезапишет nginx-конфиг автоматически)
sudo certbot --nginx -d soc-oprosnik.duckdns.org

# Проверить HTTPS
curl -I https://soc-oprosnik.duckdns.org/health  # → 200
curl -I http://soc-oprosnik.duckdns.org/health   # → 301 redirect

# Проверить автообновление
sudo certbot renew --dry-run
sudo systemctl status certbot.timer              # → active (waiting)
```

---

## Smoke-тесты после деплоя

```bash
# Health endpoint
curl http://<IP>/health
# Ожидаемый ответ: {"status":"ok"}

# Web-admin с Basic Auth
curl -u researcher:<пароль> http://<IP>/admin/studies
# Ожидаемый ответ: HTML страница

# Логи
journalctl -u interview-web -f
journalctl -u interview-bot -f
```

В Telegram: отправить `/start` боту — должен ответить.
Researcher: отправить `/researcher` — меню открывается.

---

## Обновление кода

```bash
cd /srv/interview
git pull
source .venv/bin/activate
pip install -r requirements.txt   # если изменились зависимости

sudo systemctl restart interview-web interview-bot
```

---

## Backup БД (M17)

Используется `sqlite3 .backup` — официальный hot backup API SQLite.
Консистентен при активных записях (в отличие от `cp`).
Хранит снимки за 14 дней.

```bash
# Создать директорию
sudo mkdir -p /srv/interview/backups
sudo chown user1:user1 /srv/interview/backups

# Установить cron-job
sudo cp /srv/interview/deploy/interview-backup.cron /etc/cron.d/interview-backup
sudo chmod 644 /etc/cron.d/interview-backup

# Проверить вручную (сразу, не ждать 03:00)
sudo -u user1 /usr/bin/sqlite3 /srv/interview/interview.db \
  ".backup '/srv/interview/backups/interview_test.db'"
sqlite3 /srv/interview/backups/interview_test.db "PRAGMA integrity_check;"
# → ok
```

Backup запускается ежедневно в 03:00 UTC. Старые файлы (>14 дней) удаляются автоматически.

---

## Чеклист безопасности

- [ ] `ADMIN_PASSWORD` задан (не пустой)
- [ ] `APP_HOST=127.0.0.1` — uvicorn не торчит наружу
- [ ] `.env` имеет права `chmod 600`
- [ ] SSH по ключу: `PasswordAuthentication no` в `/etc/ssh/sshd_config`
- [ ] Security Group: закрыт порт 8000, открыты только 22/80/443
- [ ] `RESEARCHER_TELEGRAM_IDS` заполнен нужными ID

---

## Масштабирование (когда понадобится)

- При нагрузке >50 одновременных сессий → 4 vCPU / 8 GB RAM
- При необходимости надёжности хранения → миграция на PostgreSQL
- При нескольких исследователях → managed DB (Cloud.ru DBaaS)
