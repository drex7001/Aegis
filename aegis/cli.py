"""The ``aegis`` platform command line."""

from __future__ import annotations

import ipaddress
from pathlib import Path

import typer

from aegis.logging import configure_logging

REPO_ROOT = Path(__file__).resolve().parents[1]

app = typer.Typer(help="Aegis platform CLI (see speckit/)", no_args_is_help=True)
db_app = typer.Typer(help="Database migrations (Alembic)", no_args_is_help=True)
ontology_app = typer.Typer(help="Ontology artifact tools", no_args_is_help=True)
audit_app = typer.Typer(help="Audit chain tools", no_args_is_help=True)
api_app = typer.Typer(help="API document tools", no_args_is_help=True)
projections_app = typer.Typer(help="Projection builders", no_args_is_help=True)
ingest_app = typer.Typer(
    help="Raw landing + extraction passes (spec 04)", no_args_is_help=True
)
authz_app = typer.Typer(help="OpenFGA projection tools (ADR-014)", no_args_is_help=True)
identity_app = typer.Typer(
    help="Identity ledger maintenance (spec 05)", no_args_is_help=True
)
app.add_typer(db_app, name="db")
app.add_typer(ontology_app, name="ontology")
app.add_typer(audit_app, name="audit")
app.add_typer(api_app, name="api")
app.add_typer(projections_app, name="projections")
app.add_typer(ingest_app, name="ingest")
app.add_typer(authz_app, name="authz")
app.add_typer(identity_app, name="identity")


@app.callback()
def _main() -> None:
    configure_logging()


def _alembic_config():
    from alembic.config import Config

    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "migrations"))
    return cfg


@db_app.command("upgrade")
def db_upgrade(revision: str = typer.Argument("head")) -> None:
    """Apply migrations up to REVISION (default: head)."""
    from alembic import command

    command.upgrade(_alembic_config(), revision)
    typer.echo(f"database upgraded to {revision}")


@db_app.command("downgrade")
def db_downgrade(
    revision: str = typer.Argument(..., help="Target revision, e.g. -1 or base"),
) -> None:
    from alembic import command

    command.downgrade(_alembic_config(), revision)
    typer.echo(f"database downgraded to {revision}")


@db_app.command("current")
def db_current() -> None:
    from alembic import command

    command.current(_alembic_config(), verbose=True)


@db_app.command("revision")
def db_revision(message: str = typer.Option(..., "-m", "--message")) -> None:
    from alembic import command

    command.revision(_alembic_config(), message=message)


@ontology_app.command("validate")
def ontology_validate(
    path: Path = typer.Argument(
        None, help="Ontology YAML (default: AEGIS_ONTOLOGY_PATH)"
    ),
) -> None:
    """Validate the ontology artifact; exit 1 with precise errors on failure."""
    from aegis.config import get_settings
    from aegis.ontology import OntologyValidationError, load

    target = path or REPO_ROOT / get_settings().ontology_path
    try:
        ont = load(target)
    except OntologyValidationError as exc:
        typer.secho(f"INVALID: {target}", fg=typer.colors.RED, err=True)
        for error in exc.errors:
            typer.secho(f"  - {error}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    typer.secho(
        f"OK: {target} (v{ont.version}) — "
        f"{len(ont.object_types)} object types, {len(ont.predicates)} predicates, "
        f"{len(ont.categories)} categories, {len(ont.actions)} actions",
        fg=typer.colors.GREEN,
    )


