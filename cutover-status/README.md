# Cutover status — Final Stage Cutover Cleanup

Эта директория — **source of truth для прогресса parallel-execute плана**, описанного в [`docs/final-stage-cutover-cleanup-sprint-plan.md`](../docs/final-stage-cutover-cleanup-sprint-plan.md).

## Конвенция

- Один файл на track: `<track-id>.md` (например, `track-a-observability-infra.md`).
- Каждый chat с Claude Code, который работает над треком, **в конце своей сессии коммитит обновление статуса** в свой файл.
- Конфликтов между параллельными chat'ами нет — разные файлы.

## Формат файла трека

```markdown
# Track <ID> — <name>

**Status:** not-started | in-progress | blocked | done
**Owner chat:** <короткое описание сессии или дата>
**Last update:** YYYY-MM-DD

## Done
- Что сделано (по дате обновления)

## In progress
- Что в работе сейчас

## Blocked
- Что блокирует (если есть)

## Next
- Следующий шаг

## Artifacts
- Ссылки на коммиты / PR / измененные файлы / dump'ы
```

## Быстрый обзор всех треков

```bash
cd /home/dolgan/russ360
cat cutover-status/*.md | less        # все треки разом
grep -A1 "Status:" cutover-status/*.md  # компактная сводка
```

## Правила обновления

- Обновляй статус в конце сессии Claude Code, не в начале.
- Не удаляй секции — если что-то стало неактуально, помечай `~~зачёркнуто~~` с причиной.
- Каждое обновление = commit. Это и audit trail, и crash-recovery (если ноут упал — git log покажет где остановился).
- Если track blocked — обязательно укажи причину и кто/что снимет блокер.
