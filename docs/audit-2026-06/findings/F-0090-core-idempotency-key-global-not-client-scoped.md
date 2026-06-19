---
id: F-0090
flow: core-crud
dimension: data-integrity
severity: P3
confidence: confirmed
services: [rusaicore]
status: open
---

## Симптом
Idempotency-ключ хранится с `unique` только на `idempotency_key`, без привязки к `client_id`/`sub`. Два разных клиента, выбравших одинаковый ключ, пересекаются: при разном теле → `409 idempotency_key_reused`, при одинаковом — клиент B получит реплей ответа клиента A (тихая подмена/потеря записи).

## Доказательства (file:line)
- Миграция idempotency_keys — `unique` только на `idempotency_key` (нет `client_id` в ключе/индексе).
- `EnsureIdempotency.php:35` — поиск только по `idempotency_key`, без `client_id`.
- `EnsureIdempotency.php:66-73` — `fingerprint()` включает method+path+body, но НЕ клиента → ответ A может уехать B.

## Триггер / repro
Маловероятно при UUIDv4-ключах, но возможно при не-UUID/баге генерации у потребителя: клиент B шлёт тот же ключ с тем же fingerprint → получает закешированный ответ записи клиента A; контракт «ключ глобален» нигде не задокументирован для потребителей.

## Корневая причина (гипотеза)
Область уникальности ключа глобальна, а не per-client. Низкий риск при текущей дисциплине генерации.

## Радиус поражения
Кросс-клиентское пересечение идемпотентности; зависит от качества генерации ключей потребителями.

## Направление фикса
Добавить `client_id` (`$principal->clientId`) в fingerprint и/или в unique-scope ключа; задокументировать контракт ключа.