@api_app.command("export-openapi")
def api_export_openapi(
    out: Path = typer.Option(
        REPO_ROOT / "ui" / "openapi.json",
        "--out",
        help="Where to write the OpenAPI document.",
    ),
) -> None:
    """Write the OpenAPI document the workspace's typed client is built from.

    Committed rather than fetched at build time (ADR-032 §2): the UI build then
    needs no running API, and ``tests/contract/test_openapi.py`` can fail on
    drift between the document and the routes — which is the actual risk, since
    a stale document produces a client that type-checks and 404s.
    """
    import json

    from aegis.api import create_app

    document = create_app().openapi()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(document, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    paths = sum(len(item) for item in document["paths"].values())
    typer.secho(f"wrote {out} ({paths} operations)", fg=typer.colors.GREEN)


@audit_app.command("verify")
def audit_verify() -> None:
    """Recompute the audit hash chain and fail at the first altered row."""
    from aegis.audit import verify
    from aegis.store import get_sessionmaker

    with get_sessionmaker()() as session:
        report = verify(session)
    if not report.valid:
        typer.secho(
            f"INVALID: audit chain failed at row {report.failed_id} after "
            f"{report.checked} verified row(s): {report.reason}",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1)
    typer.secho(
        f"OK: audit chain valid ({report.checked} row(s))", fg=typer.colors.GREEN
    )


@app.command("serve")
def serve(
    host: str = typer.Option("127.0.0.1", help="Bind address."),
    port: int = typer.Option(8000, help="Port."),
    reload: bool = typer.Option(False, "--reload", help="Auto-reload (dev)."),
    allow_non_loopback: bool = typer.Option(
        False,
        "--allow-non-loopback",
        help="Explicitly allow a non-loopback bind (unsafe before the pilot gate).",
    ),
) -> None:
    """Run the governed API and, when built, the workspace bundle (T13/T22).

    The loopback default survives T22 even though no anonymous route does: the
    remaining reasons to refuse a public bind are TLS, secrets hygiene, and
    request limits — the pilot gate (ADR-033 §4), not ADR-026.
    """
    normalized_host = host.strip().lower().strip("[]")
    try:
        loopback = ipaddress.ip_address(normalized_host).is_loopback
    except ValueError:
        loopback = normalized_host == "localhost"
    if not loopback and not allow_non_loopback:
        raise typer.BadParameter(
            "non-loopback binds are refused by default; pass "
            "--allow-non-loopback only after applying the pilot security gate",
            param_hint="--host",
        )
    if not loopback:
        import structlog

        structlog.get_logger(__name__).warning(
            "non_loopback_bind_enabled",
            host=host,
            warning="the pilot security gate (TLS, secrets, backups) is not verified here",
        )
        typer.secho(
            "WARNING: non-loopback bind explicitly enabled before the pilot "
            "security gate (ADR-033 §4).",
            fg=typer.colors.YELLOW,
            err=True,
        )
    import uvicorn

    typer.secho(
        f"aegis API on http://{host}:{port}  (docs at /docs)", fg=typer.colors.GREEN
    )
    uvicorn.run(
        "aegis.api:create_app" if not reload else "aegis.api:create_app",
        factory=True,
        host=host,
        port=port,
        reload=reload,
    )


@app.command("migrate-legacy")
def migrate_legacy(
    report_path: Path = typer.Option(
        Path("output/migration_report.json"),
        "--report",
        help="Where to write the migration report JSON.",
    ),
    actor: str = typer.Option("system:migrate-legacy", help="Audit actor for the run."),
) -> None:
    """Migrate the curated legacy dataset into the claim store (T8, idempotent)."""
    import json

    from aegis.migration import LegacyMigrationError, migrate
    from aegis.store import get_sessionmaker

    try:
        with get_sessionmaker()() as session:
            report = migrate(session, actor=actor)
    except LegacyMigrationError as exc:
        typer.secho(f"MIGRATION FAILED: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8"
    )
    d = report.to_dict()
    typer.secho(
        "migrate-legacy OK: "
        f"{d['entities']['created']} entities created ({d['entities']['existing']} existing), "
        f"{report.claims_created} claims created "
        f"({d['node_claims']['existing'] + d['edge_claims']['existing']} existing), "
        f"{d['edges_total']} legacy edges → {len(d['remap_log'])} remap entries "
        f"({len(d['splits'])} splits, {len(d['credibility_caps'])} caps, "
        f"{len(d['category_corrections'])} category corrections)",
        fg=typer.colors.GREEN,
    )
    typer.echo(f"report: {report_path}")


@projections_app.command("rebuild")
def projections_rebuild(
    output_dir: Path = typer.Option(
        Path("output"),
        "--output",
        help="Directory for real_graph.json / real_ingest.cypher.",
    ),
) -> None:
    """Rebuild every projection from canonical state (Article XIII, T10/T21).

    Order matters and is not incidental: edges resolve their endpoints through
    ``entity_canonical_map``, so the map is rebuilt from the ledger first.
    Rebuilding edges against a stale map would resolve identity as it was at
    the last adjudication rather than as it is now.
    """
    from aegis.config import get_settings
    from aegis.er.canonical import rebuild_canonical_map
    from aegis.ontology import load
    from aegis.projections import (
        build_full_graph,
        rebuild_edge_projection,
        write_outputs,
    )
    from aegis.store import get_sessionmaker

    settings = get_settings()
    ontology_path = Path(settings.ontology_path)
    ontology = load(
        ontology_path if ontology_path.is_absolute() else REPO_ROOT / ontology_path
    )
    with get_sessionmaker()() as session:
        identity = rebuild_canonical_map(session)
        edges = rebuild_edge_projection(session, ontology=ontology)
        session.commit()
        graph = build_full_graph(session, ontology)
    written = write_outputs(graph, output_dir)
    typer.secho(
        f"projections rebuilt: {edges.edges} edges over {edges.segments} segments, "
        f"{identity.entities} entities ({identity.merged} merged, "
        f"{identity.tombstoned} tombstoned), {len(graph['cells'])} cells",
        fg=typer.colors.GREEN,
    )
    typer.echo(
        f"  stamped: revision {edges.built_at_revision_id}, "
        f"ontology {edges.ontology_version}, builder {edges.builder_version}"
    )
    for path in written:
        typer.echo(f"  wrote {path}")


@authz_app.command("sync")
def authz_sync(
    limit: int = typer.Option(None, "--limit", help="Drain at most N outbox rows."),
) -> None:
    """Drain pending authz_outbox rows into OpenFGA (in order; stops on failure)."""
    from aegis.authz import FGAClient, sync
    from aegis.store import get_sessionmaker

    fga = FGAClient()
    with get_sessionmaker()() as session:
        report = sync(session, fga, limit=limit)
    if not report.ok:
        typer.secho(
            f"sync stopped at outbox row {report.failed_id} after {report.processed} "
            f"row(s): {report.error} ({report.pending} still pending)",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1)
    typer.secho(
        f"authz sync OK: {report.processed} row(s) drained", fg=typer.colors.GREEN
    )


@authz_app.command("rebuild")
def authz_rebuild() -> None:
    """Re-derive the full FGA tuple set from Postgres alone (Article XIII)."""
    from aegis.authz import FGAClient, rebuild
    from aegis.store import get_sessionmaker

    fga = FGAClient()
    with get_sessionmaker()() as session:
        report = rebuild(session, fga)
    typer.secho(
        f"authz rebuild OK: {report.desired} desired tuple(s) — "
        f"{report.written} written, {report.deleted} stale deleted, "
        f"{report.superseded_outbox_rows} outbox row(s) superseded",
        fg=typer.colors.GREEN,
    )


@identity_app.command("run-rules")
def identity_run_rules(
    record_id: str = typer.Option(
        None, "--record", help="Limit the same-document rule to one source record."
    ),
) -> None:
    """Run deterministic ER rules, emitting candidates for human adjudication.

    Emits candidates only — nothing here merges anything (ADR-027).  Safe to
    re-run: a pair that already has a candidate is not proposed twice, and a
    pair a reviewer rejected is not proposed again at all.
    """
    from aegis.config import get_settings
    from aegis.er.rules import run_rules
    from aegis.ontology import load
    from aegis.store import get_sessionmaker

    settings = get_settings()
    ontology_path = Path(settings.ontology_path)
    ontology = load(
        ontology_path if ontology_path.is_absolute() else REPO_ROOT / ontology_path
    )
    with get_sessionmaker()() as session:
        report = run_rules(session, ontology=ontology, record_id=record_id)
        session.commit()
    typer.secho(
        f"emitted {report.emitted} candidates ({report.pre_verified} pre-verified)",
        fg=typer.colors.GREEN,
    )
    typer.echo(
        f"  skipped: {report.already_open} already awaiting review, "
        f"{report.same_entity} already one entity"
    )
    typer.echo(
        f"  suppressed: {report.suppressed_conflict} identifier conflicts (H-07), "
        f"{report.suppressed_constraint} previously rejected pairs"
    )


@identity_app.command("run-splink")
def identity_run_splink(
    threshold: float = typer.Option(
        None, "--threshold", help="Override the emission threshold (spec 05 §6)."
    ),
) -> None:
    """Score mention pairs with Splink, emitting candidates above threshold.

    Emits candidates only — nothing here merges anything (ADR-027).  Each
    candidate records the settings version and the graph snapshot its context
    features were computed against, so the score is reproducible (H-07).
    """
    from aegis.er.settings import SPLINK_MATCH_THRESHOLD
    from aegis.er.splink_job import run_splink
    from aegis.store import get_sessionmaker

    with get_sessionmaker()() as session:
        report = run_splink(
            session,
            threshold=threshold if threshold is not None else SPLINK_MATCH_THRESHOLD,
        )
        session.commit()
    typer.secho(
        f"emitted {report.emitted} candidates from {report.compared} scored pairs",
        fg=typer.colors.GREEN,
    )
    typer.echo(
        f"  skipped: {report.below_threshold} below threshold, "
        f"{report.same_entity} already one entity, {report.already_open} already open"
    )
    typer.echo(
        f"  suppressed: {report.suppressed_constraint} previously rejected pairs"
    )
    typer.echo(
        f"  settings: {report.settings_version}  snapshot: {report.graph_snapshot_id}"
    )


@identity_app.command("backfill-anchors")
def identity_backfill_anchors(
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Report what would be anchored without writing."
    ),
) -> None:
    """Anchor pre-T17 claims to their mentions where the evidence is unambiguous.

    Heuristic and lossy by construction — Phase-1 claims never recorded the
    mention they came from (spec 02 §3.1).  Ambiguous claims are reported and
    left unanchored rather than guessed.  Safe to re-run.
    """
    from aegis.er.backfill import backfill_anchors
    from aegis.store import get_sessionmaker

    with get_sessionmaker()() as session:
        report = backfill_anchors(session)
        if dry_run:
            session.rollback()
        else:
            session.commit()
    typer.secho(
        f"{'would anchor' if dry_run else 'anchored'} {report.anchored} of "
        f"{report.considered} unanchored claims",
        fg=typer.colors.GREEN,
    )
    typer.echo(
        f"  left unanchored: {report.left_unanchored} "
        f"({report.ambiguous} ambiguous, {report.unmatched} with no mention in record)"
    )
    if report.ambiguous_claims:
        typer.echo(
            "  ambiguous sample: " + ", ".join(report.to_dict()["ambiguous_sample"])
        )
        typer.echo(
            "  these follow the re-adjudication path on a split, by design "
            "(spec 02 §3.1 rule 4)"
        )


