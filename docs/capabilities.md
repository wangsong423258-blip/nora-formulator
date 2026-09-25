# API capabilities

Choose a resource by its documented purpose. Resources with different meanings are not interchangeable, even when operation names look similar.

| Resource | Public purpose |
|---|---|
| `/v1/practical-recipes` | Practical recipes with user-declared supplements |
| `/v1/diet-designs` | Fresh-food contribution within an existing diet context |
| `/v1/daily-recipes` | Daily recipes using a pet profile |
| `/v1/body-condition-daily-recipes` | Daily recipes with body-condition context |
| `/v1/food-core-plans` | Food plans and nutrient reminders |
| `/v1/nutrient-completion-plans` | Food plans and active-nutrient completion references |
| `/v1/selectable-daily-plans` | Daily plans with user-specified candidate categories |
| `/v1/scientific-daily-plans` | Daily plans with preparation support |
| `/v1/candidate-pool-meals` | Quick meals from an allowed candidate pool |
| `/v1/selected-ingredient-meals` | Quick meals using a fixed user-selected ingredient set |

The OpenAPI specification lists the supported operations for each resource. A resource identifier belongs to the capability that created it. `/v1/version` describes the selected-ingredient capability; every response carries versions for its own capability.

Candidate pools and fixed selections have different contracts: an absent candidate category permits unrestricted selection in that category; an empty candidate category disables it. For fixed selections, absent and empty categories both mean not selected. Do not convert one meaning into the other.

Omitted profile fields are not equivalent to zero. Do not invent a diagnosis or silently replace missing biological information. Consult the schema and validation response. Cooking-plan batch size defaults to 3 where the operation supports it. Recalculation with omitted profile or selection retains that capability's documented existing-state behavior.

The CLI currently exposes version lookup only. There is no local calculation mode, offline engine, ingredient dataset or bulk-response example collection. The generic client supports all published operations through their operation identifiers.
