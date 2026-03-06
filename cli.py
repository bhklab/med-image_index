"""CLI tool for validating the med-image index."""

from pathlib import Path

import click

INDEXED_DATASETS_DIR = Path("indexed_datasets")


@click.group()
def cli():
    """med-image-index: validate the index."""
    pass


@cli.command()
@click.argument("collection_name", required=False, default=None)
def validate(collection_name):
    """Validate that the index is compatible with imgnet.

    If COLLECTION_NAME is given, validates that single collection.
    Otherwise validates all collections.
    """
    if collection_name:
        ok = _validate_collection(collection_name)
    else:
        ok = _validate_all()

    if ok:
        click.echo("\nValidation passed.")
    else:
        click.echo("\nValidation FAILED.", err=True)
        raise SystemExit(1)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _validate_collection(collection_name):
    """Validate a single collection. Returns True if valid."""
    from imgnet.collections.store import IndexedDatasets

    ok = True
    try:
        indexed_datasets = IndexedDatasets(str(INDEXED_DATASETS_DIR))
    except FileNotFoundError:
        click.echo(f"  ERROR: {INDEXED_DATASETS_DIR} not found.", err=True)
        return False

    if collection_name not in indexed_datasets.collections:
        click.echo(f"  ERROR: '{collection_name}' not in collections list.", err=True)
        return False

    try:
        indexed_datasets.source_config(collection_name)
        click.echo(f"  [{collection_name}] source.json: OK")
    except Exception as e:
        click.echo(f"  [{collection_name}] source.json: FAILED ({e})", err=True)
        ok = False

    try:
        df = indexed_datasets.index(collection_name)
        if df.empty:
            click.echo(f"  [{collection_name}] index.csv: FAILED (empty DataFrame)", err=True)
            ok = False
        else:
            click.echo(f"  [{collection_name}] index.csv: OK ({len(df)} rows)")
            for col in ["filepath", "PatientID"]:
                if col not in df.columns:
                    click.echo(f"  [{collection_name}] index.csv: WARNING missing column '{col}'", err=True)
    except Exception as e:
        click.echo(f"  [{collection_name}] index.csv: FAILED ({e})", err=True)
        ok = False

    return ok


def _validate_all():
    """Validate all collections. Returns True if all valid."""
    from imgnet.collections.store import IndexedDatasets

    try:
        indexed_datasets = IndexedDatasets(str(INDEXED_DATASETS_DIR))
    except FileNotFoundError:
        click.echo(f"  ERROR: {INDEXED_DATASETS_DIR} not found.", err=True)
        return False

    all_ok = True
    for name in indexed_datasets.collections:
        ok = _validate_collection(name)
        if not ok:
            all_ok = False
    return all_ok


if __name__ == "__main__":
    cli()
