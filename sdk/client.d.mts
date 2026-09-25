export type OperationId =
  | "practical_recipes__confirmRecipe"
  | "practical_recipes__generateCookingPlan"
  | "practical_recipes__generatePracticalRecipe"
  | "practical_recipes__getRecipe"
  | "practical_recipes__recalculateRecipe"
  | "practical_recipes__replaceIngredient"
  | "practical_recipes__setUserSupplementSpec"
  | "practical_recipes__updatePetNutritionProfile"
  | "practical_recipes__validateProfile"
  | "diet_designs__confirmRecipe"
  | "diet_designs__designFreshFoodRecipe"
  | "diet_designs__generateCookingPlan"
  | "diet_designs__getRecipe"
  | "diet_designs__recalculateRecipe"
  | "diet_designs__replaceIngredient"
  | "diet_designs__setUserSupplementSpec"
  | "diet_designs__updateDesignContext"
  | "daily_recipes__confirmRecipe"
  | "daily_recipes__designDailyFreshFoodRecipe"
  | "daily_recipes__generateCookingPlan"
  | "daily_recipes__getDiseaseCatalog"
  | "daily_recipes__getRecipe"
  | "daily_recipes__recalculateRecipe"
  | "daily_recipes__replaceIngredient"
  | "daily_recipes__setUserSupplementSpec"
  | "daily_recipes__updatePetNutritionProfile"
  | "daily_recipes__validateProfile"
  | "body_condition_daily_recipes__confirmRecipe"
  | "body_condition_daily_recipes__designDailyFreshFoodRecipe"
  | "body_condition_daily_recipes__generateCookingPlan"
  | "body_condition_daily_recipes__getDiseaseCatalog"
  | "body_condition_daily_recipes__getRecipe"
  | "body_condition_daily_recipes__recalculateRecipe"
  | "body_condition_daily_recipes__replaceIngredient"
  | "body_condition_daily_recipes__setUserSupplementSpec"
  | "body_condition_daily_recipes__updatePetNutritionProfile"
  | "body_condition_daily_recipes__validateProfile"
  | "food_core_plans__confirmRecipe"
  | "food_core_plans__designDailyFreshFoodRecipe"
  | "food_core_plans__generateCookingPlan"
  | "food_core_plans__getDiseaseCatalog"
  | "food_core_plans__getRecipe"
  | "food_core_plans__recalculateRecipe"
  | "food_core_plans__replaceIngredient"
  | "food_core_plans__updatePetNutritionProfile"
  | "food_core_plans__validateProfile"
  | "nutrient_completion_plans__confirmRecipe"
  | "nutrient_completion_plans__designDailyFreshFoodRecipe"
  | "nutrient_completion_plans__generateCookingPlan"
  | "nutrient_completion_plans__getDiseaseCatalog"
  | "nutrient_completion_plans__getRecipe"
  | "nutrient_completion_plans__recalculateRecipe"
  | "nutrient_completion_plans__replaceIngredient"
  | "nutrient_completion_plans__updatePetNutritionProfile"
  | "nutrient_completion_plans__validateProfile"
  | "selectable_daily_plans__confirmRecipe"
  | "selectable_daily_plans__designDailyFreshFoodRecipe"
  | "selectable_daily_plans__generateCookingPlan"
  | "selectable_daily_plans__getDiseaseCatalog"
  | "selectable_daily_plans__getIngredientCatalog"
  | "selectable_daily_plans__getRecipe"
  | "selectable_daily_plans__recalculateRecipe"
  | "selectable_daily_plans__replaceIngredient"
  | "selectable_daily_plans__setIngredientSelection"
  | "selectable_daily_plans__updatePetNutritionProfile"
  | "selectable_daily_plans__validateProfile"
  | "scientific_daily_plans__confirmRecipe"
  | "scientific_daily_plans__designDailyFreshFoodRecipe"
  | "scientific_daily_plans__generateCookingPlan"
  | "scientific_daily_plans__getDiseaseCatalog"
  | "scientific_daily_plans__getIngredientCatalog"
  | "scientific_daily_plans__getRecipe"
  | "scientific_daily_plans__recalculateRecipe"
  | "scientific_daily_plans__replaceIngredient"
  | "scientific_daily_plans__setIngredientSelection"
  | "scientific_daily_plans__updatePetNutritionProfile"
  | "scientific_daily_plans__validateProfile"
  | "candidate_pool_meals__designQuickFreshMeal"
  | "candidate_pool_meals__getDiseaseCatalog"
  | "candidate_pool_meals__getIngredientCatalog"
  | "candidate_pool_meals__getQuickFreshMeal"
  | "candidate_pool_meals__getQuickMealCookingPlan"
  | "candidate_pool_meals__recalculateQuickFreshMeal"
  | "candidate_pool_meals__validateQuickMealProfile"
  | "selected_ingredient_meals__cancelQuickFreshMeal"
  | "selected_ingredient_meals__checkIngredientCombination"
  | "selected_ingredient_meals__designQuickFreshMeal"
  | "selected_ingredient_meals__getDiseaseCatalog"
  | "selected_ingredient_meals__getIngredientCatalog"
  | "selected_ingredient_meals__getIngredientEligibility"
  | "selected_ingredient_meals__getQuickFreshMeal"
  | "selected_ingredient_meals__getQuickMealCookingPlan"
  | "selected_ingredient_meals__recalculateQuickFreshMeal"
  | "selected_ingredient_meals__resolveQuickMealLifeStage"
  | "selected_ingredient_meals__validateQuickMealProfile"
  | "version";
export interface PublicResponse {
  metadata: { api_version: string; engine_version: string; data_version: string; ruleset_version: string };
  operation_id: string;
  status: string;
  result: Record<string, unknown>;
  warnings: Array<{ code: string }>;
  errors: Array<{ code: string }>;
}
export interface CallOptions {
  body?: Record<string, unknown>;
  path?: Record<string, string>;
  query?: Record<string, string | number | boolean>;
  signal?: AbortSignal;
}
export class NoraClientError extends Error { readonly code: string; readonly status?: number; }
export class NoraClient {
  constructor(options: { baseUrl?: string; token: string; fetchImpl?: typeof fetch; timeoutMs?: number });
  call(operationId: OperationId, options?: CallOptions): Promise<PublicResponse>;
  runtimeStatus(): Promise<RuntimeStatus>;
  version(options?: CallOptions): Promise<PublicResponse>;
}

export interface RuntimeStatus {
  runtime_version: string; api_version: 'v1'; status: string;
  channel: 'development' | 'production'; offline_runtime: boolean;
  edition: 'Community' | 'Commercial' | 'Enterprise' | 'OEM';
  attribution_required: boolean; attribution_text?: string; attribution: { en: string; zh: string };
}
