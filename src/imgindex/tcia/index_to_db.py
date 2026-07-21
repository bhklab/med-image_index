"""Convert imgtools output to index.csv."""

from pathlib import Path
import hashlib
import json
import pandas as pd
from imgtools.dicom import Interlacer

from imgindex.model import validate_index

def generate_sample_id(ids):
    """Generate a sample ID from a list of IDs."""
    sorted_ids = sorted(map(str, ids))
    key = "|".join(sorted_ids)
    return hashlib.sha256(key.encode()).hexdigest()

def convert_to_db(imgtools_path: Path) -> pd.DataFrame:
    """Convert imgtools output of a collection to a med-imagenet valid index.csv."""

    index_path = imgtools_path / "index.csv"
    index_df = pd.read_csv(index_path)
    crawl_db_path = imgtools_path / "crawl_db.json"
    with open(crawl_db_path, "r") as f:
        crawl_db = json.load(f)

    interlacer = Interlacer(index_df)

    main_db = []
    samples = interlacer.query_all()
    
    found_series = set()
    n_samples = 0
    for sample in samples:
        sample_id = generate_sample_id([series.SeriesInstanceUID for series in sample])
        n_samples += 1
        for series in sample:
            if series.SeriesInstanceUID in found_series:
                continue
            found_series.add(series.SeriesInstanceUID)
            entry = crawl_db[series.SeriesInstanceUID]
            record = entry[next(iter(entry))]
            main_db.append({
                "SampleID": sample_id,
                **record
            })

    # For modalities that are not considered by the crawler, add them manually
    for series in index_df["SeriesInstanceUID"]:
        if series in found_series:
            continue
        n_samples += 1
        found_series.add(series)
        entry = crawl_db[series]
        record = entry[next(iter(entry))]
        main_db.append({
            "SampleID": generate_sample_id([series]),
            **record
        })

    print(f"Converted {n_samples} samples")
    updated_index_df = pd.DataFrame(main_db)
    validated_df = validate_index(updated_index_df, "dicom", lazy=True)
    if validated_df is None:
        raise ValueError(f"Invalid index for collection {imgtools_path.name}")

    if len(updated_index_df) != len(index_df):
        raise ValueError(f"Invalid index for collection {imgtools_path.name}, {len(updated_index_df)} != {len(index_df)}")
        
    return updated_index_df

if __name__ == "__main__":
    from imgnet.collections.store import IndexedDatasets

    new_index_path = Path("new_index")
    new_index_path.mkdir(parents=True, exist_ok=True)

    indexed_datasets = IndexedDatasets()
    for collection in indexed_datasets.collections:
        if indexed_datasets.file_type(collection).value == "dicom":
            print(f"Converting collection {collection}")
            imgtools_path = indexed_datasets.imgtools_path / collection
            main_db = convert_to_db(imgtools_path)
            collection_path = new_index_path / collection
            collection_path.mkdir(parents=True, exist_ok=True)
            main_db.to_csv(collection_path / "index.csv", index=False)
            print(f"Finished converting collection {collection}")



            