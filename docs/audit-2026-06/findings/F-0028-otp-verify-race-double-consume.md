---
id: F-0028
flow: login-otp
dimension: correctness
severity: P2
confidence: likely
services: [rusaiauth]
status: open
---
## Симптом
Гонка на `otp/verify`: один валидный OTP может быть успешно «погашен» дважды при конкурентных запросах; счётчик `attempts` неатомарен → потеря инкрементов расширяет лимит брутфорса сверх `max_attempts`.

## Доказательства (file:line)
- `rusaiauth/app/Domain/Identity/Services/OtpService.php:60-88` — `verify()`: `->whereNull('consumed_at')->first()`, затем `Hash::check`, затем `$otp->update(['consumed_at'=>now()])`. Нет транзакции/`lockForUpdate`/атомарного `UPDATE ... WHERE consumed_at IS NULL` с проверкой affected-rows.
- `OtpService.php:80` — `attempts` increment вне атомарной операции.

## Триггер / repro
Два параллельных `POST /login/otp/verify` (или /recovery/code) с одним кодом читают строку до записи `consumed_at` → оба проходят `Hash::check` → две успешные сессии. Throttle 10/мин не спасает от одновременных.

## Корневая причина (гипотеза)
Read-modify-write без блокировки/атомарности.

## Радиус поражения
OTP-логин и recovery (общий OtpService). Окно узкое, но эксплуатируемо для обхода счётчика попыток.

## Направление фикса (1-2 строки, НЕ реализовано)
Атомарный `UPDATE otp_codes SET consumed_at=now() WHERE id=? AND consumed_at IS NULL` + действие по affected-rows; `attempts` через атомарный increment в транзакции.
