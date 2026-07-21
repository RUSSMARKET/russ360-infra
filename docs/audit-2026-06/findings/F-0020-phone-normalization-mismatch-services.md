---
id: F-0020
flow: registration-auth
dimension: data-integrity
severity: P1
confidence: confirmed
services: [rusaiauth, rusaifin]
status: open
---
## Симптом
Телефон нормализуется по-разному в rusaiauth и rusaifin → рассинхрон ключа связи `identity_users`↔`users`: легаси-юзер с `phone='8...'` либо дублируется, либо не может завершить регистрацию (404 на set-password).

## Доказательства (file:line)
- `rusaiauth/app/Domain/Identity/Support/PhoneNormalizer.php:22-24` — конвертирует `8XXXXXXXXXX` → `7XXXXXXXXXX`.
- `rusaifin/app/Http/Controllers/Internal/Registration/RegistrationInternalController.php:116-118` — `normalizePhone`: `preg_replace('/[^0-9]+/','')` БЕЗ конверсии `8→7`. То же в `Internal/Users/SetPasswordController.php:35`.

## Триггер / repro
Легаси-пользователь rusaifin с `users.phone='8...'`. rusaiauth нормализует ввод в `7...`; `init` ищет `User::where('phone','7...')` — не находит → создаёт новую shell-запись `7...`, либо `set-password` `DB::table('users')->where('phone','7...')` даёт `affected=0` → 404 / `RuntimeException`.

## Корневая причина (гипотеза)
Дублирование логики нормализации без единого источника правды; rusaifin-копия неполная (нет `8→7`).

## Радиус поражения
Все легаси-юзеры с `users.phone` в формате `8...`; любой импорт с непривёденным форматом.

## Направление фикса (1-2 строки, НЕ реализовано)
Единый нормализатор (общий модуль или передавать уже-нормализованный `7...` из rusaiauth) + одноразово привести `users.phone` к `7...`.

## Проверка статуса

**2026-07-21 — сверено с `origin/main`: дефект НА МЕСТЕ.**
`RegistrationInternalController:137-140` нормализует телефон без конверсии `8→7`, тогда как `rusaiauth/PhoneNormalizer:22-24` конвертирует. Рассинхрон ключа сохраняется.
