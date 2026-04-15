# Post-Migration Refinement

You are reviewing the results of an OpenClaw → Hermes migration.

## Context

The migration was run with `hermes claw migrate`. Archived items (things with no direct Hermes equivalent) were saved under:

```
/opt/data/migration/openclaw/*/archive/
```

Your data directory is `/opt/data/`.

## Task

### 1. Read the migration summary

```bash
cat /opt/data/migration/openclaw/*/summary.md
```

### 2. Read each archived file and take action

Go through every file in the archive directory. Use this mapping to decide what to do with each one:

| Archived File | Hermes Equivalent | What To Do |
|---|---|---|
| `workspace/IDENTITY.md` | `SOUL.md` | Read both files. Merge any missing personality/identity info into `/opt/data/SOUL.md` |
| `workspace/TOOLS.md` | Built-in tools | Check if any custom tool instructions should become a skill in `/opt/data/skills/` |
| `workspace/HEARTBEAT.md` | Cron jobs | For each periodic task, create it with `hermes cron create` |
| `workspace/BOOTSTRAP.md` | Context files / skills | Convert to a skill or context file in `/opt/data/skills/` |
| `plugins-config.json` | Hermes plugins | List what was installed, check `hermes plugins list` for equivalents |
| `hooks-config.json` | Hermes webhooks | Create equivalents with `hermes webhook create` |
| `skills-registry-config.json` | Hermes skills | Cross-reference with `hermes skills list` |
| `ui-identity-config.json` | `/skin` command | Apply skin settings if relevant |
| `agents-list.json` | Hermes profiles | Create profiles with `hermes profile create` |
| `channels-deep-config.json` | Platform config | List what needs manual setup per platform |
| `gateway-config.json` | API server config | Compare with `/opt/data/config.yaml` — note any differences |
| `tools-config.json` | Tool config | Check if any tool settings need transferring to config.yaml |
| `model-aliases.json` | Model config | Suggest entries for the `model` section of `/opt/data/config.yaml` |
| `browser-config.json` | Already migrated | Verify the `browser` section in `/opt/data/config.yaml` looks right |
| `workspace/memory/*.md` | MEMORY.md | Verify daily memories were merged into `/opt/data/memories/` |

### 3. Verify current state

Run these to confirm things are working:

```bash
hermes status
hermes skills list
hermes config get model
hermes cron list
```

### 4. Output a checklist

After reviewing everything, give me a prioritized checklist of manual actions still needed, if any.

## Important Notes

- API keys are NOT needed in Hermes — all LLM requests go through ClawRoute (`http://clawroute:18790/v1`)
- Your config lives at `/opt/data/config.yaml`
- Your soul/personality is at `/opt/data/SOUL.md`
- Skills live in `/opt/data/skills/`
- Memories live in `/opt/data/memories/`
