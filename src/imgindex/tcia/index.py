import asyncio
import logging
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path
import json
from typing import Literal

import pandas as pd
from pydicom import dcmread
from tabulate import tabulate
from tqdm import tqdm

from imgnet.collections.store import IndexedDatasets
from imgtools.dicom.crawl import Crawler
from nbiatoolkit import NBIA_ENDPOINT
from nbiatoolkit.dicomtags.tags import generateFileDatasetFromTags
from nbiatoolkit.nbia import NBIAClient

from imgindex.model import DicomIndex, validate_index
from imgindex.tcia.utils import convert_to_db
from imgindex.parquet import csv_to_parquet

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class TCIAUpdate:
    """Series update plan from summarize_updates, used by apply_updates."""

    by_collection: dict[str, list[dict]] = field(default_factory=dict)
    existing_series: list[dict] = field(default_factory=list)
    new_series: list[dict] = field(default_factory=list)
    existing_summary: pd.DataFrame = field(default_factory=pd.DataFrame)
    new_summary: pd.DataFrame = field(default_factory=pd.DataFrame)


def process_single_series(
    client: NBIAClient,
    series: dict,
    output_path: Path,
    collection: str,
    exist_strategy: Literal["skip", "overwrite"] = "skip",
) -> bool:
    """Download or reconstruct one series header DICOM. Returns True on success."""
    out_file = output_path / collection / "images" / f"{series['SeriesInstanceUID']}.dcm"
    if exist_strategy == "skip" and out_file.exists():
        return True

    try:
        if series["Modality"] not in ["CT", "PT", "MR"]:
            sop_uid_data = client.getSOPIDs(series)
            sop_uid = next(
                (entries[0]["SOPInstanceUID"] for entries in sop_uid_data.values() if entries),
                None,
            )
            if sop_uid is None:
                logger.warning("No SOP instances for series %s", series["SeriesInstanceUID"])
                return False

            file = asyncio.run(
                client.query_bytes(
                    NBIA_ENDPOINT.DOWNLOAD_IMAGE,
                    {
                        "SeriesInstanceUID": series["SeriesInstanceUID"],
                        "SOPInstanceUID": sop_uid,
                    },
                )
            )
            ds = dcmread(file, stop_before_pixels=True, force=True)
        else:
            tags = asyncio.run(
                client.query_json(
                    NBIA_ENDPOINT.GET_DICOM_TAGS,
                    {"SeriesUID": series["SeriesInstanceUID"]},
                )
            )
            ds = generateFileDatasetFromTags(pd.DataFrame(tags))

        ds.save_as(out_file, enforce_file_format=False)
        return True
    except Exception as e:
        logger.warning("Failed to process series %s: %s", series["SeriesInstanceUID"], e)
        return False


