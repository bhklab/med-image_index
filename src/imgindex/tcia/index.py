import asyncio
from typing import Literal
from pathlib import Path
import concurrent.futures
from functools import partial
import os
import sys
from dotenv import load_dotenv

from tqdm import tqdm
import pandas as pd
from pydicom import dcmread
from imgtools.dicom.crawl import Crawler
from nbiatoolkit import NBIA_ENDPOINT
from nbiatoolkit.nbia import NBIAClient
from nbiatoolkit.dicomtags.tags import generateFileDatasetFromTags
import datetime

from imgnet.loggers import logger
import logging
from imgnet.collections.store import IndexedDatasets


def process_single_series(client: NBIAClient, s: dict, output_path: Path, collection: str, exist_strategy: Literal["skip", "overwrite"] = "skip") -> bool:
    """
    Process a single series. Returns True if successful, False otherwise.
    """
    if exist_strategy == "skip" and (output_path / collection / "images" / f"{s['SeriesInstanceUID']}.dcm").exists():
        return True
    
    try:
        if s["Modality"] not in ["CT", "PT", "MR"]:
            sop_uid_data = client.getSOPIDs(s)

            for key in sop_uid_data:
                sop_uid = sop_uid_data[key][0]["SOPInstanceUID"]
            series_uid = s["SeriesInstanceUID"]
            
            file = asyncio.run(
                client.query_bytes(NBIA_ENDPOINT.DOWNLOAD_IMAGE, {"SeriesInstanceUID": series_uid, "SOPInstanceUID": sop_uid})
            )
            ds = dcmread(file, stop_before_pixels=True, force=True)
        else: 
            tags = asyncio.run(
                client.query_json(NBIA_ENDPOINT.GET_DICOM_TAGS, {"SeriesUID": s["SeriesInstanceUID"]})
            )
            tags_df = pd.DataFrame(tags)
            ds = generateFileDatasetFromTags(tags_df)

        ds.save_as(output_path / collection / "images" / f"{s['SeriesInstanceUID']}.dcm", enforce_file_format=False)
        return True
        
    except (asyncio.TimeoutError, Exception) as e:
        logger.warning(f"Failed to process series {s['SeriesInstanceUID']}: {e}")
        return False



