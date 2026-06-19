#!/usr/bin/env bash
# IR-2026-06-15 tripwire — детект признаков повторного заражения.
# Алерт уходит в Telegram (токен/chat_id берутся из защищённого файла $CONF).
# Тихий при чистоте (пишет в лог 'ok'). Сигналы выбраны так, чтобы НЕ ложнить на деплоях.
set -u
LOG=/root/ir-2026-06-15/tripwire.log
CONF=/root/ir-2026-06-15/tg.conf      # должен содержать: TG_TOKEN=...  и  TG_CHAT=...
TS=$(date '+%F %T')
OUT=""; FOUND=0

# 1) LD_PRELOAD-руткит вернулся (здесь его быть не должно вообще)
if [ -e /etc/ld.so.preload ]; then
  OUT="${OUT}[!] /etc/ld.so.preload ПОЯВИЛСЯ СНОВА\n"; FOUND=1
fi

# 2) .php внутри .git/objects (структурно невозможно для легита)
GOBJ=$(find /home/*/web -path "*/.git/objects/*" -name "*.php" 2>/dev/null | head -20)
if [ -n "$GOBJ" ]; then OUT="${OUT}[!] .php в .git/objects:\n${GOBJ}\n"; FOUND=1; fi

# 3) root-owned .php с plugin-именами в корне public_html и .well-known
PLUG=""
for D in $(ls -d /home/*/web/*/public_html 2>/dev/null); do
  PLUG="${PLUG}$(find "$D" -maxdepth 1 -name "*.php" -user root 2>/dev/null; find "$D/.well-known" -name "*.php" -user root 2>/dev/null)
"
done
PLUG=$(printf '%s' "$PLUG" | grep -iE "wp-|class-|loader|dispatcher|handler|registry|sanitiz|template-|resolver|init-|hook-|option-|setup-|widget-|theme-|meta-|term-|query-|router|page-|media-|enqueue|formatter|manager-|post-" | head -20)
if [ -n "$PLUG" ]; then OUT="${OUT}[!] подозрительные root-php в webroot:\n${PLUG}\n"; FOUND=1; fi

# 4) известная C2-сигнатура в корнях public_html (мелко, быстро)
SIG=$(grep -rlsI "uzak shell\|scarfacemarka\|snippets/6001061" /home/*/web/*/public_html/*.php 2>/dev/null | head -20)
if [ -n "$SIG" ]; then OUT="${OUT}[!] C2-сигнатура:\n${SIG}\n"; FOUND=1; fi

notify() {  # отправка в Telegram; токен/чат из защищённого $CONF (chmod 600)
  [ -f "$CONF" ] || return 0
  # shellcheck disable=SC1090
  . "$CONF"
  [ -n "${TG_TOKEN:-}" ] && [ -n "${TG_CHAT:-}" ] || return 0
  curl -s --max-time 15 "https://api.telegram.org/bot${TG_TOKEN}/sendMessage" \
    --data-urlencode "chat_id=${TG_CHAT}" \
    --data-urlencode "text=$1" >/dev/null 2>&1
}

if [ "$FOUND" -eq 1 ]; then
  printf "%s ALERT:\n%b\n" "$TS" "$OUT" >> "$LOG"
  notify "$(printf '🚨 IR-TRIPWIRE ALERT (%s) %s\n%b' "$(hostname)" "$TS" "$OUT")"
else
  echo "$TS ok" >> "$LOG"
fi
