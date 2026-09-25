# Nora API v1

All operations require verified Bearer authentication and the `nora:use` scope. The deployment chooses the credential provider; there is no default credential and no anonymous fallback. All resource reads, writes and cancellations operate only in the authenticated principal's state. Authentication comes from the trusted HTTP gateway, never from body fields.

## Separate capabilities

|Resource|Meaning|
|---|---|
|`/v1/practical-recipes`|Practical recipe with user-declared supplements|
|`/v1/diet-designs`|Fresh-food contribution with explicit existing-diet context and declared feeding goal|
|`/v1/daily-recipes`|Pet-profile daily recipe with product-label support|
|`/v1/body-condition-daily-recipes`|Body-condition and disease-adapted daily recipe|
|`/v1/food-core-plans`|Food core and nutrient reminders, without automatic product dosing|
|`/v1/nutrient-completion-plans`|Food plan and active-nutrient completion references|
|`/v1/selectable-daily-plans`|Scientific daily plan with candidate-pool selection|
|`/v1/scientific-daily-plans`|Daily plan with evidence-purpose and preparation audit|
|`/v1/candidate-pool-meals`|Quick meal using candidates the service can select from|
|`/v1/selected-ingredient-meals`|Quick meal using all and only the user's selected ingredients|

These are different product contracts, not aliases. A recipe belongs to the capability that created it. Resource identifiers cannot silently move between capabilities. There is no hidden model-version or mode switch. The existing-diet feeding goal is an explicit part of diet-design context; it is not a selector for another capability resource.

The OpenAPI lists all supported create, validate, read, recalculate, confirm, cooking-plan and catalog operations. Not every capability supports every operation. `GET /v1/version` reports the selected-ingredient capability's current versions. Every operation response reports its own four version fields.

## Requests and defaults

Use the operation's request schema. POST accepts a JSON object; GET uses declared path/query parameters and no body. Unknown top-level fields and duplicate JSON/query keys are rejected. A missing optional version reads the latest owned snapshot. A missing `expected_version` retains the original capability's behavior with no caller version precondition; send an explicit version to reject stale writes. Cooking-plan batch size defaults to 3 where supported. Omitted recalculation profile/selection retains that capability's documented existing-state behavior.

Candidate-pool selection and fixed selected-set selection are distinct: an absent candidate category means unrestricted selection, while an empty candidate category disables that category. For fixed selected sets, absent and empty categories both mean not selected. An omitted fixed selection is not permission to choose ingredients automatically. Profile normalization remains capability-specific; do not translate omitted biological data to zero or infer a diagnosis. Business validation reports invalid or incomplete profiles explicitly.

## Responses

Every response contains `metadata`, `operation_id`, `status`, `result`, `warnings` and `errors`. The closed response schema only exposes user-facing result fields. Ingredient catalogs provide identity, display, state and selectability; they do not provide the underlying per-food nutrient dataset. Public recipe responses expose returned grams and available aggregate nutrition facts, without recalculation or transport rounding.

`pet_me_kcal` is provided only when that capability supplies pet ME. `recipe_energy_kcal` may be a food-reference estimate and must not be relabeled as measured pet ME. Missing values remain absent or null. `known_subtotal` is a quantified contribution, not a claim that all unmeasured contributions are zero. No public claim of complete balance may be inferred from a successful request. The original domain status and available completeness flag remain authoritative.

Public warnings use a small reviewed code set; other legacy warnings map to `REVIEW_REQUIRED`, preserving warning count. Detailed private warning payloads are not transmitted. Public infeasibility exposes a domain reason category, not internal thresholds. Per-constraint details are private; `constraint_status` may be `UNKNOWN` where the original capability supplies no compatible aggregate. The public interface is intentionally a safe projection of private output, not the full historical JSON response.

## Errors and concurrency

HTTP 200 can carry an infeasible or review-required domain result. Inspect `status`, `errors` and `result`, not HTTP status alone. Transport errors use 400; missing authentication 401; scope/ownership failure 403; unknown operation or owned resource 404; wrong HTTP method 405; stale version 409; invalid domain input 422; private failure 500; calculation unavailable 503. Responses never include raw exceptions or internal addresses. There is no automatic retry of writes.

Python execution is synchronous. Browser integration may use asynchronous transport without changing calculation semantics. Cancellation is scoped to the authenticated principal's service and requires the deployment to retain the same owned service instance for that principal. No cancellation is allowed to cross principal boundaries.

## Independent versions

- `api_version`: public contract major, currently `v1`.
- `engine_version`: the capability's formulation-engine revision.
- `data_version`: its nutrition-data revision; compound identifiers can include a content fingerprint.
- `ruleset_version`: its rule-set revision or content fingerprint, independent of API major.

An engine/data revision does not itself create API v2. A breaking public request, response, default, state or error contract requires a major-version decision. Different resources must not be automatically redirected to each other during an engine upgrade.
