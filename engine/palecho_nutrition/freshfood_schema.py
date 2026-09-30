"""Offline structural validation of our frozen JSON Schema subset (no resolver)."""
import json,math,re
from pathlib import Path
from .freshfood_contract import ContractError
SCHEMA=json.loads(Path(__file__).with_name('freshfood_api_v1.schema.json').read_text())
def validate_model(name,value,*,schema=None):
 schema=SCHEMA if schema is None else schema
 def walk(rule,v,path):
  if '$ref' in rule:return walk(schema['$defs'][rule['$ref'].rsplit('/',1)[1]],v,path)
  if 'oneOf' in rule:
   valid=0
   for r in rule['oneOf']:
    try:walk(r,v,path);valid+=1
    except ContractError:pass
   if valid!=1:raise ContractError('CONTRACT_SCHEMA_INVALID',path)
  types=rule.get('type');types=[types] if isinstance(types,str) else types
  checks={'null':v is None,'boolean':type(v) is bool,'integer':type(v) is int,'number':type(v) in (int,float) and math.isfinite(v),'string':isinstance(v,str),'array':isinstance(v,list),'object':isinstance(v,dict)}
  def check(ok):
   if not ok:raise ContractError('CONTRACT_SCHEMA_INVALID',path)
  if types:check(any(checks[t] for t in types))
  if 'const' in rule:check(v==rule['const'] and (type(v) is not bool or type(rule['const']) is bool))
  if 'enum' in rule:check(v in rule['enum'] and (type(v) is not bool or any(type(x) is bool and x==v for x in rule['enum'])))
  if isinstance(v,dict):
   check(set(rule.get('required',[]))<=set(v));props=rule.get('properties',{})
   if rule.get('additionalProperties') is False:check(set(v)<=set(props))
   for k in set(v)&set(props):walk(props[k],v[k],path+'.'+k)
  if isinstance(v,list):
   if 'minItems' in rule:check(len(v)>=rule['minItems'])
   for i,x in enumerate(v):walk(rule.get('items',{}),x,path+'['+str(i)+']')
  if isinstance(v,str) and 'pattern' in rule:check(re.fullmatch(rule['pattern'],v) is not None)
  if type(v) in (int,float):
   if 'minimum' in rule:check(v>=rule['minimum'])
   if 'maximum' in rule:check(v<=rule['maximum'])
   if 'exclusiveMinimum' in rule:check(v>rule['exclusiveMinimum'])
 walk(schema['$defs'][name],value,name);return True
