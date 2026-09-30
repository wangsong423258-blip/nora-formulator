"""One local JSON request/response boundary; never opens a listening socket."""
from .freshfood_contract import error
METHODS={
 'validateProfile':({'profile'},set()),
 'generatePracticalRecipe':({'profile'},set()),
 'getRecipe':({'recipe_id'},{'recipe_version'}),
 'setUserSupplementSpec':({'recipe_id','userSupplementSpec'},{'expected_version'}),
 'recalculateRecipe':({'recipe_id'},{'expected_version'}),
 'replaceIngredient':({'request'},set()),
 'updatePetNutritionProfile':({'recipe_id','profile'},{'expected_version'}),
 'confirmRecipe':({'recipe_id'},{'expected_version'}),
 'generateCookingPlan':({'confirmed_recipe_id'},{'batch_days'}),
}
DESIGN_METHODS={
 'designFreshFoodRecipe':({'context'},set()),
 'updateDesignContext':({'recipe_id','context'},{'expected_version'}),
 **{k:v for k,v in METHODS.items() if k in {'getRecipe','setUserSupplementSpec','recalculateRecipe','replaceIngredient','confirmRecipe','generateCookingPlan'}},
}
DAILY_METHODS={
 'designDailyFreshFoodRecipe':({'profile'},set()),
 'getDiseaseCatalog':(set(),set()),
 **{k:v for k,v in METHODS.items() if k != 'generatePracticalRecipe'},
}
def dispatch(service,request):
 def fail(code,field):return {**service.versions(),'status':'ERROR','errors':[error(code,field)],'warnings':[]}
 if not isinstance(request,dict) or set(request)!={'api_version','method','params'}:return fail('REQUEST_ENVELOPE_INVALID',None)
 if request['api_version'] not in ('1.0','1.1','1.2','1.3','1.4','1.5','1.6','1.7','1.8','1.9'):return fail('API_VERSION_UNSUPPORTED','api_version')
 methods=METHODS
 if request['api_version']=='1.9':
  from .freshfood_v19 import ingredient_first_service
  service=ingredient_first_service(service);methods={
   'designQuickFreshMeal':({'profile'},{'ingredientSelection'}),
   'getQuickFreshMeal':({'meal_id'},{'version'}),
   'recalculateQuickFreshMeal':({'meal_id'},{'profile','ingredientSelection','expected_version'}),
   'getQuickMealCookingPlan':({'meal_id'},{'version'}),
   'validateQuickMealProfile':({'profile'},set()),
   'resolveQuickMealLifeStage':({'profile'},set()),
   'cancelQuickFreshMeal':(set(),set()),
   'getIngredientCatalog':({'profile'},set()),'getIngredientEligibility':({'profile'},set()),
   'checkIngredientCombination':({'profile','ingredientSelection'},set()),
   'upgradeQuickFreshMeal':({'meal_id','ingredientSelection'},set()),
   'getScientificSourceRegistry':(set(),set()),'getDiseaseCatalog':(set(),set())}
 elif request['api_version']=='1.8':
  from .freshfood_v18 import quick_service
  service=quick_service(service);methods={
   'designQuickFreshMeal':({'profile'},{'ingredientSelection'}),
   'getQuickFreshMeal':({'meal_id'},{'version'}),
   'recalculateQuickFreshMeal':({'meal_id'},{'profile','ingredientSelection','expected_version'}),
   'getQuickMealCookingPlan':({'meal_id'},{'version'}),
   'validateQuickMealProfile':({'profile'},set()),
   'getIngredientCatalog':(set(),set()),'getDiseaseCatalog':(set(),set())}
 elif request['api_version']=='1.1':
  from .freshfood_v11 import design_service
  service=design_service(service);methods=DESIGN_METHODS
 elif request['api_version']=='1.7':
  from .freshfood_v17 import daily_service
  service=daily_service(service);methods={**{k:v for k,v in DAILY_METHODS.items() if k!='setUserSupplementSpec'},'recalculateDailyRecipe':METHODS['recalculateRecipe'],
   'getIngredientCatalog':(set(),set()),'setIngredientSelection':({'recipe_id','ingredient_selection'},{'expected_version'})}
 elif request['api_version']=='1.6':
  from .freshfood_v16 import daily_service
  service=daily_service(service);methods={**{k:v for k,v in DAILY_METHODS.items() if k!='setUserSupplementSpec'},'recalculateDailyRecipe':METHODS['recalculateRecipe'],
   'getIngredientCatalog':(set(),set()),'setIngredientSelection':({'recipe_id','ingredient_selection'},{'expected_version'})}
 elif request['api_version']=='1.5':
  from .freshfood_v15 import daily_service
  service=daily_service(service);methods={**{k:v for k,v in DAILY_METHODS.items() if k!='setUserSupplementSpec'},'recalculateDailyRecipe':METHODS['recalculateRecipe']}
 elif request['api_version']=='1.4':
  from .freshfood_v14 import daily_service
  service=daily_service(service);methods={**{k:v for k,v in DAILY_METHODS.items() if k!='setUserSupplementSpec'},'recalculateDailyRecipe':METHODS['recalculateRecipe']}
 elif request['api_version']=='1.3':
  from .freshfood_v13 import daily_service
  service=daily_service(service);methods={**DAILY_METHODS,'recalculateDailyRecipe':METHODS['recalculateRecipe']}
 elif request['api_version']=='1.2':
  from .freshfood_v12 import daily_service
  service=daily_service(service);methods=DAILY_METHODS
 elif service.versions()['api_version'] != '1.0':
  from .freshfood import FreshFoodService
  base=FreshFoodService.__new__(FreshFoodService);base.__dict__.update(service.__dict__);service=base
 method=request['method'];params=request['params']
 if not isinstance(method,str) or method not in methods:return fail('METHOD_UNKNOWN','method')
 required,optional=methods[method]
 if not isinstance(params,dict) or not required<=set(params) or not set(params)<=required|optional:return fail('METHOD_PARAMETERS_INVALID','params')
 return getattr(service,method)(**params)
