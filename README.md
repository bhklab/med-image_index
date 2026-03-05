# med-image_index

Index metadata for BHKLAB medical imaging collections (NBIA-style). The `indexed_datasets` folder contains per-collection index files (e.g. `index.csv`, `crawl_db.json`) and `collections_summary.json`.

## Releases

Releases are built automatically when you push a version tag. The `indexed_datasets` folder is packaged as a tarball and attached to the GitHub release.

1. Create and push a tag (e.g. `v0.1.0`):
   ```bash
   git tag v0.1.0
   git push origin v0.1.0
   ```
2. The [Release indexed datasets](.github/workflows/release_indexed_datasets.yml) workflow runs, creates the release, and uploads `indexed_datasets-<tag>.tar.gz`.

**Note:** The release workflow is currently commented out. Until it is enabled, the indexed-datasets tarball is provided via PR (see [Updating the index](#updating-the-index)) and uploaded manually to the release.

## Adding a remote

After creating the repository on GitHub:

```bash
git remote add origin https://github.com/<org>/med-image_index.git
```

## Updating the index

The full procedure for adding a new collection and shipping an updated index is in **[docs/UPDATING_INDEX.md](docs/UPDATING_INDEX.md)**.

In short: get the latest `indexed_datasets` (clone or from release), add the collection (see [test.ipynb](test.ipynb) for non-TCIA/Zenodo or [index_tcia.py](index_tcia.py) for TCIA), tar the `indexed_datasets` folder, then open a PR with your config/code changes and attach the tarball so it can be used as the release asset.