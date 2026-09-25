# Minimal examples

- `version.mjs` reads version metadata from an authenticated client.
- `validate-profile.mjs` submits one artificial dog profile to illustrate request shape. The intentionally minimal profile may receive validation warnings or errors; it is not a feeding recommendation.

Import an example and pass a configured client. Nothing executes at import time. No example contains a real user, ingredient dataset, meal result, or saved calculation output. Tests use mocks and make no network requests.
