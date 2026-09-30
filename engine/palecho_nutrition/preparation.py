"""Preparation is a downstream gate, never a way around nutritional review."""
from .runtime import audit_recipe,recipe_digest
from .profile import assess

def prepare(pet,grams,store,*,days,meals_per_day):
    if type(days) is not int or days<=0 or type(meals_per_day) is not int or meals_per_day<=0:
        return {'recipe_status':'INVALID_INPUT','reasons':['days and meals_per_day must be positive integers']}
    checked=audit_recipe(pet,grams,store)
    if checked['recipe_status']!='VALIDATED':return checked
    foods=store.keyed('ingredients','ingredient_id');methods=store.keyed('cooking_methods','cooking_method_id');shopping=[];missing=[]
    for i,g in grams.items():
        f=foods[i];method=methods.get(f['cooking_method_id'])
        if f['raw_purchase_yield'] is None:missing.append(i+': raw edible purchase yield not verified')
        if method is None:missing.append(i+': cooking method unknown')
        if f['edible_fraction'] is None:missing.append(i+': purchased edible fraction unknown')
        shopping.append({'ingredient_id':i,'name_zh':f['name_zh'],'daily_consumed_g':g,'batch_consumed_g':g*days,
                         'weighing_state':f['food_state'],'skin_bone_shell_requirements':f['edible_portion'],
                         'raw_edible_purchase_g':None if f['raw_purchase_yield'] is None else g*days/f['raw_purchase_yield'],
                         'gross_purchase_g':None if f['raw_purchase_yield'] is None or f['edible_fraction'] is None else g*days/f['raw_purchase_yield']/f['edible_fraction'],
                         'cooking':None if method is None else method['instructions_zh'],'source_id':f['source_id']})
    for s in store.rows('supplements'):
        if s['ingredient_id'] in grams and (s['add_after_cooling'] is None or not s['assay_source_id']):missing.append(s['supplement_id']+': mixing and stability unknown')
    # No guessed raw weights, cuts, losses or shelf life. A validated process certificate supplies these.
    digest=recipe_digest(grams,assess(pet,store),store)
    protocol=store.meta.get('preparation_protocols',{}).get(digest)
    if protocol is None:missing.append('No matching verified cutting/mixing/storage protocol')
    else:
        for field in ['cutting','cooking','mixing_order','cool_additions','storage_schedule','max_batch_days','source_ids']:
            if protocol.get(field) is None:missing.append('Process certificate missing '+field)
        if type(protocol.get('max_batch_days')) is not int or days>protocol['max_batch_days']:missing.append('Batch duration exceeds verified recipe/process shelf-life')
    if missing:return {'recipe_status':'PREPARATION_NEEDS_REVIEW','reasons':missing,'shopping_audit':shopping,'complete_balanced_claim':False}
    total=sum(grams.values())
    return {'recipe_status':'VALIDATED','shopping_list':shopping,'daily_total_g':total,'meals_per_day':meals_per_day,'per_meal_g':total/meals_per_day,
            'batch_days':days,'daily_packages':days,'package_g':total,'protocol':protocol,
            'food_safety':[r for r in methods.values() if r['food_state']=='SAFETY_RULE']}
