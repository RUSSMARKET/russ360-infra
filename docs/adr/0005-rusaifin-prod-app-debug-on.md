# ADR-0005: На rusaifin prod APP_DEBUG=true оставлен намеренно

**Status:** accepted
**Date:** 2026-05-22

## Context

В Laravel `APP_DEBUG=true` показывает Ignition-страницу со stack trace, query log и dump переменных при exception в HTTP-ответе. По умолчанию prod-best-practice — `APP_DEBUG=false` (Whoops-страница раскрывает пути файлов, частично — содержимое `.env`, помогает атакующему).

На rusaifin prod (`server.rusaifin.ru`) `APP_DEBUG=true` стоит. Это вызывает регулярные предложения «выключить» при аудитах конфигурации. Этот ADR фиксирует: **оставить включённым**, и почему.

## Decision

На rusaifin prod `APP_DEBUG=true` остаётся включённым. На rusaicore / rusaiauth / rusaisklad_back prod — `APP_DEBUG=false` (там нужды в стектрейсах по скриншотам нет).

## Alternatives

- **Выключить как везде** — теряем главный канал debug'а: агент пришлёт скрин с Ignition, по стектрейсу автор видит причину за секунды без `tail -f laravel.log` и попыток воспроизвести.
- **Custom error handler с redacted-Ignition только для админ-IP** — лишний код и поверхность для багов в кастомной фильтрации; обычные агенты ходят с мобильного IP, белый список не работает.
- **Sentry/GlitchTip + слать стектрейс автору** — будет внедрено как часть Phase 0 observability (Track A/B), но не **заменяет** ситуацию «агент в поле, экран с ошибкой» — agent не открывает Sentry, а скрин шлёт.

## Consequences

**Получаем:** мгновенный debug по скриншоту от агента с поля. Окупается каждый раз, когда без него пришлось бы воспроизводить редкий side-effect.

**Платим:** Ignition-страница содержит пути файлов, фрагменты query, имена переменных. Mitigation:
- Nginx (Hestia) возвращает 404 на `/.env`, `/.git/*`, `/storage/*` (проверено 2026-05-22).
- Никаких credentials в исходном коде / в exception-сообщениях.
- `APP_KEY`, БД-пароли — только в `.env`, недоступны через web.

## Revisit if

- Появится observability stack с Sentry + workflow «агент пишет в Telegram → автор открывает Sentry» (Phase 0 завершён + неделя baseline). Тогда выключаем.
- Какой-то компонент начинает протекать чувствительные данные в exception-сообщения (credentials в SQL, токены в headers). Тогда — закрываем точечно.

## Links

ADR-0004 (что мы deliberately НЕ делаем — observability там тоже упомянут).
