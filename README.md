# ufc-mention-markets

Analysis of UFC fight transcripts, keyed by fighter matchup.

## Data

The raw dataset lives in `ufc_cleaned_export/` — 5,581 gzip-compressed JSON files
(~52 MB), one per fight, named by matchup
(e.g. `AJ_Dobson_vs_Jacob_Malkoun_UFC_271.json.gz`).

This folder is **git-ignored** and is not part of the public repo. To work with the
data, place the `ufc_cleaned_export/` folder at the repo root and decompress files as
needed (each is a `.json.gz`).
