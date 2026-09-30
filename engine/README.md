# Nora plaintext nutrition engine

This directory publishes the actual Python formulation algorithms and the
nutrition data they use. There is no encrypted DataPack or decryption key in
this package. The runtime reads human-readable JSON tables from
`palecho_nutrition/data/nutrition-json/` and JSON rules and ingredient records
beside the Python modules. `manifest.json` contains SHA-256 checksums for the
JSON table files; it is an integrity check, not encryption.

## Run

Python 3.11 or newer is required. From the repository root:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install ./engine
.venv/bin/palecho-nutrition status
.venv/bin/palecho-nutrition assess --pet engine/examples/dog-adult.json
.venv/bin/palecho-nutrition freshfood --state :memory: --request engine/examples/life-stage-request.json
```

The package installs NumPy 2.2.6 and SciPy 1.15.3. For a persistent recipe
journal, replace `:memory:` with a writable SQLite path outside this repository.
Use `--db PATH` to select another plaintext JSON data directory or a legacy
SQLite nutrition database. The shipped default is the plaintext JSON data.

To build an inspectable runtime wheel:

```sh
.venv/bin/python -m pip wheel --no-deps ./engine -w dist
```

The wheel is a ZIP archive containing Python and JSON files. It is a command
line runtime; the older v1.1.1 desktop installers and self-hosted archives
still contain their original encrypted DataPack and have not been replaced by
this package.

## Data and source

- `palecho_nutrition/*.py`: formulation, eligibility, solver and audit logic.
- `palecho_nutrition/data/nutrition-json/meta.json`: data version and review state.
- `palecho_nutrition/data/nutrition-json/tables/*.json`: the 22 nutrition tables.
- `palecho_nutrition/*.json`: schema, food, mapping and rule resources.
- `tools/export_plain_data.py`: deterministic export from the historical SQLite database.

The exported JSON tables were compared with the source SQLite database after
the original Store's boolean decoding; all 22 tables and 7,023 rows matched.
The existing dataset marks itself `production_ready: false` and
`build_mode: REVIEW_ONLY`. Do not treat the Preview as a clinically validated
complete-diet prescription.

Python source is Apache-2.0. Nutrition data and JSON resources follow
[DATA_LICENSE.md](DATA_LICENSE.md), with PalEcho attribution required for use.
