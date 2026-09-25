// Generated exclusively from the published OpenAPI contract.
export const operations = Object.freeze({
  "practical_recipes__confirmRecipe": {
    "method": "POST",
    "path": "/v1/practical-recipes/confirm",
    "parameters": []
  },
  "practical_recipes__generateCookingPlan": {
    "method": "POST",
    "path": "/v1/practical-recipes/cooking-plan",
    "parameters": []
  },
  "practical_recipes__generatePracticalRecipe": {
    "method": "POST",
    "path": "/v1/practical-recipes",
    "parameters": []
  },
  "practical_recipes__getRecipe": {
    "method": "GET",
    "path": "/v1/practical-recipes/{recipe_id}",
    "parameters": [
      {
        "name": "recipe_id",
        "in": "path"
      },
      {
        "name": "recipe_version",
        "in": "query"
      }
    ]
  },
  "practical_recipes__recalculateRecipe": {
    "method": "POST",
    "path": "/v1/practical-recipes/recalculate",
    "parameters": []
  },
  "practical_recipes__replaceIngredient": {
    "method": "POST",
    "path": "/v1/practical-recipes/replace-ingredient",
    "parameters": []
  },
  "practical_recipes__setUserSupplementSpec": {
    "method": "POST",
    "path": "/v1/practical-recipes/supplement",
    "parameters": []
  },
  "practical_recipes__updatePetNutritionProfile": {
    "method": "POST",
    "path": "/v1/practical-recipes/profile",
    "parameters": []
  },
  "practical_recipes__validateProfile": {
    "method": "POST",
    "path": "/v1/practical-recipes/validate",
    "parameters": []
  },
  "diet_designs__confirmRecipe": {
    "method": "POST",
    "path": "/v1/diet-designs/confirm",
    "parameters": []
  },
  "diet_designs__designFreshFoodRecipe": {
    "method": "POST",
    "path": "/v1/diet-designs",
    "parameters": []
  },
  "diet_designs__generateCookingPlan": {
    "method": "POST",
    "path": "/v1/diet-designs/cooking-plan",
    "parameters": []
  },
  "diet_designs__getRecipe": {
    "method": "GET",
    "path": "/v1/diet-designs/{recipe_id}",
    "parameters": [
      {
        "name": "recipe_id",
        "in": "path"
      },
      {
        "name": "recipe_version",
        "in": "query"
      }
    ]
  },
  "diet_designs__recalculateRecipe": {
    "method": "POST",
    "path": "/v1/diet-designs/recalculate",
    "parameters": []
  },
  "diet_designs__replaceIngredient": {
    "method": "POST",
    "path": "/v1/diet-designs/replace-ingredient",
    "parameters": []
  },
  "diet_designs__setUserSupplementSpec": {
    "method": "POST",
    "path": "/v1/diet-designs/supplement",
    "parameters": []
  },
  "diet_designs__updateDesignContext": {
    "method": "POST",
    "path": "/v1/diet-designs/context",
    "parameters": []
  },
  "daily_recipes__confirmRecipe": {
    "method": "POST",
    "path": "/v1/daily-recipes/confirm",
    "parameters": []
  },
  "daily_recipes__designDailyFreshFoodRecipe": {
    "method": "POST",
    "path": "/v1/daily-recipes",
    "parameters": []
  },
  "daily_recipes__generateCookingPlan": {
    "method": "POST",
    "path": "/v1/daily-recipes/cooking-plan",
    "parameters": []
  },
  "daily_recipes__getDiseaseCatalog": {
    "method": "GET",
    "path": "/v1/daily-recipes/disease-catalog",
    "parameters": []
  },
  "daily_recipes__getRecipe": {
    "method": "GET",
    "path": "/v1/daily-recipes/{recipe_id}",
    "parameters": [
      {
        "name": "recipe_id",
        "in": "path"
      },
      {
        "name": "recipe_version",
        "in": "query"
      }
    ]
  },
  "daily_recipes__recalculateRecipe": {
    "method": "POST",
    "path": "/v1/daily-recipes/recalculate",
    "parameters": []
  },
  "daily_recipes__replaceIngredient": {
    "method": "POST",
    "path": "/v1/daily-recipes/replace-ingredient",
    "parameters": []
  },
  "daily_recipes__setUserSupplementSpec": {
    "method": "POST",
    "path": "/v1/daily-recipes/supplement",
    "parameters": []
  },
  "daily_recipes__updatePetNutritionProfile": {
    "method": "POST",
    "path": "/v1/daily-recipes/profile",
    "parameters": []
  },
  "daily_recipes__validateProfile": {
    "method": "POST",
    "path": "/v1/daily-recipes/validate",
    "parameters": []
  },
  "body_condition_daily_recipes__confirmRecipe": {
    "method": "POST",
    "path": "/v1/body-condition-daily-recipes/confirm",
    "parameters": []
  },
  "body_condition_daily_recipes__designDailyFreshFoodRecipe": {
    "method": "POST",
    "path": "/v1/body-condition-daily-recipes",
    "parameters": []
  },
  "body_condition_daily_recipes__generateCookingPlan": {
    "method": "POST",
    "path": "/v1/body-condition-daily-recipes/cooking-plan",
    "parameters": []
  },
  "body_condition_daily_recipes__getDiseaseCatalog": {
    "method": "GET",
    "path": "/v1/body-condition-daily-recipes/disease-catalog",
    "parameters": []
  },
  "body_condition_daily_recipes__getRecipe": {
    "method": "GET",
    "path": "/v1/body-condition-daily-recipes/{recipe_id}",
    "parameters": [
      {
        "name": "recipe_id",
        "in": "path"
      },
      {
        "name": "recipe_version",
        "in": "query"
      }
    ]
  },
  "body_condition_daily_recipes__recalculateRecipe": {
    "method": "POST",
    "path": "/v1/body-condition-daily-recipes/recalculate",
    "parameters": []
  },
  "body_condition_daily_recipes__replaceIngredient": {
    "method": "POST",
    "path": "/v1/body-condition-daily-recipes/replace-ingredient",
    "parameters": []
  },
  "body_condition_daily_recipes__setUserSupplementSpec": {
    "method": "POST",
    "path": "/v1/body-condition-daily-recipes/supplement",
    "parameters": []
  },
  "body_condition_daily_recipes__updatePetNutritionProfile": {
    "method": "POST",
    "path": "/v1/body-condition-daily-recipes/profile",
    "parameters": []
  },
  "body_condition_daily_recipes__validateProfile": {
    "method": "POST",
    "path": "/v1/body-condition-daily-recipes/validate",
    "parameters": []
  },
  "food_core_plans__confirmRecipe": {
    "method": "POST",
    "path": "/v1/food-core-plans/confirm",
    "parameters": []
  },
  "food_core_plans__designDailyFreshFoodRecipe": {
    "method": "POST",
    "path": "/v1/food-core-plans",
    "parameters": []
  },
  "food_core_plans__generateCookingPlan": {
    "method": "POST",
    "path": "/v1/food-core-plans/cooking-plan",
    "parameters": []
  },
  "food_core_plans__getDiseaseCatalog": {
    "method": "GET",
    "path": "/v1/food-core-plans/disease-catalog",
    "parameters": []
  },
  "food_core_plans__getRecipe": {
    "method": "GET",
    "path": "/v1/food-core-plans/{recipe_id}",
    "parameters": [
      {
        "name": "recipe_id",
        "in": "path"
      },
      {
        "name": "recipe_version",
        "in": "query"
      }
    ]
  },
  "food_core_plans__recalculateRecipe": {
    "method": "POST",
    "path": "/v1/food-core-plans/recalculate",
    "parameters": []
  },
  "food_core_plans__replaceIngredient": {
    "method": "POST",
    "path": "/v1/food-core-plans/replace-ingredient",
    "parameters": []
  },
  "food_core_plans__updatePetNutritionProfile": {
    "method": "POST",
    "path": "/v1/food-core-plans/profile",
    "parameters": []
  },
  "food_core_plans__validateProfile": {
    "method": "POST",
    "path": "/v1/food-core-plans/validate",
    "parameters": []
  },
  "nutrient_completion_plans__confirmRecipe": {
    "method": "POST",
    "path": "/v1/nutrient-completion-plans/confirm",
    "parameters": []
  },
  "nutrient_completion_plans__designDailyFreshFoodRecipe": {
    "method": "POST",
    "path": "/v1/nutrient-completion-plans",
    "parameters": []
  },
  "nutrient_completion_plans__generateCookingPlan": {
    "method": "POST",
    "path": "/v1/nutrient-completion-plans/cooking-plan",
    "parameters": []
  },
  "nutrient_completion_plans__getDiseaseCatalog": {
    "method": "GET",
    "path": "/v1/nutrient-completion-plans/disease-catalog",
    "parameters": []
  },
  "nutrient_completion_plans__getRecipe": {
    "method": "GET",
    "path": "/v1/nutrient-completion-plans/{recipe_id}",
    "parameters": [
      {
        "name": "recipe_id",
        "in": "path"
      },
      {
        "name": "recipe_version",
        "in": "query"
      }
    ]
  },
  "nutrient_completion_plans__recalculateRecipe": {
    "method": "POST",
    "path": "/v1/nutrient-completion-plans/recalculate",
    "parameters": []
  },
  "nutrient_completion_plans__replaceIngredient": {
    "method": "POST",
    "path": "/v1/nutrient-completion-plans/replace-ingredient",
    "parameters": []
  },
  "nutrient_completion_plans__updatePetNutritionProfile": {
    "method": "POST",
    "path": "/v1/nutrient-completion-plans/profile",
    "parameters": []
  },
  "nutrient_completion_plans__validateProfile": {
    "method": "POST",
    "path": "/v1/nutrient-completion-plans/validate",
    "parameters": []
  },
  "selectable_daily_plans__confirmRecipe": {
    "method": "POST",
    "path": "/v1/selectable-daily-plans/confirm",
    "parameters": []
  },
  "selectable_daily_plans__designDailyFreshFoodRecipe": {
    "method": "POST",
    "path": "/v1/selectable-daily-plans",
    "parameters": []
  },
  "selectable_daily_plans__generateCookingPlan": {
    "method": "POST",
    "path": "/v1/selectable-daily-plans/cooking-plan",
    "parameters": []
  },
  "selectable_daily_plans__getDiseaseCatalog": {
    "method": "GET",
    "path": "/v1/selectable-daily-plans/disease-catalog",
    "parameters": []
  },
  "selectable_daily_plans__getIngredientCatalog": {
    "method": "GET",
    "path": "/v1/selectable-daily-plans/ingredient-catalog",
    "parameters": []
  },
  "selectable_daily_plans__getRecipe": {
    "method": "GET",
    "path": "/v1/selectable-daily-plans/{recipe_id}",
    "parameters": [
      {
        "name": "recipe_id",
        "in": "path"
      },
      {
        "name": "recipe_version",
        "in": "query"
      }
    ]
  },
  "selectable_daily_plans__recalculateRecipe": {
    "method": "POST",
    "path": "/v1/selectable-daily-plans/recalculate",
    "parameters": []
  },
  "selectable_daily_plans__replaceIngredient": {
    "method": "POST",
    "path": "/v1/selectable-daily-plans/replace-ingredient",
    "parameters": []
  },
  "selectable_daily_plans__setIngredientSelection": {
    "method": "POST",
    "path": "/v1/selectable-daily-plans/ingredient-selection",
    "parameters": []
  },
  "selectable_daily_plans__updatePetNutritionProfile": {
    "method": "POST",
    "path": "/v1/selectable-daily-plans/profile",
    "parameters": []
  },
  "selectable_daily_plans__validateProfile": {
    "method": "POST",
    "path": "/v1/selectable-daily-plans/validate",
    "parameters": []
  },
  "scientific_daily_plans__confirmRecipe": {
    "method": "POST",
    "path": "/v1/scientific-daily-plans/confirm",
    "parameters": []
  },
  "scientific_daily_plans__designDailyFreshFoodRecipe": {
    "method": "POST",
    "path": "/v1/scientific-daily-plans",
    "parameters": []
  },
  "scientific_daily_plans__generateCookingPlan": {
    "method": "POST",
    "path": "/v1/scientific-daily-plans/cooking-plan",
    "parameters": []
  },
  "scientific_daily_plans__getDiseaseCatalog": {
    "method": "GET",
    "path": "/v1/scientific-daily-plans/disease-catalog",
    "parameters": []
  },
  "scientific_daily_plans__getIngredientCatalog": {
    "method": "GET",
    "path": "/v1/scientific-daily-plans/ingredient-catalog",
    "parameters": []
  },
  "scientific_daily_plans__getRecipe": {
    "method": "GET",
    "path": "/v1/scientific-daily-plans/{recipe_id}",
    "parameters": [
      {
        "name": "recipe_id",
        "in": "path"
      },
      {
        "name": "recipe_version",
        "in": "query"
      }
    ]
  },
  "scientific_daily_plans__recalculateRecipe": {
    "method": "POST",
    "path": "/v1/scientific-daily-plans/recalculate",
    "parameters": []
  },
  "scientific_daily_plans__replaceIngredient": {
    "method": "POST",
    "path": "/v1/scientific-daily-plans/replace-ingredient",
    "parameters": []
  },
  "scientific_daily_plans__setIngredientSelection": {
    "method": "POST",
    "path": "/v1/scientific-daily-plans/ingredient-selection",
    "parameters": []
  },
  "scientific_daily_plans__updatePetNutritionProfile": {
    "method": "POST",
    "path": "/v1/scientific-daily-plans/profile",
    "parameters": []
  },
  "scientific_daily_plans__validateProfile": {
    "method": "POST",
    "path": "/v1/scientific-daily-plans/validate",
    "parameters": []
  },
  "candidate_pool_meals__designQuickFreshMeal": {
    "method": "POST",
    "path": "/v1/candidate-pool-meals",
    "parameters": []
  },
  "candidate_pool_meals__getDiseaseCatalog": {
    "method": "GET",
    "path": "/v1/candidate-pool-meals/disease-catalog",
    "parameters": []
  },
  "candidate_pool_meals__getIngredientCatalog": {
    "method": "GET",
    "path": "/v1/candidate-pool-meals/ingredient-catalog",
    "parameters": []
  },
  "candidate_pool_meals__getQuickFreshMeal": {
    "method": "GET",
    "path": "/v1/candidate-pool-meals/{meal_id}",
    "parameters": [
      {
        "name": "meal_id",
        "in": "path"
      },
      {
        "name": "version",
        "in": "query"
      }
    ]
  },
  "candidate_pool_meals__getQuickMealCookingPlan": {
    "method": "GET",
    "path": "/v1/candidate-pool-meals/{meal_id}/cooking-plan",
    "parameters": [
      {
        "name": "meal_id",
        "in": "path"
      },
      {
        "name": "version",
        "in": "query"
      }
    ]
  },
  "candidate_pool_meals__recalculateQuickFreshMeal": {
    "method": "POST",
    "path": "/v1/candidate-pool-meals/recalculate",
    "parameters": []
  },
  "candidate_pool_meals__validateQuickMealProfile": {
    "method": "POST",
    "path": "/v1/candidate-pool-meals/validate",
    "parameters": []
  },
  "selected_ingredient_meals__cancelQuickFreshMeal": {
    "method": "POST",
    "path": "/v1/selected-ingredient-meals/cancel",
    "parameters": []
  },
  "selected_ingredient_meals__checkIngredientCombination": {
    "method": "POST",
    "path": "/v1/selected-ingredient-meals/check-combination",
    "parameters": []
  },
  "selected_ingredient_meals__designQuickFreshMeal": {
    "method": "POST",
    "path": "/v1/selected-ingredient-meals",
    "parameters": []
  },
  "selected_ingredient_meals__getDiseaseCatalog": {
    "method": "GET",
    "path": "/v1/selected-ingredient-meals/disease-catalog",
    "parameters": []
  },
  "selected_ingredient_meals__getIngredientCatalog": {
    "method": "POST",
    "path": "/v1/selected-ingredient-meals/ingredient-catalog",
    "parameters": []
  },
  "selected_ingredient_meals__getIngredientEligibility": {
    "method": "POST",
    "path": "/v1/selected-ingredient-meals/ingredient-eligibility",
    "parameters": []
  },
  "selected_ingredient_meals__getQuickFreshMeal": {
    "method": "GET",
    "path": "/v1/selected-ingredient-meals/{meal_id}",
    "parameters": [
      {
        "name": "meal_id",
        "in": "path"
      },
      {
        "name": "version",
        "in": "query"
      }
    ]
  },
  "selected_ingredient_meals__getQuickMealCookingPlan": {
    "method": "GET",
    "path": "/v1/selected-ingredient-meals/{meal_id}/cooking-plan",
    "parameters": [
      {
        "name": "meal_id",
        "in": "path"
      },
      {
        "name": "version",
        "in": "query"
      }
    ]
  },
  "selected_ingredient_meals__recalculateQuickFreshMeal": {
    "method": "POST",
    "path": "/v1/selected-ingredient-meals/recalculate",
    "parameters": []
  },
  "selected_ingredient_meals__resolveQuickMealLifeStage": {
    "method": "POST",
    "path": "/v1/selected-ingredient-meals/life-stage",
    "parameters": []
  },
  "selected_ingredient_meals__validateQuickMealProfile": {
    "method": "POST",
    "path": "/v1/selected-ingredient-meals/validate",
    "parameters": []
  },
  "version": {
    "method": "GET",
    "path": "/v1/version",
    "parameters": []
  }
});
