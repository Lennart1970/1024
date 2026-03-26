# BRAIN.md - Shared Brain Rules

This workspace is the shared brain for bots working here.

## Canonical locations

- `TRAINING_SOURCES.md` = root index for reusable training/reference sources
- `brain-sources/` = durable source library
- `PROJECTS.md` = current work status and next steps
- `memory/YYYY-MM-DD.md` = daily raw log

## Default behavior for bots

Before designing training, prompts, workflows, or agent architecture:

1. Read `TRAINING_SOURCES.md`
2. Read relevant files from `brain-sources/`
3. Check `PROJECTS.md` for active work
4. Record meaningful outcomes back into files, not just chat

## Rules

- Treat files as durable memory; treat chat as temporary context.
- If something should survive across channels or bots, write it to the repo.
- Do not claim a source file was used for literal model training unless that actually happened.
- Prefer updating shared files at task end:
  - source docs
  - project status
  - daily memory

## Bot shorthand

If you need shared knowledge, check here first:
- `BRAIN.md`
- `TRAINING_SOURCES.md`
- `brain-sources/`
