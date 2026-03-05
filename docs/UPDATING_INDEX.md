# Updating the Index

This guide explains how to add a new collection to the index (or update an existing one), package the updated `indexed_datasets` folder, and submit a pull request with the tarball for the release.

**Reference example:** The notebook [test.ipynb](../test.ipynb) walks through adding a non-TCIA (Zenodo) collection step-by-step; use it as a runnable example while following this doc.

## Overview

- **When to update:** Adding a new collection or changing an existing one.
- **High-level flow:** Get latest index → add/update collection (e.g. via steps in test.ipynb) → tar `indexed_datasets` → open PR with code/source changes and attach the tarball for the release.

```mermaid
flowchart LR
  subgraph prep [Prepare]
    A[Get latest indexed_datasets]
    B[Add source.json]
  end
  subgraph build [Build index]
    C[Download collection]
    D[Metadata and Crawl]
    E[Optional DICOM mapping]
  end
  subgraph ship [Ship]
    F[tar indexed_datasets]
    G[PR and attach tarball]
  end
  A --> B --> C --> D --> E --> F --> G
```

## Prerequisites

- **Environment:** Use the project's Pixi environment ([pixi.toml](../pixi.toml)) so dependencies (e.g. `med-imagetools`, `med-imagenet`) are available.
  ```bash
  pixi install
  pixi run jupyter lab
  ```
- **Latest indexed_datasets:** Either clone the repo and use the existing `indexed_datasets/` directory, or download the tarball from the [latest GitHub release](https://github.com/bhklab/med-image_index/releases) and extract it into the repo root.

## Adding a new collection

### Non-TCIA (e.g. Zenodo)

Follow the same steps as in [test.ipynb](../test.ipynb).

1. **Source config**
   - Create the collection directory: `indexed_datasets/.imgtools/<CollectionName>/`
   - Add `source.json` there. The schema must match `imgnet.collections.source` (e.g. `ZenodoSource`: `record_id`, `filenames`, `post_download`, `file_type`, `source`).
   - Example (Python):
     ```python
     from imgnet.collections.source import ZenodoSource
     import json
     from pathlib import Path
     from imgnet.collections.store import IndexedDatasets

     indexed_datasets = IndexedDatasets("indexed_datasets")
     source = ZenodoSource(
         file_type="nifti",
         source="zenodo",
         record_id="<record_id>",
         filenames=["<archive>.zip", "<metadata>.xlsx"],
         post_download=["unzip"]
     )
     dataset_index_path = indexed_datasets.imgtools_path / "<CollectionName>"
     dataset_index_path.mkdir(parents=True, exist_ok=True)
     with open(dataset_index_path / "source.json", "w") as f:
         json.dump(source.model_dump(mode="json"), f, indent=2)
     ```

2. **Download**
   - Use `download_collection(collection_name, temp_data_path, indexed_datasets)` to fetch data into e.g. `temp_data/<CollectionName>/`.

3. **Metadata**
   - If the source provides metadata (e.g. Excel), convert to CSV and normalize column names (e.g. flatten headers, strip `\r\n`); save under `temp_data/<CollectionName>/` so the crawler can join on it.

4. **Crawl**
   - Use `imgtools.nifti.crawl.Crawler` with:
     - `nifti_dir` = path to NIfTI files (e.g. `temp_data/<CollectionName>/nifti_and_segms`)
     - `scan_name_pattern` and `mask_name_pattern` as appropriate for your layout
     - `metadata_path` and `metadata_join_col` for joining metadata
     - `output_dir=indexed_datasets.imgtools_path`, `dataset_name="<CollectionName>"`
   - Run `crawler.crawl()` to generate `index.csv` (and related files) under `indexed_datasets/.imgtools/<CollectionName>/`.

5. **Optional: DICOM-style column mapping**
   - Add or rename columns (e.g. Modality) if needed.
   - Edit `index_mapping.toml` in the collection folder to map index columns to DICOM-like names, then apply the mapping and overwrite `index.csv` (see the last cells of test.ipynb).

### TCIA (DICOM / NBIA)

For TCIA collections, use [index_tcia.py](../index_tcia.py). The script indexes collections from the NBIA API into `indexed_datasets` (creates collection dirs and runs the DICOM crawler). Run from the repo root with the Pixi environment; it skips collections that already have an index.

## Packaging the updated index

From the repo root:

```bash
tar -czvf indexed_datasets.tar.gz indexed_datasets/
```

## Pull request and release asset

- **PR contents**
  - Include code and config changes (e.g. new or updated `source.json`, script or doc updates).
  - Do **not** commit the full `indexed_datasets/` tree if it is large; the release asset is the tarball.

- **Release asset (current process)**
  - The [release workflow](../.github/workflows/release_indexed_datasets.yml) is currently **commented out**, so the tarball is not built automatically on tag push.
  - **Attach** the built `indexed_datasets.tar.gz` to your PR (e.g. in a comment or as a draft release asset), so a maintainer can upload it to the corresponding GitHub release when cutting the release.
  - If the workflow is later enabled: after your PR is merged, a maintainer would create and push a version tag; the workflow would then package `indexed_datasets/` and upload the tarball to the release.

## Checklist

- [ ] Get latest `indexed_datasets` (clone or download from release)
- [ ] Add `source.json` under `indexed_datasets/.imgtools/<CollectionName>/`
- [ ] Download collection (e.g. `download_collection`) to `temp_data/<CollectionName>/`
- [ ] Prepare metadata (convert to CSV, normalize columns) if needed
- [ ] Run NIFTI Crawler with correct patterns and output to `indexed_datasets.imgtools_path`
- [ ] Optional: apply DICOM column mapping via `index_mapping.toml` and save `index.csv`
- [ ] Run `tar -czvf indexed_datasets.tar.gz indexed_datasets/`
- [ ] Open PR with config/code changes and attach the tarball for the release