class IndexTCIA:
    """Fetch TCIA series updates, summarize them, then optionally download and crawl."""

    TEMP_DIR_NAME = "temp"
    INDEX_DIR_NAME = "index"

    def __init__(
        self,
        output_path: Path | str,
        *,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        self.output_path = Path(output_path)
        if username is None or password is None:
            username = "nbia_guest"
            password = ""
        self.client = NBIAClient(username=username, password=password)
        self.store = IndexedDatasets(force_download=False)

    @property
    def temp_path(self) -> Path:
        """Working directory for downloaded DICOMs and imgtools crawl outputs."""
        return self.output_path / self.TEMP_DIR_NAME

    @property
    def index_path(self) -> Path:
        """Directory for validated index CSVs and parquet datasets."""
        return self.output_path / self.INDEX_DIR_NAME

    @property
    def existing_collections(self) -> list[str]:
        """Collections already present in the local index store."""
        return self.store.collections

    @property
    def tcia_collections(self) -> list[str]:
        """All public collection names from TCIA/NBIA."""
        return [c["Collection"] for c in self.client.getCollections()]

    # ------------------------------------------------------------------
    # Step 1: summarize (no downloads / crawl)
    # ------------------------------------------------------------------

    def get_new_series_since(self, since: str) -> list[dict]:
        """Return series updated since `since` (`dd/mm/yyyy`)."""
        return self.client.getNewSeries(params={"fromDate": since})

    def _group_by_collection(self, series_list: list[dict]) -> dict[str, list[dict]]:
        """Group series rows by Collection name."""
        grouped: dict[str, list[dict]] = {}
        for series in series_list:
            collection = series["Collection"]
            grouped.setdefault(collection, []).append(series)
        return grouped

    def _split_existing_vs_new(
        self,
        by_collection: dict[str, list[dict]],
    ) -> tuple[list[dict], list[dict]]:
        """Split series into updates for known vs unknown collections."""
        existing: list[dict] = []
        new: list[dict] = []
        for collection, series in by_collection.items():
            if collection in self.existing_collections:
                existing.extend(series)
            else:
                new.extend(series)
        return existing, new

    def _get_series_sizes(self, series_uids: list[str], batch_size: int = 100) -> dict[str, int]:
        """Map SeriesInstanceUID -> TotalSizeInBytes, skipping failed lookups."""
        size_map: dict[str, int] = {uid: 0 for uid in series_uids}
        if not series_uids:
            return size_map

        def fetch_sizes(uids: list[str]) -> None:
            if not uids:
                return
            try:
                rows = self.client.getSeriesSize(
                    params=[{"SeriesInstanceUID": uid} for uid in uids]
                )
                # Responses are positional and omit SeriesInstanceUID.
                for uid, row in zip(uids, rows):
                    size_map[uid] = row.get("TotalSizeInBytes", 0)
            except Exception:
                if len(uids) == 1:
                    logger.warning("Could not get size for series %s", uids[0])
                    return
                mid = len(uids) // 2
                fetch_sizes(uids[:mid])
                fetch_sizes(uids[mid:])

        for start in range(0, len(series_uids), batch_size):
            batch = series_uids[start : start + batch_size]
            fetch_sizes(batch)
            logger.info(
                "Fetched sizes for %s/%s series",
                min(start + batch_size, len(series_uids)),
                len(series_uids),
            )
        return size_map

    def _build_collection_summary(self, series: list[dict]) -> pd.DataFrame:
        """Aggregate series into per-collection count and size columns."""
        columns = ["Collection", "SeriesCount", "Size (GB)"]
        if not series:
            return pd.DataFrame(columns=columns)

        df = pd.DataFrame(series)
        size_map = self._get_series_sizes(df["SeriesInstanceUID"].tolist())
        df["SeriesCount"] = 1
        df["FileSize"] = df["SeriesInstanceUID"].map(size_map).fillna(0)
        summary = (
            df[["Collection", "SeriesCount", "FileSize"]]
            .groupby("Collection", as_index=False)
            .sum()
        )
        summary["Size (GB)"] = (summary["FileSize"] / (1024**3)).round(2)
        return summary[["Collection", "SeriesCount", "Size (GB)"]]

    def summarize_updates(self, since: str) -> TCIAUpdate:
        """Discover changes since `since`, write summary CSVs, and return a plan."""
        self.output_path.mkdir(parents=True, exist_ok=True)

        series_list = self.get_new_series_since(since)
        logger.info("Found %s new series since %s", len(series_list), since)

        by_collection = self._group_by_collection(series_list)
        existing_series, new_series = self._split_existing_vs_new(by_collection)
        logger.info(
            "Found %s existing series and %s new series",
            len(existing_series),
            len(new_series),
        )

        existing_df = self._build_collection_summary(existing_series)
        new_df = self._build_collection_summary(new_series)
        existing_df.to_csv(self.output_path / "updated_collections_table.csv", index=False)
        new_df.to_csv(self.output_path / "new_collections_table.csv", index=False)

        print("Updated Collections Table:")
        if not existing_df.empty:
            print(tabulate(existing_df, headers="keys", tablefmt="github", showindex=False))
        else:
            print("(No updated collections)")

        print("\nNew Collections Table:")
        if not new_df.empty:
            print(tabulate(new_df, headers="keys", tablefmt="github", showindex=False))
        else:
            print("(No new collections)")

        return TCIAUpdate(
            by_collection=by_collection,
            existing_series=existing_series,
            new_series=new_series,
            existing_summary=existing_df,
            new_summary=new_df,
        )

    # ------------------------------------------------------------------
    # Step 2: apply
    # ------------------------------------------------------------------

    def apply_updates(self, update: TCIAUpdate) -> None:
        """Download series from `update` and crawl non-empty collection dirs."""
        collections = [
            collection
            for collection, series in update.by_collection.items()
            if series
        ]
        self._ensure_collection_dirs(collections)
        for collection in collections:
            self.process_series(update.by_collection[collection], collection)
        self.crawl_collections(collections)

    def process_series(self, series_list: list[dict], collection: str) -> None:
        """Process all series in one collection, with a progress bar."""
        process_func = partial(
            process_single_series,
            self.client,
            output_path=self.temp_path,
            exist_strategy="skip",
        )

        with tqdm(
            series_list,
            desc=f"Processing {collection}",
            unit="series",
            total=len(series_list),
            bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]",
        ) as pbar:
            successful = 0
            failed = 0
            for series in pbar:
                try:
                    if process_func(series, collection=series["Collection"]):
                        successful += 1
                    else:
                        failed += 1
                except Exception as e:
                    logger.error(
                        "Error processing series %s: %s",
                        series.get("SeriesInstanceUID"),
                        e,
                    )
                    failed += 1
                pbar.set_postfix({"Success": successful, "Failed": failed})

    def crawl_collections(self, collections: list[str]) -> None:
        """Run imgtools Crawler on collections that have downloaded images."""
        for collection in collections:
            images_dir = self.temp_path / collection / "images"
            if not images_dir.exists() or not any(images_dir.iterdir()):
                continue
            logger.info("Crawling collection %s", collection)
            crawler = Crawler(
                images_dir,
                output_dir=self.temp_path,
                dataset_name=collection,
                force=True,
            )
            crawler.crawl()
            logger.info(
                "Finished indexing collection %s, crawl path: %s",
                collection,
                self.temp_path / collection,
            )

    def _ensure_collection_dirs(self, collections: list[str]) -> None:
        """Create `images/` under each collection temp path."""
        for collection in collections:
            (self.temp_path / collection / "images").mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Orchestration
    # ------------------------------------------------------------------

    def run(self, since: str, *, apply: bool = True) -> TCIAUpdate:
        """Summarize updates, then optionally download and crawl."""
        update = self.summarize_updates(since)

        if apply:
            self.apply_updates(update)

        for collection in update.by_collection:
            crawl_dir = self.temp_path / collection

            index_df = pd.read_csv(crawl_dir / "index.csv")
            with (crawl_dir / "crawl_db.json").open("r") as f:
                crawl_db = json.load(f)

            updated_index = convert_to_db(index_df, crawl_db)
            
            try:
                validate_index(updated_index, "dicom", lazy=True)
            except Exception as e:
                logger.error("Invalid index for collection %s: %s", collection, e)
                continue

            collection_index_dir = self.index_path / collection
            collection_index_dir.mkdir(parents=True, exist_ok=True)
            csv_to_parquet(updated_index, collection_index_dir)

        return update


if __name__ == "__main__":
    index = IndexTCIA(output_path="data/tcia/index")
    index.run(since="01/07/2026")