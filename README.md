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

## Adding a remote

After creating the repository on GitHub:

```bash
git remote add origin https://github.com/<org>/med-image_index.git
```
