import asyncio
from typing import Literal
from pathlib import Path
import concurrent.futures
from functools import partial
import os
import sys

from tqdm import tqdm
import pandas as pd
from pydicom import dcmread
from imgtools.dicom.crawl import Crawler
from nbiatoolkit import NBIA_ENDPOINT
from nbiatoolkit.nbia import NBIAClient
from nbiatoolkit.dicomtags.tags import generateFileDatasetFromTags
import datetime

from imgnet.loggers import logger


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


def index_collection(client: NBIAClient, collection: str, output_path: Path, exist_strategy: Literal["skip", "overwrite"] = "skip", max_workers: int = 1) -> None:
    """
    Index a collection of DICOM files from the NBIA API using med-imagetools.

    Args:
        client: NBIAClient instance
        collection: str
        output_path: Path
        exist_strategy: Strategy for handling existing files
        max_workers: Number of parallel workers (1 = sequential, >1 = parallel)
    """
    series = client.getSeries({'Collection': collection})
    print(series)
    logger.info(f"Indexing collection {collection}, {len(series)} series found")

    (output_path / collection / "images").mkdir(parents=True, exist_ok=True)
    
    # Filter out existing files if skip strategy is used
    if exist_strategy == "skip":
        series = [s for s in series if not (output_path / collection / "images" / f"{s['SeriesInstanceUID']}.dcm").exists()]
        logger.info(f"After filtering existing files: {len(series)} series to process")
    
    if not series:
        logger.info(f"No new series to process for collection {collection}")
        return
    
    # Create a partial function with fixed arguments
    process_func = partial(process_single_series, client, output_path=output_path, collection=collection, exist_strategy=exist_strategy)
    
    if max_workers == 1:
        # Sequential processing (original behavior)
        with tqdm(
            series, 
            desc=f"Processing {collection}",
            unit="series",
            total=len(series),
            bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]"
        ) as pbar:
            for s in pbar:
                result = process_func(s)
                pbar.set_postfix({"Success": result})
    else:
        # Parallel processing
        logger.info(f"Processing {len(series)} series with {max_workers} workers")
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            future_to_series = {executor.submit(process_func, s): s for s in series}
            
            # Process results as they complete
            successful = 0
            failed = 0
            
            with tqdm(
                total=len(series),
                desc=f"Processing {collection}",
                unit="series",
                bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]"
            ) as pbar:
                for future in concurrent.futures.as_completed(future_to_series):
                    result = future.result()
                    if result:
                        successful += 1
                    else:
                        failed += 1
                    
                    pbar.update(1)
                    pbar.set_postfix({"Success": successful, "Failed": failed})
        
        logger.info(f"Collection {collection} processing complete: {successful} successful, {failed} failed")

    logger.info(f"Crawling collection {collection}")
    crawler = Crawler(output_path / collection, force=True)
    crawler.crawl()

    logger.info(f"Finished indexing collection {collection}, output path: {output_path / collection}")


def update_index(output_path: Path, date: datetime.date = None, max_workers: int = 1):
    print("getting new series'")
    for _collection in collections:
        (output_path / _collection["Collection"] / "images").mkdir(parents=True, exist_ok=True)

    series_list = client.getNewSeries(params={"fromDate": f"{date}"})
    
    if max_workers == 1:
        # Sequential processing - use the original client
        process_func = partial(process_single_series, client, output_path=output_path, exist_strategy="skip")
        
        with tqdm(
            series_list, 
            desc=f"Processing new data...",
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
    else:
        # Parallel processing - create a new client per thread
        logger.info(f"Processing {len(series_list)} series with {max_workers} workers")
        
        # Import here to avoid circular import
        
        # Get credentials from environment or wherever you store them
        # Adjust these based on how you initialize your client
        
        def process_with_new_client(series):
            """Create a new client for this thread and process the series"""
            # Create a new client instance for this thread
            thread_client = NBIAClient()
            return process_single_series(
                thread_client, 
                series, 
                output_path=output_path, 
                exist_strategy="skip", 
                collection=series["Collection"]
            )
        
        successful = 0
        failed = 0
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            future_to_series = {
                executor.submit(process_with_new_client, s): s 
                for s in series_list
            }
            
            with tqdm(
                total=len(series_list),
                desc=f"Processing new data...",
                unit="series",
                bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]"
            ) as pbar:
                for future in concurrent.futures.as_completed(future_to_series):
                    series = future_to_series[future]
                    try:
                        result = future.result()
                        if result:
                            successful += 1
                        else:
                            failed += 1
                    except Exception as e:
                        logger.error(f"Error processing series {series.get('SeriesInstanceUID')}: {e}")
                        failed += 1
                    
                    pbar.update(1)
                    pbar.set_postfix({"Success": successful, "Failed": failed})
        
        logger.info(f"Processing complete: {successful} successful, {failed} failed")

    # Crawling section - keep this single-threaded
    for _collection in collections:
        collection = _collection["Collection"]
        if len(os.listdir(output_path / collection / "images")) == 0:
            continue
        logger.info(f"Crawling collection {collection}")
        crawler = Crawler(output_path / collection / "images", force=True)
        crawler.crawl()
        logger.info(f"Finished indexing collection {collection}, output path: {output_path / collection}")



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
    if len(sys.argv) > 2:
        print("Usage: index_tcia.py <dd/mm/yyy>")
        exit(0)
    if len(sys.argv) == 1:
        t1 = "01/09/1900"
    else:
        t1 = sys.argv[1] 
    f1 = "%d/%m/%Y"
    client = NBIAClient()
    print("Client connection established.")
    
    collections = client.getCollections()
    print("Retrieved collections list.")
    output_path = Path("indexed_datasets")
    output_path.mkdir(parents=True, exist_ok=True)

    
    update_index(output_path=output_path, date=datetime.datetime.strptime(t1, f1).date().strftime("%d/%m/%Y"), max_workers=1)