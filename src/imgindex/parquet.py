"""Convert med-image index CSVs to hive-partitioned Parquet datasets.

Partitioning by ``Modality`` produces a directory layout that tools can filter
without scanning the full index, e.g.::

    parquet/Modality=CT/part-0.parquet
    parquet/Modality=MR/part-0.parquet
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

MODALITY_COLUMN = "Modality"
NULL_PARTITION_LABEL = "__null__"
DEFAULT_COMPRESSION = "zstd"
PARTITION_FILENAME_TEMPLATE = "part-{i}.parquet"

_UNSAFE_FILESYSTEM_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def load_index_csv(csv_path: Path | str) -> pd.DataFrame:
    """Load an index CSV into a DataFrame.

    Args:
        csv_path: Path to an index CSV (e.g. ``index.csv`` for one collection).

    Returns:
        Raw index data loaded from ``csv_path``.

    Notes:
        Assumes the CSV uses a header row and is readable by ``pandas.read_csv``.
    """
    return pd.read_csv(csv_path)


def sanitize_modality_for_partitioning(modality_values: pd.Series) -> pd.Series:
    """Sanitize Modality values for hive-style partition directory names.

    Hive partitioning embeds column values in paths (``Modality=<value>/``), so
    values must be valid single path segments. Null, empty, and whitespace-only
    values are mapped to ``__null__``; characters illegal on common filesystems
    are replaced with underscores.

    Args:
        modality_values: The ``Modality`` column from an index DataFrame.

    Returns:
        Sanitized modality labels suitable for ``partition_cols``.

    Notes:
        Assumes each value represents a single modality label, not a delimited list.
    """

    def sanitize_partition_value(value: object) -> str:
        if pd.isna(value) or value is None:
            return NULL_PARTITION_LABEL
        if isinstance(value, str) and not value.strip():
            return NULL_PARTITION_LABEL

        sanitized_value = str(value).strip()
        if not sanitized_value:
            return NULL_PARTITION_LABEL

        sanitized_value = _UNSAFE_FILESYSTEM_CHARS.sub("_", sanitized_value)
        return sanitized_value or NULL_PARTITION_LABEL

    return modality_values.map(sanitize_partition_value)


def prepare_index_for_parquet(index_df: pd.DataFrame) -> pd.DataFrame:
    """Prepare index data for Modality-partitioned Parquet export.

    Args:
        index_df: Raw index DataFrame loaded from CSV.

    Returns:
        A copy of ``index_df`` with a sanitized ``Modality`` column.

    Raises:
        ValueError: If ``Modality`` is not present in ``index_df``.

    Notes:
        Returns a copy to avoid mutating the caller's DataFrame.
    """
    if MODALITY_COLUMN not in index_df.columns:
        raise ValueError(f"missing required column {MODALITY_COLUMN!r}")

    prepared_index_df = index_df.copy()
    prepared_index_df[MODALITY_COLUMN] = sanitize_modality_for_partitioning(
        prepared_index_df[MODALITY_COLUMN]
    )
    return prepared_index_df


def write_modality_partitioned_parquet(
    index_df: pd.DataFrame,
    output_dir: Path | str,
    *,
    compression: str = DEFAULT_COMPRESSION,
) -> Path:
    """Write an index DataFrame as a Modality-partitioned Parquet dataset.

    Args:
        index_df: Prepared index data containing a sanitized ``Modality`` column.
        output_dir: Root directory for the Parquet dataset.
        compression: Parquet codec passed to PyArrow.

    Returns:
        ``output_dir`` after writing the dataset.

    Notes:
        Re-running over an existing ``output_dir`` overwrites matching partition
        files via PyArrow's ``overwrite_or_ignore`` behavior.
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    parquet_table = pa.Table.from_pandas(index_df, preserve_index=False)
    pq.write_to_dataset(
        parquet_table,
        root_path=str(output_path),
        partition_cols=[MODALITY_COLUMN],
        compression=compression,
        existing_data_behavior="overwrite_or_ignore",
        basename_template=PARTITION_FILENAME_TEMPLATE,
    )
    return output_path


def csv_to_parquet(
    csv_path: Path | str,
    output_dir: Path | str,
    *,
    compression: str = DEFAULT_COMPRESSION,
) -> Path:
    """Read an index CSV and write a Modality-partitioned Parquet dataset.

    Args:
        csv_path: Path to an index CSV (e.g. ``index.csv`` for one collection).
        output_dir: Root directory for the Parquet dataset (created if missing).
        compression: Parquet codec passed to PyArrow.

    Returns:
        ``output_dir`` after writing the dataset.

    Raises:
        ValueError: If ``Modality`` is not present in the CSV.

    Notes:
        Assumes each CSV row represents one indexed sample and that ``Modality``
        is the desired hive partition key.

    Example:
        Output layout for a collection with CT and MR rows::

            output_dir/Modality=CT/part-0.parquet
            output_dir/Modality=MR/part-0.parquet
    """
    csv_file_path = Path(csv_path)
    index_df = load_index_csv(csv_file_path)

    try:
        prepared_index_df = prepare_index_for_parquet(index_df)
    except ValueError as error:
        raise ValueError(f"{csv_file_path}: {error}") from error

    return write_modality_partitioned_parquet(
        prepared_index_df,
        output_dir,
        compression=compression,
    )
