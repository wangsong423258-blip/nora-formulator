"""Public, pet-only FreshFood 1.2 model names; runtime schema is authoritative."""
from typing import Literal, Required, TypedDict


class PetNutritionProfile(TypedDict, total=False):
    profile_id: str
    species: Required[Literal['DOG', 'CAT']]
    breed_id: str | None
    breed_name: str | None
    birth_date: str | None
    as_of_date: str
    age_years: int | None
    age_months: int | None
    life_stage: str | None
    sex: str
    neutered: bool | None
    weight_kg: Required[float]
    body_condition: int | str | None
    weight_trend: str
    activity_level: str
    diseases: list[dict | str]
    disease_subtypes: list[dict | str]
    recent_symptoms: list[str]
    food_restrictions: list[dict]
    disliked_foods: list[str]


class RecipeCompositionPolicy(TypedDict):
    version: str
    target_component_count: list[int]
    constraint_kind: Literal['SOFT_OBJECTIVE']
    main_component_excluded_categories: list[str]
    species_structure: str
    fixed_food_ratios: Literal[False]


class RequiredSupplement(TypedDict):
    supplement_type: str
    purpose: list[str]
    daily_amount: float | None
    dose_unit: str | None
    user_spec_required: bool
    user_spec_id: str | None
    dose_scope: str
    specification: dict | None
    selection_guide: dict


class DailyFreshFoodRecipe(TypedDict):
    api_version: Literal['1.2']
    recipe_id: str
    recipe_version: int
    status: str
    recipe_kind: Literal['DAILY_FRESH_FOOD_RECIPE']
    pet_summary: PetNutritionProfile
    daily_energy_target: dict | None
    recipe_components: list[dict]
    required_supplements: list[RequiredSupplement]
    disease_adaptations: list[dict]
    nutrition_explanation: list[dict]
    warnings: list[dict]
    replacement_options: list[dict]
    daily_feeding_plan: dict
    single_component_reason: str | None
    recipe_composition_policy: RecipeCompositionPolicy | None