@ingest_app.command("land")
def ingest_land(
    paths: list[Path] = typer.Argument(..., help="Files or directories to land."),
    operator: str = typer.Option(
        ..., "--operator", help="Acting user, e.g. user:ayodhya"
    ),
    source_id: str = typer.Option(
        None,
        "--source-id",
        help="Existing source row (default: the manual-upload source).",
    ),
    handling_code: str = typer.Option("open", "--handling"),
) -> None:
    """Land raw files: bytes → vault, provenance envelope, source_record row."""
    from aegis.evidence import get_vault
    from aegis.ingestion import IngestionError, land_file
    from aegis.store import get_sessionmaker

    files: list[Path] = []
    for path in paths:
        if path.is_dir():
            files.extend(p for p in sorted(path.rglob("*")) if p.is_file())
        elif path.is_file():
            files.append(path)
        else:
            typer.secho(f"skip {path}: not found", fg=typer.colors.YELLOW, err=True)
    if not files:
        typer.secho("nothing to land", fg=typer.colors.YELLOW, err=True)
        raise typer.Exit(code=1)

    vault = get_vault()
    with get_sessionmaker()() as session:
        for path in files:
            try:
                result = land_file(
                    session,
                    vault,
                    path=path,
                    operator=operator,
                    source_id=source_id,
                    handling_code=handling_code,
                )
            except IngestionError as exc:
                typer.secho(f"FAIL {path.name}: {exc}", fg=typer.colors.RED, err=True)
                raise typer.Exit(code=1) from exc
            state = (
                "QUARANTINED"
                if result.quarantined
                else ("landed" if result.created else "already landed")
            )
            typer.echo(f"{state}: {path.name} → {result.record.record_id}")


