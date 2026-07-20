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

_UNSAFE_FS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _sanitize_modality(series: pd.Series) -> pd.Series:
    """Make Modality values safe for hive-style partition directory names.

    Hive partitioning embeds column values in paths (``Modality=<value>/``), so
    values must be valid single path segments. Null, empty, and whitespace-only
    values are mapped to ``__null__``; characters illegal on common filesystems
    (``<>:"/\\|?*`` and control chars) are replaced with ``_``.

    Args:
        series: The ``Modality`` column from an index DataFrame.

    Returns:
        A series of sanitized strings suitable for ``partition_cols``.
    """

    def one(v: object) -> str:
        if pd.isna(v) or v is None or (isinstance(v, str) and not v.strip()):
            return "__null__"
        s = str(v).strip()
        if not s:
            return "__null__"
        s = _UNSAFE_FS.sub("_", s)
        return s or "__null__"

    return series.map(one)


def csv_to_parquet(
    csv_path: Path | str,
    out_dir: Path | str,
    *,
    compression: str = "zstd",
) -> Path:
    """Read an index CSV and write a Modality-partitioned Parquet dataset.

    Reads ``csv_path`` with pandas, requires a ``Modality`` column, sanitizes
    partition labels, then writes under ``out_dir`` using PyArrow hive
    partitioning. Re-running over an existing ``out_dir`` overwrites matching
    partition files.

    Args:
        csv_path: Path to an index CSV (e.g. ``index.csv`` for one collection).
        out_dir: Root directory for the Parquet dataset (created if missing).
        compression: Parquet codec passed to PyArrow (default: ``zstd``).

    Returns:
        ``out_dir`` after writing the dataset.

    Raises:
        ValueError: If ``Modality`` is not present in the CSV.

    Example:
        Output layout for a collection with CT and MR rows::

            out_dir/Modality=CT/part-0.parquet
            out_dir/Modality=MR/part-0.parquet
    """
    csv_path = Path(csv_path)
    out_dir = Path(out_dir)

    df = pd.read_csv(csv_path)
    if "Modality" not in df.columns:
        raise ValueError(f"{csv_path}: missing required column 'Modality'")

    df = df.copy()
    df["Modality"] = _sanitize_modality(df["Modality"])

    out_dir.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pandas(df, preserve_index=False)
    pq.write_to_dataset(
        table,
        root_path=str(out_dir),
        partition_cols=["Modality"],
        compression=compression,
        existing_data_behavior="overwrite_or_ignore",
        basename_template="part-{i}.parquet",
    )
    return out_dir
