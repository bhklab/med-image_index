# Updating the Index

This guide explains how to add a new non-TCIA collection to the index and submit it via pull requests on both GitHub and Hugging Face Hub.

**Reference example:** The notebook [notebooks/LiverHCCSeg.ipynb](../notebooks/LiverHCCSeg.ipynb) walks through adding a Zenodo collection end-to-end. Follow it as a runnable example alongside this doc.

## Overview

```mermaid
flowchart LR
  A[Get latest indexed_datasets] --> B[Create source.json]
  B --> C[Download data]
  C --> D[Prepare metadata]
  D --> E[Run crawler]
  E --> F[Optional DICOM mapping]
  F --> G[Validate]
  G --> H["HF Hub PR (data)"]
```

## Prerequisites

1. **Environment:** Install dependencies with Pixi:
   ```bash
   pixi install
   ```

2. **HF Hub auth:** Log in to Hugging Face (needs a write-scope token):
   ```bash
   hf auth login
   ```

3. **Latest indexed_datasets:** Download from [HF Hub](https://huggingface.co/datasets/BruhJosh/med-image-index):
   ```bash
   hf download BruhJosh/med-image-index --repo-type dataset --local-dir ./hf-data
   cp -r ./hf-data/indexed_datasets ./indexed_datasets
   ```

## Step 1: Create source.json

Create the collection directory and add a `source.json` that describes where the data comes from. The schema must match `imgnet.collections.source` (e.g. `ZenodoSource`, `DropboxSource`, `S3Source`).

```python
import json
from imgnet.collections.store import IndexedDatasets
from imgnet.collections.source import ZenodoSource

indexed_datasets = IndexedDatasets("indexed_datasets")

source = ZenodoSource(
    file_type="nifti",
    source="zenodo",
    record_id="<record_id>",
    filenames=["<archive>.zip", "<metadata>.xlsx"],
    post_download=["unzip"],
)

dataset_path = indexed_datasets.imgtools_path / "<CollectionName>"
dataset_path.mkdir(parents=True, exist_ok=True)
with open(dataset_path / "source.json", "w") as f:
    json.dump(source.model_dump(mode="json"), f, indent=2)
```

## Step 2: Download the data

Use `download_collection` to fetch the data into a temporary directory:

```python
from pathlib import Path
from imgnet.download import download_collection

temp_data_path = Path("temp_data") / "<CollectionName>"
temp_data_path.mkdir(parents=True, exist_ok=True)
download_collection("<CollectionName>", temp_data_path, indexed_datasets)
```

## Step 3: Prepare metadata

If the source provides metadata (e.g. an Excel file), convert it to CSV and normalize column names:

```python
import re
import pandas as pd

xlsx_path = temp_data_path / "<MetadataFile>.xlsx"
csv_path = temp_data_path / "<MetadataFile>.csv"

df = pd.read_excel(xlsx_path)
df = df.dropna(how="all")
df.columns = [re.sub(r"[\r\n\x0d_]+", " ", str(c)).strip() for c in df.columns]
df.to_csv(csv_path, index=False)
```

Skip this step if the source has no separate metadata file.

## Step 4: Run the crawler

Use the `imgtools` NIfTI crawler to generate `index.csv` and related files:

```python
from imgtools.nifti.crawl import Crawler

crawler = Crawler(
    nifti_dir=str(temp_data_path / "<data_subfolder>"),
    scan_name_pattern="{PatientID}/{StudyDate}/{PhaseContrast}.nii.gz",
    mask_name_pattern="{PatientID}/{StudyDate}/rater{rater_id}_{ROIName}.nii.gz",
    metadata_path=str(csv_path),            # omit if no metadata
    metadata_join_col="PatientID",           # omit if no metadata
    deep=True,
    output_dir=str(indexed_datasets.imgtools_path),
    dataset_name="<CollectionName>",
    n_jobs=10,
    force=True,
)
crawler.crawl()
```

Adjust `scan_name_pattern`, `mask_name_pattern`, and other parameters to match your dataset's file layout. See the [LiverHCCSeg notebook](../notebooks/LiverHCCSeg.ipynb) for a concrete example.

## Step 5: Optional DICOM column mapping

If the crawler generated an `index_mapping.toml`, you can use it to rename columns in `index.csv` to DICOM-style names:

```python
import toml

mapping_path = indexed_datasets.imgtools_path / "<CollectionName>" / "index_mapping.toml"
index_path = indexed_datasets.imgtools_path / "<CollectionName>" / "index.csv"

with open(mapping_path) as f:
    mapping = toml.load(f)

non_empty = {k: v for k, v in mapping.items() if v}
if non_empty:
    df = pd.read_csv(index_path)
    df.rename(columns=non_empty, inplace=True)
    df.to_csv(index_path, index=False)
```

You can also add a `Modality` column or other custom columns at this point.

## Step 6: Validate

Check that the new collection is compatible with imgnet:

```bash
pixi run validate <CollectionName>
```

This verifies:
- `source.json` parses correctly.
- `index.csv` loads as a non-empty DataFrame.
- Required columns (`filepath`, `PatientID`) exist.

Fix any errors before proceeding.

## Step 7: Submit pull requests

Once validation passes, open two PRs: one on HF Hub for the data, and one on GitHub for any code/config changes.

### 7a. Open HF Hub PR

Upload the updated `indexed_datasets/` to [BruhJosh/med-image-index](https://huggingface.co/datasets/BruhJosh/med-image-index) as a pull request:

```bash
huggingface-cli upload BruhJosh/med-image-index ./indexed_datasets indexed_datasets \
  --repo-type dataset \
  --commit-message "Add <CollectionName>" \
  --create-pr
```

## Checklist

- [ ] Get latest `indexed_datasets` from HF Hub
- [ ] Create `source.json` under `indexed_datasets/.imgtools/<CollectionName>/`
- [ ] Download the data to `temp_data/<CollectionName>/`
- [ ] Convert metadata to CSV if needed
- [ ] Run the crawler to generate `index.csv`
- [ ] Optional: apply DICOM column mapping via `index_mapping.toml`
- [ ] Run `pixi run validate <CollectionName>` and confirm it passes