@ingest_app.command("status")
def ingest_status() -> None:
    """Landed/quarantined/processed counts + open quarantine reasons."""
    import sqlalchemy as sa

    from aegis.store import SourceRecord, get_sessionmaker

    with get_sessionmaker()() as session:
        counts = dict(
            session.execute(
                sa.select(SourceRecord.status, sa.func.count()).group_by(
                    SourceRecord.status
                )
            ).all()
        )
        typer.echo(
            "records: "
            + ", ".join(
                f"{status}={counts.get(status, 0)}"
                for status in ("landed", "quarantined", "processed")
            )
        )
        quarantined = session.scalars(
            sa.select(SourceRecord).where(SourceRecord.status == "quarantined")
        ).all()
        for record in quarantined:
            typer.secho(
                f"  {record.record_id}: {record.quarantine_reason}",
                fg=typer.colors.YELLOW,
            )


@ingest_app.command("mvp")
def ingest_mvp(
    reset: bool = typer.Option(
        False, "--reset", help="Restore the empty migrated baseline."
    ),
    yes: bool = typer.Option(
        False, "--yes", help="Confirm the destructive local reset."
    ),
    fixture_dir: Path = typer.Option(
        REPO_ROOT / "data" / "sample" / "mvp",
        "--fixture-dir",
        help="Committed fictional fixture directory.",
    ),
    output_dir: Path = typer.Option(
        Path("output/mvp"),
        "--output",
        help="Directory for rebuilt projection artifacts.",
    ),
    actor: str = typer.Option(
        "user:mvp-demo-operator",
        "--actor",
        help="Human operator recorded on curated fixture actions.",
    ),
) -> None:
    """Load the fully local fictional MVP corpus, or reset its disposable store."""
    from sqlalchemy.engine import make_url

    from aegis.config import get_settings
    from aegis.evidence import get_vault
    from aegis.ingestion import MvpFixtureError, load_mvp_fixture, reset_mvp_fixture
    from aegis.store import get_sessionmaker

    host = make_url(get_settings().database_url).host
    try:
        local = host is None or ipaddress.ip_address(host).is_loopback
    except ValueError:
        local = host == "localhost"
    if not local:
        typer.secho(
            "the MVP fixture is local-only and refuses a non-loopback database",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1)
    if reset and not yes:
        typer.secho(
            "--reset is destructive; repeat with --yes", fg=typer.colors.RED, err=True
        )
        raise typer.Exit(code=1)

    try:
        with get_sessionmaker()() as session:
            if reset:
                report = reset_mvp_fixture(session, output_dir=output_dir)
                typer.secho(
                    f"MVP baseline restored; projections rebuilt ({report.projection_edges} edges)",
                    fg=typer.colors.GREEN,
                )
                return
            report = load_mvp_fixture(
                session,
                get_vault(),
                root=fixture_dir,
                actor=actor,
                output_dir=output_dir,
            )
    except MvpFixtureError as exc:
        typer.secho(f"MVP fixture failed: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    typer.secho(
        f"MVP fixture ready: {report.records} records ({report.quarantined} quarantined), "
        f"{report.suggestions} new suggestions, {report.curated_claims} curated claims",
        fg=typer.colors.GREEN,
    )
    typer.echo(
        f"  candidates: rules={report.rule_candidates}, splink={report.splink_candidates}; "
        f"projection edges={report.projection_edges}"
    )


