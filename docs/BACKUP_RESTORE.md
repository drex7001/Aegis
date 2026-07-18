# Backup & Restore Runbook (speckit T15)

Covers the two stateful stores: the PostgreSQL claim store (source of truth) and
the MinIO evidence vault (content-addressed originals + provenance). OpenFGA and
Keycloak hold **projections/config** — FGA is rebuilt from Postgres
(`aegis authz rebuild`) and the Keycloak realm is re-imported from
`infra/keycloak/aegis-realm.json`, so neither is part of the data backup.

## What is backed up

| Store | Contents | Tool |
|---|---|---|
| PostgreSQL `aegis` | claims, entities, sources, cases, evidence rows, **audit_log** | `pg_dump -Fc` |
| MinIO `evidence` / `raw-landing` / `exports` | vault objects + `.provenance.json` sidecars | `mc mirror` |

Not backed up (derived/config, reproducible): the `edge_projection` and
`entity_canonical_map` tables, `output/*.json`, FGA tuples, Keycloak realm.
Both tables are rebuilt from claims and the identity ledger (Article XIII), so
losing them loses nothing — but they must be rebuilt *after* restore, not
assumed present.

## Backup

```bash
bash scripts/backup.sh                 # → backups/<UTC-timestamp>/
bash scripts/backup.sh /path/to/dest   # explicit destination
```

Produces `db.dump` (custom-format archive), `vault/<bucket>/…`, and
`manifest.json`. **Encrypt at rest** (`age`/`gpg`) before moving off-box — the
vault contains real names from public reporting; treat as `restricted`
(spec 03 §7).

## Restore (into a clean stack)

```bash
make nuke up bootstrap                  # fresh Postgres + MinIO + FGA store/model
bash scripts/restore.sh backups/<UTC-timestamp>
```

`restore.sh` is **destructive**: it drops and recreates the target database,
`pg_restore`s the dump, mirrors the vault buckets back, then:

1. `aegis projections rebuild` — rebuilds `entity_canonical_map`, then
   `edge_projection`, then `output/real_graph.json` (that order matters: edges
   resolve their endpoints through the map);
2. `aegis audit verify` — confirms the hash chain survived the round-trip;
3. (run manually if FGA tuples are needed) `aegis authz rebuild` — re-derives the
   FGA tuple set from the restored `case_member` / evidence rows.

## Drill acceptance (T15)

A restore is successful when, against the restored stack:

- `aegis audit verify` reports the chain valid over the same row count as the source;
- `aegis projections rebuild` reproduces the graph (node/edge counts match);
- row counts for `entity`, `claim`, `source_record` match the pre-backup store.

## Notes & Windows

- Scripts are POSIX `sh`/`bash`; on Windows run them from Git Bash. They probe
  for a working `python`/`python3` (the Store shim is skipped).
- `pg_restore --no-owner` maps objects to the restoring role; the app/audit
  grants are re-applied by the migration role, not the dump.
- For a point-in-time or larger deployment, replace `pg_dump` with WAL archiving
  and MinIO bucket replication (Phase 2+).
