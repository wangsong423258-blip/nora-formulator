# Contributing

Contributions may cover client transport, types, schemas, CLI behavior, documentation and the Python engine. Changes to nutrition data require source attribution, review and updates to the plaintext manifest.

Use artificial inputs for tests. Do not add customer data, credentials or service dumps. The published nutrition tables are the reviewed reference data; new tables or changes need provenance and review.

Use Node.js 22 or later for SDK checks. Run `node cli/nora.mjs --help` for a CLI smoke check. For the Python engine, follow `engine/README.md`. The v1.1.1 native Runtime still requires its separate release bundle.

`PUBLIC_MANIFEST.json` records the historical SDK export; it does not cover the newly published engine. Review new engine and data files directly, including paths, credentials and provenance.

Code contributions are provided under Apache-2.0. Nutrition data contributions follow `engine/DATA_LICENSE.md` and require documented source rights and review. Maintainers must verify that contributors have the right to publish submitted material.