@ingest_app.command("extract")
def ingest_extract(
    record_id: str = typer.Argument(..., help="A landed source_record id."),
    producer: str = typer.Option(..., "--producer", help="structural or semantic"),
    actor: str = typer.Option(..., "--actor", help="Acting user, e.g. user:ayodhya"),
    model: str = typer.Option(
        None, "--model", help="semantic only: provider:model override"
    ),
    mock: bool = typer.Option(
        False, "--mock", help="semantic only: offline mock extraction"
    ),
    cached_output: Path = typer.Option(
        None,
        "--cached-output",
        help="semantic only: validated aegis.cached-semantic/v1 JSON (offline)",
    ),
) -> None:
    """Run an extraction pass over a landed record → review-queue suggestions.

    Never writes claims (Article VII): review with `review_suggestion`.
    """
    from aegis.evidence import get_vault
    from aegis.ingestion import (
        IngestionError,
        ensure_text,
        run_semantic_pass,
        run_structural_pass,
    )
    from aegis.store import SourceRecord, get_sessionmaker

    if producer not in {"structural", "semantic"}:
        typer.secho(
            "--producer must be structural or semantic", fg=typer.colors.RED, err=True
        )
        raise typer.Exit(code=1)
    if cached_output is not None and producer != "semantic":
        typer.secho(
            "--cached-output is only valid with --producer semantic",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1)
    if cached_output is not None and not cached_output.is_file():
        typer.secho(
            f"cached output not found: {cached_output}", fg=typer.colors.RED, err=True
        )
        raise typer.Exit(code=1)

    vault = get_vault()
    with get_sessionmaker()() as session:
        record = session.get(SourceRecord, record_id)
        if record is None:
            typer.secho(
                f"record {record_id!r} does not exist", fg=typer.colors.RED, err=True
            )
            raise typer.Exit(code=1)
        if record.status == "quarantined":
            typer.secho(
                f"record is quarantined ({record.quarantine_reason}); release it first",
                fg=typer.colors.RED,
                err=True,
            )
            raise typer.Exit(code=1)
        try:
            extraction = ensure_text(session, vault, record=record, operator=actor)
        except IngestionError as exc:
            typer.secho(str(exc), fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1) from exc
        if extraction.derivative is not None:
            typer.echo(
                f"derivative ({'new' if extraction.created else 'reused'}): "
                f"{extraction.derivative.derivative_id} via {extraction.tool} "
                f"{extraction.derivative.tool_version}"
            )
        text = extraction.text
        if producer == "structural":
            suggestions = run_structural_pass(
                session, record=record, text=text, actor=actor
            )
        else:
            suggestions = run_semantic_pass(
                session,
                vault,
                record=record,
                text=text,
                actor=actor,
                model_name=model,
                mock=mock,
                cached_output=cached_output.read_bytes()
                if cached_output is not None
                else None,
            )
        session.commit()
    typer.secho(
        f"{producer} pass over {record_id}: {len(suggestions)} suggestion(s) queued "
        "(0 claims written — Article VII)",
        fg=typer.colors.GREEN,
    )


if __name__ == "__main__":
    app()
