"""The `aegis` CLI (speckit T2): db migrations, ontology validation, and stubs for
audit verification (T6) and projection rebuild (T10)."""

from __future__ import annotations

from pathlib import Path

import typer

from aegis.logging import configure_logging

REPO_ROOT = Path(__file__).resolve().parents[1]

app = typer.Typer(help="Aegis platform CLI (see speckit/)", no_args_is_help=True)
db_app = typer.Typer(help="Database migrations (Alembic)", no_args_is_help=True)
ontology_app = typer.Typer(help="Ontology artifact tools", no_args_is_help=True)
audit_app = typer.Typer(help="Audit chain tools", no_args_is_help=True)
projections_app = typer.Typer(help="Projection builders", no_args_is_help=True)
app.add_typer(db_app, name="db")
app.add_typer(ontology_app, name="ontology")
app.add_typer(audit_app, name="audit")
app.add_typer(projections_app, name="projections")


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
def db_downgrade(revision: str = typer.Argument(..., help="Target revision, e.g. -1 or base")) -> None:
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
    path: Path = typer.Argument(None, help="Ontology YAML (default: AEGIS_ONTOLOGY_PATH)"),
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


@audit_app.command("verify")
def audit_verify() -> None:
    """Verify the audit hash chain. Implemented in T6."""
    typer.secho("audit verify: not implemented yet (speckit task T6)", fg=typer.colors.YELLOW, err=True)
    raise typer.Exit(code=2)


@projections_app.command("rebuild")
def projections_rebuild() -> None:
    """Rebuild all projections from the claim store (Article XIII). Implemented in T10."""
    typer.secho("projections rebuild: not implemented yet (speckit task T10)", fg=typer.colors.YELLOW, err=True)
    raise typer.Exit(code=2)


if __name__ == "__main__":
    app()
