---
id: F-0100
flow: webhooks
dimension: architecture-drift
severity: P2
confidence: confirmed
services: [rusaifin]
status: open
---

## Симптом
Все три webhook-роута аутентифицируются статичным секретом в URL-пути (нет HMAC/signature, нет middleware), используют GET для мутирующих операций и не имеют идемпотентности → повторная доставка/случайный префетч = повторная обработка.

## Доказательства (file:line)
- `rusaifin/routes/api.php:548-550` — три GET-роута: `import-ruchnik`, `clear`, `magnit-export`; аутентификация = literal-секрет в path, без middleware.
- `import-ruchnik` (`ImportService::Ruchnik()`) и `magnit-export` (dispatch job) — повторный вызов = повторная обработка/дубль постановки в очередь, дедупликации нет.

## Триггер / repro
Кэширующие прокси/префетчеры/сканеры/повторная доставка дёргают GET-`import-ruchnik` → повторный импорт; `magnit-export` → дубль job в очереди. Секрет из логов/Referer переиспользуется кем угодно.

## Корневая причина (гипотеза)
Webhook-auth = знание секрета в URL (логируется); мутирующие операции на GET; нет idempotency-key/lock.

## Радиус поражения
Дубли импорта/экспорта; компрометация секрета через логи. См. F-0099 (тот же класс, но с порчей данных).

## Направление фикса
Вынести секрет в заголовок + `hash_equals`; перевести мутирующие на POST; добавить idempotency-key/distributed lock (Redis — кандидат по memory).
