"""FreshFood 1.1 domain contracts; nutrition targets are internal solver inputs."""
from typing import TypedDict, Literal, NotRequired

FreshFoodGoal = Literal['COMPLETE_DIET', 'PARTIAL_WITH_MAIN_DIET', 'OCCASIONAL_MEAL']

class CurrentSupplementContribution(TypedDict):
    user_spec_id: str
    supplement_type: str
    previous_daily_amount: float | None
    designed_daily_amount: float | None
    dose_unit: str | None
    action: str
    known_nutrients: dict
    energy_kcal_interval: list[float] | None

class CurrentDietContext(TypedDict, total=False):
    """Deprecated compatibility context; unused by the daily 1.2 design engine."""
    main_diet: dict
    extra_foods: list[dict]
    snacks: list[dict]
    freeze_dried: list[dict]
    human_foods: list[dict]
    commercial_extras: list[dict]
    current_supplements: list[dict]

class FreshFoodDesignContext(TypedDict):
    pet_profile: dict
    feeding_goal: FreshFoodGoal
    current_diet_context: NotRequired[CurrentDietContext]
    current_intake: NotRequired[dict]
    food_preferences: NotRequired[dict]
    food_restrictions: NotRequired[list[dict]]
    available_supplements: NotRequired[list[dict]]

class NutritionDesignTarget(TypedDict):
    daily_energy_kcal: float
    fresh_food_energy_kcal: float
    life_stage: str
    nutrient_constraints: list[dict]
    disease_constraints: list[str]
    design_policy: dict

class RecipeComponent(TypedDict):
    component_type: str
    ingredient_id: str
    display_name: str
    amount_g: float
    amount_min_g: float
    amount_max_g: float
    purpose: list[str]
    replaceable: bool
    replacement_options: list[dict]

class FreshFoodRecipeDesign(TypedDict):
    recipe_summary: dict
    recipe_components: list[RecipeComponent]
    supplements: list[dict]
    replacement_options: list[dict]
    disease_adaptations: list[dict]
    warnings: list[dict]
    nutrition_explanation: dict
    api_version: str
    recipe_id: str
    recipe_version: int
    status: str
