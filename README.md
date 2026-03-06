# med-image_index

Index metadata for BHKLAB medical imaging collections. The `indexed_datasets` folder contains per-collection index files (e.g. `index.csv`, `crawl_db.json`, `source.json`) and `collections_summary.json`.

Data is stored on [Hugging Face Hub](https://huggingface.co/datasets/BruhJosh/med-image-index). This repo contains the code, notebooks, and documentation for managing the index.

## Quick start

```bash
pixi install
```

## Adding a new collection

Follow the step-by-step guide in **[docs/UPDATING_INDEX.md](docs/UPDATING_INDEX.md)**. The [LiverHCCSeg notebook](notebooks/LiverHCCSeg.ipynb) is a runnable reference example.

In short:

1. Download the latest `indexed_datasets` from HF Hub.
2. Create a `source.json` describing where the data lives.
3. Download and prepare the data locally.
4. Run the `imgtools` crawler to generate `index.csv`.
5. Validate with `pixi run validate <CollectionName>`.
6. Open an HF Hub PR with the updated data and a GitHub PR referencing it.

## Validate the index

```bash
pixi run validate                  # all collections
pixi run validate MyCollection     # single collection
```
