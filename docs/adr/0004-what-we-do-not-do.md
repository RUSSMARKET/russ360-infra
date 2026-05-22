# ADR-0004: Что мы deliberately НЕ делаем

**Status:** accepted
**Date:** 2026-05-21

## Context

Микросервисная литература давит набором паттернов и инструментов: service mesh, event bus, distributed tracing, contract testing, k8s, полный observability stack. Каждый — может казаться «обязательным», но требует инфры, времени на освоение и постоянного внимания.

Solo-команда не может поддерживать всю обвязку без потери темпа на бизнес-задачах. При этом без явной фиксации **«мы это сознательно не делаем»** каждая новая статья или разговор провоцирует переоценку и архитектурный паралич.

Этот ADR — **анти-паралич-инструмент**: явный список того, что мы не внедряем сейчас, и условия, при которых решение пересматривается.

## Decision

Сознательно НЕ внедряем следующие технологии и паттерны до выполнения соответствующих триггеров:

- **Service mesh (Istio / Linkerd / Consul Connect).** Текущая инфра — жёсткие URL в `.env`, mTLS не нужен внутри одного хоста. Revisit if: появилась 2+ команда ИЛИ требование mTLS между сервисами.
- **Event bus (Kafka / RabbitMQ / NATS).** REST + dual-write покрывают текущие сценарии sync data exchange. Revisit if: появилась потребность fan-out событий в 3+ consumer'а ИЛИ real-time projections между сервисами.
- **Distributed tracing (Jaeger / Zipkin / OpenTelemetry).** Laravel log + grep справляются с текущим debugging. Revisit if: p95 latency cross-service стабильно > 1 сек ИЛИ появятся async-flow с 3+ хопами.
- **Contract testing (Pact / Spring Cloud Contract).** Контракты в одной голове + интеграционные тесты покрывают coverage. Revisit if: 2+ команда работает над shared контрактами.
- **Kubernetes.** Docker compose на одном сервере покрывает текущую нагрузку. Revisit if: появится потребность multi-host deployment или auto-scaling.
- ~~**Полный observability stack (Prometheus / Grafana / ELK).**~~ **Триггер сработал 2026-05-21:** incident detection latency стала бизнес-проблемой, перед Stage Final Cutover нужны глаза за критической операцией. Принят bootstrap-набор: GlitchTip + Prometheus + Loki + Grafana + Promtail + Node Exporter + Laravel exporter + Telegram alerts + UptimeRobot. Detailed план — `docs/final-stage-cutover-cleanup-sprint-plan.md` (Phase 0, Track A + B).
- **Multi-region deployment.** Вся клиентура в одном регионе, один дата-центр. Revisit if: появятся клиенты в других регионах с latency-чувствительностью.

## Alternatives

- **Внедрить «на всякий случай»** — преждевременная инвестиция, отвлекает от бизнеса, требует постоянного maintenance.
- **Не фиксировать решение, разбираться по случаю** — провоцирует архитектурный паралич при каждом упоминании в литературе.

## Consequences

**Получаем:** фокус на бизнес-логике, не на платформенной обвязке. Понятный код без abstraction layers поверх «вдруг понадобится». Защита от impostor-syndrome при чтении микросервисной литературы.

**Платим:** при росте команды или нагрузки часть из этого списка придётся внедрять (но это сознательный trade-off, не упущение — у каждого item есть свой trigger).

## Revisit if

- Сработал триггер любого item — пересматриваем именно этот item, не весь список.
- Появилась 2-я команда / 2-й разработчик — может потребоваться часть из списка для координации.

## Links

ADR-0001 (SOA)
