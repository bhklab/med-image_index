"""Convert each new_index/<collection>/index.csv to Parquet hive-partitioned by modality.

Writes under a dedicated subfolder so index.csv is not picked up as data, e.g.:
  <collection>/parquet/Modality=CT/part-0.parquet
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq


def iter_index_csv_paths(src: Path) -> list[Path]:
    paths: list[Path] = []
    if not src.is_dir():
        return paths
    for child in sorted(src.iterdir()):
        if not child.is_dir():
            continue
        csv_path = child / "index.csv"
        if csv_path.is_file():
            paths.append(csv_path)
    return paths


def resolve_partition_root(
    csv_path: Path, dest: Path | None, output_subdir: str
) -> Path:
    base = csv_path.parent if dest is None else dest / csv_path.parent.name
    return base / output_subdir


_UNSAFE_FS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def sanitize_partition_values(series: pd.Series) -> pd.Series:
    """Make partition labels safe for directory names (hive partitioning)."""

    def one(v: object) -> str:
        if pd.isna(v) or v is None or (isinstance(v, str) and not v.strip()):
            return "__null__"
        s = str(v).strip()
        if not s:
            return "__null__"
        s = _UNSAFE_FS.sub("_", s)
        return s or "__null__"

    return series.map(one)


def convert_one_partitioned(
    csv_path: Path,
    root_path: Path,
    partition_column: str,
    compression: str,
) -> tuple[Path, bool]:
    """Write hive-partitioned dataset under root_path. Returns (root_path, partitioned).

    If partition_column is absent, writes a single index.parquet under root_path.
    """
    df = pd.read_csv(csv_path)

    if partition_column not in df.columns:
        single = root_path / "index.parquet"
        single.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(single, index=False, compression=compression)
        return single, False

    df = df.copy()
    df[partition_column] = sanitize_partition_values(df[partition_column])

    table = pa.Table.from_pandas(df, preserve_index=False)
    pq.write_to_dataset(
        table,
        root_path=str(root_path),
        partition_cols=[partition_column],
        compression=compression,
        existing_data_behavior="overwrite_or_ignore",
        basename_template="part-{i}.parquet",
    )
    return root_path, True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Write a Parquet dataset per index.csv, hive-partitioned by modality "
            "(default column: Modality). Output goes under "
            "<collection>/<subdir>/ (default subdir: parquet), or "
            "--dest/<collection>/<subdir>/ when --dest is set."
        )
    )
    parser.add_argument(
        "--src",
        type=Path,
        default=Path("new_index"),
        help="Directory containing collection subfolders (default: new_index)",
    )
    parser.add_argument(
        "--dest",
        type=Path,
        default=None,
        help="If set, write under <dest>/<collection>/<subdir>/ instead of local mirror",
    )
    parser.add_argument(
        "--output-subdir",
        default="parquet",
        metavar="NAME",
        help=(
            "Folder name under each collection for Parquet output (default: parquet). "
            "Keeps hive partitions separate from index.csv."
        ),
    )
    parser.add_argument(
        "--partition-column",
        default="Modality",
        help="Column used for hive-style directory partitions (default: Modality)",
    )
    parser.add_argument(
        "--compression",
        default="zstd",
        help="Parquet codec (default: zstd)",
    )
    args = parser.parse_args(argv)

    csv_paths = iter_index_csv_paths(args.src.resolve())
    if not csv_paths:
        print(f"No index.csv files found under {args.src.resolve()}", file=sys.stderr)
        return 1

    n_partitioned = 0
    n_fallback = 0
    for csv_path in csv_paths:
        root = resolve_partition_root(csv_path, args.dest, args.output_subdir)
        out, partitioned = convert_one_partitioned(
            csv_path,
            root,
            args.partition_column,
            args.compression,
        )
        if partitioned:
            n_partitioned += 1
            print(f"{csv_path} -> {out}/ ({args.partition_column}=…/)")
        else:
            n_fallback += 1
            print(
                f"{csv_path} -> {out} (no column {args.partition_column!r}; single file)",
                file=sys.stderr,
            )

    print(
        f"Done: {n_partitioned} partitioned dataset(s), "
        f"{n_fallback} single-file fallback(s) (missing partition column)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
