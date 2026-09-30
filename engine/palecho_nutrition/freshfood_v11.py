"""FreshFood 1.1 local service, sharing immutable journal infrastructure only."""
from copy import deepcopy
import uuid
from .freshfood import FreshFoodService, endpoint
from .freshfood_contract import require
from .practical import digest, RECOMMENDED
from .recipe_design import RecipeDesignEngine, ENGINE_VERSION, COMPONENTS
from .recipe_design_context import normalize_context
from .practical_preparation import prepare_practical


def design_service(service):
    """Borrow the connection and lock; the owning 1.0 service retains its lifetime."""
    if isinstance(service,FreshFoodDesignService):return service
    result=FreshFoodDesignService.__new__(FreshFoodDesignService)
    result.__dict__.update(service.__dict__)
    return result


class FreshFoodDesignService(FreshFoodService):
    def versions(self):
        return {**super().versions(),'api_version':'1.1','recipe_engine_version':ENGINE_VERSION}

    def generatePracticalRecipe(self,profile):
        return FreshFoodV1Adapter(self).generatePracticalRecipe(profile)

    def _snapshot_profile(self,body):return deepcopy(body['context']['pet_profile'])
    def _snapshot_details(self,body):return {'design_context':deepcopy(body['context'])}

    def _compute(self,body):
        design=RecipeDesignEngine(self.store).design(body['context'],excluded=body['excluded'],required=body['required'])
        body.update(context=design['context'],profile=design['profile'],specs=design['specs'],raw=design['raw'],
                    nutrition_design_target=design['target'],current_nutrition_estimate=design['estimate'])
        body['result']={**design['result'],**self.versions(),'recipe_id':body['recipe_id'],'recipe_version':body['version'],'profile_version':body['profile_version']}
        return body

    @endpoint
    def designFreshFoodRecipe(self,context):
        normalized,_,_,_=normalize_context(context,self.store)
        def op():
            # Own profile namespace; the same pet may keep a frozen 1.0 recipe.
            self.db.execute('CREATE TABLE IF NOT EXISTS design_profile_links(profile_id TEXT PRIMARY KEY,recipe_id TEXT NOT NULL UNIQUE REFERENCES recipes(id))')
            row=self.db.execute('SELECT recipe_id FROM design_profile_links WHERE profile_id=?',(normalized['pet_profile']['profile_id'],)).fetchone()
            if row:
                old=self._load(row[0]);require(old['profile']['species']==normalized['pet_profile']['species'],'PROFILE_SPECIES_IMMUTABLE')
                if old['context']==normalized and all(old['result'][k]==v for k,v in self.versions().items()):return old['result']
                new=self._next(old);new['context']=normalized;new['profile_version']+=1
            else:
                new={'recipe_id':'recipe11_'+uuid.uuid4().hex,'version':1,'profile_version':1,'context':normalized,'excluded':[],'required':[]}
            self._compute(new);self._write(new)
            if not row:self.db.execute('INSERT INTO design_profile_links VALUES (?,?)',(normalized['pet_profile']['profile_id'],new['recipe_id']))
            return new['result']
        return self._transaction(op)

    def _recalc_result(self,old,new):
        return {**self.versions(),'recipe_id':new['recipe_id'],'previous_version':old['version'],'new_version':new['version'],
                'status':new['result']['status'],'recipe':new['result'],'whole_recipe_recalculated':True,'errors':[],'warnings':new['result']['warnings']}

    @endpoint
    def updateDesignContext(self,recipe_id,context,expected_version=None):
        normalized,_,_,_=normalize_context(context,self.store)
        def op():
            old=self._load(recipe_id,expected_version)
            require(normalized['pet_profile']['profile_id']==old['profile']['profile_id'],'PROFILE_ID_CONFLICT')
            require(normalized['pet_profile']['species']==old['profile']['species'],'PROFILE_SPECIES_IMMUTABLE')
            new=self._next(old);new['context']=normalized;new['profile_version']+=1
            self._compute(new);self._write(new);return self._recalc_result(old,new)
        return self._transaction(op)

    @endpoint
    def setUserSupplementSpec(self,recipe_id,userSupplementSpec,expected_version=None):
        def op():
            old=self._load(recipe_id,expected_version);new=self._next(old);c=new['context'];spec=deepcopy(userSupplementSpec)
            require(isinstance(spec,dict),'INVALID_PRODUCT_SPEC')
            found=False
            for item in c['current_diet_context']['current_supplements']:
                if item.get('spec',{}).get('id')==spec.get('id'):
                    require(item['supplement_type']==spec.get('supplement_type'),'SUPPLEMENT_TYPE_CONFLICT')
                    item['spec']=spec;found=True
            if not found:c['available_supplements']=[s for s in c['available_supplements'] if s['id']!=spec.get('id')]+[spec]
            self._compute(new);self._write(new);return self._recalc_result(old,new)
        return self._transaction(op)

    @endpoint
    def replaceIngredient(self,request):
        require(isinstance(request,dict) and set(request)<={'recipe_id','source_ingredient_id','target_ingredient_id','expected_version','user_requested_amount'},'REPLACEMENT_REQUEST_INVALID')
        require(all(isinstance(request.get(k),str) for k in ('recipe_id','source_ingredient_id','target_ingredient_id')),'REPLACEMENT_REQUEST_INVALID')
        def op():
            old=self._load(request['recipe_id'],request.get('expected_version'));src=request['source_ingredient_id'];dst=request['target_ingredient_id'];defs=self.store.keyed('ingredients','ingredient_id')
            reasons=[]
            if old['result']['status'] not in RECOMMENDED:reasons.append('BASELINE_NOT_RECOMMENDED')
            if src not in {f['ingredient_id'] for f in old['result']['recipe_components']}:reasons.append('SOURCE_INGREDIENT_NOT_IN_RECIPE')
            if dst not in defs:reasons.append('UNKNOWN_INGREDIENT_ID')
            elif defs[dst]['toxicity_flag']:reasons.append('UNSAFE_INGREDIENT')
            elif src in defs and COMPONENTS.get(defs[src]['food_category'])!=COMPONENTS.get(defs[dst]['food_category']):reasons.append('COMPONENT_TYPE_CONFLICT')
            if src==dst:reasons.append('IDENTICAL_INGREDIENT')
            if request.get('user_requested_amount') is not None:reasons.append('FIXED_WEIGHT_REQUIRES_REDESIGN_CONSTRAINT')
            def reject(extra):return {**self._recalc_result(old,old),'status':'REPLACEMENT_REJECTED','reason_codes':extra,'whole_recipe_recalculated':False}
            if reasons:return reject(reasons)
            new=self._next(old);new['excluded']=sorted((set(new['excluded'])|{src})-{dst});new['required']=sorted((set(new['required'])-{src})|{dst})
            if 'available_ingredient_ids' in new['context']['pet_profile']:
                new['context']['pet_profile']['available_ingredient_ids']=sorted((set(new['context']['pet_profile']['available_ingredient_ids'])-{src})|{dst})
            self._compute(new)
            if new['result']['status'] not in RECOMMENDED:
                return {**reject(['NO_SAFE_REDESIGN']), 'attempted_status':new['result']['status'],'diagnostic_reason_codes':new['result']['reason_codes'],'whole_recipe_recalculated':True}
            self._write(new);return {**self._recalc_result(old,new),'status':'REPLACEMENT_ACCEPTED','equal_weight_swap':False}
        return self._transaction(op)

    def _cooking(self,body,snapshot_id,batch_days):
        # Re-run the 1.1 engine before materializing; no 1.0 semantic fallback.
        rebuilt=RecipeDesignEngine(self.store).design(body['context'],excluded=body['excluded'],required=body['required'])
        require(rebuilt['raw'].get('recipe_hash')==body['raw'].get('recipe_hash') and rebuilt['raw']['recipe_status'] in RECOMMENDED,'COOKING_PLAN_RECHECK_FAILED')
        raw=body['raw'];prepared=prepare_practical({**raw,'confirmed':True},self.store,days=batch_days,meals_per_day=raw['meals_per_day'])
        legacy=deepcopy(body)
        legacy['result']['safe_general_guidance']=raw['disease_advice']['daily_care']
        plan=super()._cooking(legacy,snapshot_id,batch_days,prepared=prepared)
        plan['daily_feeding_plan'].update(diet_scope=body['context']['feeding_goal'],recipe_kind=body['result']['recipe_summary']['recipe_kind'],fresh_food_share=body['result']['fresh_food_share'])
        plan['current_supplement_plan']=body['result']['nutrition_explanation']['current_supplement_contributions']
        plan['transition_plan']['current_diet_context']=body['context']['current_diet_context']
        if body['context']['feeding_goal']=='OCCASIONAL_MEAL':
            plan['daily_feeding_plan']['usage_note']='仅在计划喂食当天使用这一小餐；不按整天完整口粮喂食。'
        return plan


class FreshFoodV1Adapter:
    """Compatibility facade. 1.0 semantics and output contract remain unchanged."""
    def __init__(self,service):
        self.service=FreshFoodService.__new__(FreshFoodService)
        self.service.__dict__.update(service.__dict__)
    def generatePracticalRecipe(self,profile):return self.service.generatePracticalRecipe(profile)
