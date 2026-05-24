#!/usr/bin/env bash
# smoke_check.sh — post-deploy health check for Interview Bot (M20)
#
# Запускать на VM после каждого деплоя:
#   bash /srv/interview/scripts/smoke_check.sh
#
# Переменные окружения (читаются из .env если не заданы):
#   ADMIN_PASSWORD — пароль для Basic Auth веб-панели
#   ADMIN_USERNAME — логин (default: researcher)
#   BASE_URL       — базовый URL (default: https://soc-oprosnik.duckdns.org)

set -euo pipefail

# --- конфигурация ---
BASE_URL="${BASE_URL:-https://soc-oprosnik.duckdns.org}"
ADMIN_USERNAME="${ADMIN_USERNAME:-researcher}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-}"

# Если ADMIN_PASSWORD не задан — попробовать прочитать из .env
if [[ -z "$ADMIN_PASSWORD" && -f /srv/interview/.env ]]; then
    ADMIN_PASSWORD=$(grep -E '^ADMIN_PASSWORD=' /srv/interview/.env | cut -d= -f2- | tr -d '"'"'" || echo "")
fi

PASS=0
FAIL=0

ok()   { echo "[OK]   $1"; ((PASS++)) || true; }
fail() { echo "[FAIL] $1"; ((FAIL++)) || true; }

echo "=== Interview Bot Smoke Check ==="
echo "Target: $BASE_URL"
echo ""

# --- 1. Systemd: interview-web ---
if systemctl is-active --quiet interview-web 2>/dev/null; then
    ok "interview-web.service is active"
else
    fail "interview-web.service is NOT active (run: sudo systemctl status interview-web)"
fi

# --- 2. Systemd: interview-bot ---
if systemctl is-active --quiet interview-bot 2>/dev/null; then
    ok "interview-bot.service is active"
else
    fail "interview-bot.service is NOT active (run: sudo systemctl status interview-bot)"
fi

# --- 3. Health endpoint ---
HTTP_STATUS=$(curl -sf -o /dev/null -w "%{http_code}" --max-time 10 "$BASE_URL/health" 2>/dev/null || echo "000")
HEALTH_BODY=$(curl -sf --max-time 10 "$BASE_URL/health" 2>/dev/null || echo "")

if [[ "$HTTP_STATUS" == "200" && "$HEALTH_BODY" == *'"ok"'* ]]; then
    ok "GET /health → 200 OK"
else
    fail "GET /health → $HTTP_STATUS (expected 200 with {\"status\":\"ok\"})"
fi

# --- 4. Web admin (Basic Auth) ---
if [[ -n "$ADMIN_PASSWORD" ]]; then
    ADMIN_STATUS=$(curl -sf -o /dev/null -w "%{http_code}" --max-time 10 \
        -u "$ADMIN_USERNAME:$ADMIN_PASSWORD" \
        "$BASE_URL/admin/studies" 2>/dev/null || echo "000")
    if [[ "$ADMIN_STATUS" == "200" ]]; then
        ok "GET /admin/studies (Basic Auth) → 200 OK"
    else
        fail "GET /admin/studies → $ADMIN_STATUS (expected 200; check credentials or service)"
    fi
else
    echo "[SKIP] /admin/studies check — ADMIN_PASSWORD not set"
fi

# --- 5. HTTPS certificate (не expired) ---
CERT_EXPIRY=$(echo | openssl s_client -servername soc-oprosnik.duckdns.org \
    -connect soc-oprosnik.duckdns.org:443 2>/dev/null \
    | openssl x509 -noout -enddate 2>/dev/null | cut -d= -f2 || echo "")

if [[ -n "$CERT_EXPIRY" ]]; then
    ok "TLS certificate valid until: $CERT_EXPIRY"
else
    fail "Could not verify TLS certificate"
fi

# --- итог ---
echo ""
echo "================================="
if [[ $FAIL -eq 0 ]]; then
    echo "[OK] All checks passed ($PASS/$PASS)"
    exit 0
else
    echo "[FAIL] $FAIL check(s) failed (passed: $PASS)"
    exit 1
fi
