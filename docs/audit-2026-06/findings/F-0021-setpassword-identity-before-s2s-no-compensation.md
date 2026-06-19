---
id: F-0021
flow: registration-auth
dimension: data-integrity
severity: P1
confidence: confirmed
services: [rusaiauth, rusaifin]
status: open
---
## Симптом
На финальном шаге регистрации `identity_users.password_hash` записывается ДО S2S-вызова в rusaifin, без транзакции/компенсации. При недоступности rusaifin пользователь получает частичную регистрацию: пароль есть в identity, но не в `users` rusaifin.

## Доказательства (file:line)
- `rusaiauth/app/Http/Controllers/Auth/Registration/RegistrationController.php:192-196` — сначала `$user->update(['password_hash' => ...])`, затем `$this->rusaifin->setPassword(...)`. Обёртки `DB::transaction` нет.
- `rusaiauth/app/Domain/Identity/Support/Rusaifin/RusaifinInternalClient.php:83-92` — `ensureOk` бросает `RuntimeException` на не-2xx (httpTimeout≈5с).

## Триггер / repro
rusaifin недоступен/таймаут или вернул 404 (`user_not_found`, в т.ч. из-за phone-mismatch F-0020) на set-password → `identity_users.password_hash` уже записан → юзер может логиниться через rusaiauth по паролю, но `users.password` в rusaifin пуст/старый → guard rusaifin/sklad ведут себя несогласованно. Повтор setPassword требует валидную OTP-сессию (уже consumed) → 500.

## Корневая причина (гипотеза)
Нет распределённой транзакции/компенсации/ретрая; порядок «локально→удалённо» оставляет identity-сторону записанной при отказе удалённой.

## Радиус поражения
Любой setPassword в окно недоступности rusaifin или при phone-mismatch.

## Направление фикса (1-2 строки, НЕ реализовано)
Идемпотентный outbox/ретрай set-password; либо порядок «сначала rusaifin, потом identity»; либо метка identity «не завершён» до подтверждения rusaifin.