def update_index(
    output_path: Path, 
    client: NBIAClient, 
    date: datetime.date = None, 
    is_dry: bool = False,
):
    db = IndexedDatasets(force_download=True)
    current_collections = db.collections
    tcia_collections = client.getCollections()

    collection_series = {}
    existing_summary = []
    new_summary = []

    if is_dry:
        print("Starting dry run, no new data will be downloaded.")
    print("getting new series'")
    for _collection in tcia_collections:
        (output_path / _collection["Collection"] / "images").mkdir(parents=True, exist_ok=True)
        collection_series[_collection["Collection"]] = []
    series_list = client.getNewSeries(params={"fromDate": f"{date}"})

    def process_collection(series_list: list, collection: str):
        # Sequential processing - use the original client
        process_func = partial(process_single_series, client, output_path=output_path, exist_strategy="skip")
        
        with tqdm(
            series_list, 
            desc=f"Processing {collection}",
            unit="series",
            total=len(series_list),
            bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]"
        ) as pbar:
            successful = 0
            failed = 0
            for s in pbar:
                try:
                    result = process_func(s, collection=s["Collection"])
                    if result:
                        successful += 1
                    else:
                        failed += 1
                except Exception as e:
                    logger.error(f"Error processing series {s.get('SeriesInstanceUID')}: {e}")
                    failed += 1
                pbar.set_postfix({"Success": successful, "Failed": failed})


    
    for s in series_list:
        collection_series[s["Collection"]].append(s)
    for collection, series in collection_series.items():
        if collection in current_collections:
            logger.info(f"Processing series for collection which exists in current collections: {collection}")
            existing_summary += series
        else:
            logger.info(f"Processing series for collection does not exist in current collections: {collection}")
            new_summary += series
        if not is_dry:
                process_collection(series, collection)
    
    
    # Crawling section 
    if not is_dry:
        for _collection in tcia_collections:
            collection = _collection["Collection"]
            if len(os.listdir(output_path / collection / "images")) == 0:
                continue
            logger.info(f"Crawling collection {collection}")
            crawler = Crawler(output_path / collection / "images", force=True)
            crawler.crawl()
            logger.info(f"Finished indexing collection {collection}, output path: {output_path / collection}")

    existing_df = pd.DataFrame(existing_summary)
    new_df = pd.DataFrame(new_summary)

    existing_df['SeriesCount'] = 1
    new_df['SeriesCount'] = 1

    existing_file_size = pd.DataFrame(client.getSeriesSize(params=[{"SeriesInstanceUID": uid} for uid in existing_df['SeriesInstanceUID'].to_list()]))['TotalSizeInBytes']
    new_file_size = pd.DataFrame(client.getSeriesSize(params=[{"SeriesInstanceUID": uid} for uid in new_df['SeriesInstanceUID'].to_list()]))['TotalSizeInBytes']

    existing_df['FileSize'] =  existing_file_size
    new_df['FileSize'] = new_file_size

    existing_df = existing_df[['Collection', 'SeriesCount', 'FileSize']].groupby(by='Collection', as_index=False).sum()
    new_df = new_df[['Collection', 'SeriesCount', 'FileSize']].groupby(by='Collection', as_index=False).sum()

    existing_df['Size (GB)'] = (existing_df['FileSize'] / (1024 ** 3)).round(2)
    new_df['Size (GB)'] = (new_df['FileSize'] / (1024 ** 3)).round(2)


    existing_df.to_csv(output_path / "updated_collections_table.csv")
    new_df.to_csv(output_path / "new_collections_table.csv")


# if __name__ == "__main__":
#     client = NBIAClient()

#     collections = client.getCollections()

#     output_path = Path("indexed_datasets")
#     output_path.mkdir(parents=True, exist_ok=True)

#     for _collection in collections:
#         collection = _collection["Collection"]

#         if (output_path / ".imgtools" / collection / "index.csv").exists():
#             logger.info(f"Skipping collection {collection} because it already exists")
#             continue

#         index_collection(client, collection, output_path, exist_strategy="overwrite", max_workers=int(client.max_concurrent_requests) - 3)

if __name__ == "__main__":
    logger.setLevel(logging.DEBUG)
    # TODO: Fix logging, add summary table as a csv (one for new colelctions one for existing), add private access.
    is_dry = False
    usage = "Usage: index_tcia.py <dd/mm/yyy> [OPTIONS]\nOptions:\n   --dry: executes a dry run which does not download any new data, but produces the summary tables for new and existing collection changes."
    if len(sys.argv) > 3:
        print(usage)
        exit(0)
    if len(sys.argv) == 3:
        if sys.argv[2] == "--dry":
            is_dry = True
        else:
            print(f"Unknown option {sys.argv[2]}")
            print(usage)
        
    if len(sys.argv) == 1:
        t1 = "01/09/1900"
    else:
        if sys.argv[1] == "--dry":
            is_dry = True
        else:
            t1 = sys.argv[1] 
    f1 = "%d/%m/%Y"

    load_dotenv()

    NBIA_USERNAME = os.getenv('NBIA_USERNAME')
    NBIA_PASSWORD = os.getenv('NBIA_PASSWORD')
    client = NBIAClient(username=NBIA_USERNAME, password=NBIA_PASSWORD, timeout_seconds=1000, max_concurrent_requests=32)
    print("Client connection established.")
    
    
    print("Retrieved collections list.")
    output_path = Path("indexed_datasets")
    output_path.mkdir(parents=True, exist_ok=True)

    
    update_index(output_path=output_path, date=datetime.datetime.strptime(t1, f1).date().strftime("%d/%m/%Y"), max_workers=1, is_dry=is_dry)

    # FIX LOGGING STUFF
    # MAKE .ENV