# ADR-0002: rusaiauth как identity boundary

**Status:** accepted
**Date:** 2026-05-21

## Context

В deliberate SOA с shared identity (ADR-0001) нужно решить: где живёт identity provider?

Если auth внутри одного из доменных сервисов — компрометация этого сервиса даёт атакующему доступ ко всем остальным (общий issuer, единый ключ подписи). Если auth размазан между сервисами (каждый со своей таблицей `users`) — нет SSO, drift, повторные логины. Если внешний IdP — чужой стек или vendor lock.

## Decision

`rusaiauth` — отдельный Laravel-сервис на базе Passport (OAuth2/OIDC, RS256 JWT). Остальные сервисы — resource servers, проверяющие JWT через JWKS endpoint. У rusaiauth своя БД, свой жизненный цикл, своя зона ответственности — identity и nothing else.

## Alternatives

- **Auth внутри rusaifin** — fin получает несвойственную ответственность; его взлом = доступ ко всем сервисам.
- **Sanctum в каждом сервисе** — нет SSO, нет единого ключа подписи, нет общей identity.
- **Внешний Keycloak / Authentik / Auth0** — чужой стек (Java/Python) или vendor lock + платность.

## Consequences

**Получаем:** security boundary (компрометация доменного сервиса не даёт токены), отдельный жизненный цикл (ротация ключей, аудит, deploy отдельно от доменных сервисов), SSO для всех frontend и сервисов, готовность к OIDC-стандартным интеграциям.

**Платим:** дополнительный сервис в инфре, JWT validation overhead на каждом cross-service запросе, JWKS caching/refresh coordination, дополнительная точка отказа (если auth недоступен — все вызовы 401).

## Revisit if

Это решение **не пересматривается**. Слияние auth обратно в один из доменных сервисов отвергается по security и compliance.

## Links

ADR-0001 (SOA), ADR-0003 (big-bang cutovers)
