"""Master.xlsx -> validated normalized staging DB -> tests -> atomic artifact replacement."""
import argparse, hashlib, json, os, re, sqlite3, subprocess, sys, tempfile,zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from .master import SCHEMA,read_master
from .validation import (validate_master,normalize_units,validate_sources,validate_disease_rules,
                         validate_foods,validate_constraints,validate_release,MasterError)

ROOT=Path(__file__).resolve().parents[1]
DEFAULT=ROOT/'outputs/palecho-nutrition-v1'

def canonical_digest(t):
    v=t['18_Versions'][0];excluded={v['expert_signoff'],v['recipe_process_validation']}
    content={name:rows for name,rows in t.items() if name not in ['16_Evidence_Map','17_Test_Cases','18_Versions']}
    # Safety policies must be covered by signatures too; changing weighing or
    # unresolved conflicts must invalidate prior recipe/process approvals.
    content['runtime_policy']=json.loads(v['runtime_config_json'])
    content['schema_version']=v['schema_version']
    content['15_Sources']=[s for s in t['15_Sources'] if s['source_id'] not in excluded]
    return hashlib.sha256(json.dumps(content,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()

def _certificates(t,root,data_hash):
    v=t['18_Versions'][0];sources={r['source_id']:r for r in t['15_Sources']};certs={}
    for field in ['expert_signoff','recipe_process_validation']:
        sid=v[field]
        if sid is None:continue
        path=Path(root)/sources[sid]['local_file']
        cert=json.loads(path.read_text())
        if cert.get('data_content_sha256')!=data_hash:raise MasterError('Review certificate does not cover this exact data content')
        if not cert.get('reviewer') or not cert.get('reviewed_at'):raise MasterError('Independent named review/date missing')
        if field=='expert_signoff' and not all(cert.get(k) for k in ['qualifications','species_life_stage_scope','conditional_nutrients_reviewed','bioavailability_review']):
            raise MasterError('Expert certificate must review applicability, conditional nutrients and bioavailability')
        if field=='recipe_process_validation' and not all(cert.get(k) for k in ['food_process_retention_review','nutrient_stability_review','approved_recipe_hashes','preparation_protocols']):
            raise MasterError('Process certificate requires retention/stability evidence and matched recipe protocols')
        certs[field]=cert
    process=certs.get('recipe_process_validation',{})
    if process and set(process['approved_recipe_hashes'])!=set(process['preparation_protocols']):raise MasterError('Every approved recipe requires a matching preparation protocol')
    return process.get('approved_recipe_hashes',[]),process.get('preparation_protocols',{})

def build_sqlite(t,path,metadata):
    db=sqlite3.connect(path)
    try:
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('BEGIN')
        for name,spec in SCHEMA.items():
            columns=[]
            for c,typ in spec['columns'].items():
                sqltyp='INTEGER' if typ=='BOOLEAN' else typ
                declaration=f'"{c}" {sqltyp}'
                if c==spec['pk']:declaration+=' PRIMARY KEY NOT NULL'
                if typ=='BOOLEAN':declaration+=f' CHECK ("{c}" IN (0,1) OR "{c}" IS NULL)'
                # Deferred FKs allow the ordered workbook sheets to stay human-friendly.
                parent={'source_id':('sources','source_id'),'nutrient_id':('nutrients','nutrient_id'),
                        'ingredient_id':('ingredients','ingredient_id'),'disease_id':('diseases','disease_id'),
                        'cooking_method_id':('cooking_methods','cooking_method_id')}.get(c)
                if parent and not (spec['table']==parent[0] and c==spec['pk']):
                    declaration+=f' REFERENCES "{parent[0]}"("{parent[1]}") DEFERRABLE INITIALLY DEFERRED'
                columns.append(declaration)
            db.execute('CREATE TABLE "'+spec['table']+'" ('+','.join(columns)+')')
        db.execute('CREATE TABLE build_metadata (key TEXT PRIMARY KEY,value TEXT NOT NULL)')
        for name,spec in SCHEMA.items():
            headers=list(spec['columns']);params=','.join('?' for h in headers)
            db.executemany('INSERT INTO "'+spec['table']+'" VALUES ('+params+')',[[r[h] for h in headers] for r in t[name]])
        db.executemany('INSERT INTO build_metadata VALUES (?,?)',[(k,json.dumps(v,ensure_ascii=False,allow_nan=False)) for k,v in metadata.items()])
        db.execute('CREATE UNIQUE INDEX ingredient_vector_key ON ingredient_nutrients(ingredient_id,nutrient_id)')
        db.execute('CREATE INDEX requirements_lookup ON requirements(profile_id,nutrient_id)')
        db.execute('CREATE INDEX disease_rule_lookup ON disease_rules(disease_id,species)')
        db.execute('CREATE UNIQUE INDEX lifestyle_key ON disease_lifestyle(disease_id,field)')
        db.execute('CREATE INDEX evidence_row_lookup ON evidence_map(table_name,row_id)')
        db.execute('CREATE VIEW unknown_nutrients AS SELECT * FROM ingredient_nutrients WHERE value IS NULL')
        db.execute('CREATE VIEW ingredient_readiness AS SELECT ingredient_id,name_zh,recipe_eligible,review_status,review_reason FROM ingredients')
        db.commit()
        if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise MasterError('SQLite integrity check failed')
        if db.execute('PRAGMA foreign_key_check').fetchall():raise MasterError('SQLite foreign key check failed')
    finally:db.close()

def run_regression_tests(db_path,t,output,master):
    from .store import Store
    from .runtime import solve
    matrix=[]
    with Store(db_path) as store:
        for r in t['17_Test_Cases']:
            result=solve(json.loads(r['input_json']),store)
            matrix.append({'test_id':r['test_id'],'expected':r['expected_status'],'actual':result['recipe_status'],
                           'status':'PASS' if result['recipe_status']==r['expected_status'] else 'FAIL',
                           'profile_id':result.get('profile_id'),'reason':result.get('reasons')})
    env=dict(os.environ,PALECHO_TEST_DB=str(db_path),PALECHO_TEST_MASTER=str(master))
    cp=subprocess.run([sys.executable,'-m','unittest','discover','-s',str(ROOT/'tests'),'-v'],cwd=ROOT,env=env,capture_output=True,text=True,timeout=900)
    qa=output/'qa';qa.mkdir(exist_ok=True)
    (qa/'test_output.txt').write_text(cp.stdout+'\n'+cp.stderr)
    count=re.search(r'Ran (\d+) tests?',cp.stderr)
    result={'status':'PASS' if cp.returncode==0 and all(r['status']=='PASS' for r in matrix) and count else 'FAIL',
            'unit_tests':int(count.group(1)) if count else 0,'unit_test_exit_code':cp.returncode,'matrix':matrix,
            'validated_real_recipes':sum(r['actual']=='VALIDATED' for r in matrix)}
    (qa/'regression_results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    if result['status']!='PASS':raise MasterError('Regression tests failed; see qa/test_output.txt and regression_results.json')
    return result

def build(master,output,*,review=False,run_tests=True):
    """Public build. Tests cannot be disabled in a release or artifact-producing review build."""
    if not run_tests:raise MasterError('Test bypass is not permitted')
    master=Path(master).resolve();output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
    checks={};raw=read_master(master);checks['validate_master']=validate_master(raw)
    t,checks['normalize_units']=normalize_units(raw)
    checks['validate_sources']=validate_sources(t,ROOT)
    checks['validate_disease_rules']=validate_disease_rules(t)
    checks['validate_foods']=validate_foods(t)
    checks['validate_constraints']=validate_constraints(t)
    checks['clinical_release']=validate_release(t,ROOT)
    data_hash=canonical_digest(t)
    approved,protocols=_certificates(t,ROOT,data_hash)
    if not review and (checks['clinical_release']['status']!='PASS' or not approved):
        (output/'release_blocked.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2))
        raise MasterError('Production release BLOCKED: '+ '; '.join(checks['clinical_release']['reasons'] or ['No reviewed recipe/process certificates']))
    meta={'schema_version':6,'data_version':t['18_Versions'][0]['data_version'],
          'production_ready':not review and checks['clinical_release']['status']=='PASS',
          'build_mode':'REVIEW_ONLY' if review else 'RELEASE','master_sha256':hashlib.sha256(master.read_bytes()).hexdigest(),
          'data_content_sha256':data_hash,'approved_recipe_hashes':approved,'preparation_protocols':protocols,
          'runtime_network_allowed':False,'source_of_truth':'Master.xlsx'}
    fd,staging=tempfile.mkstemp(prefix='.nutrition-',suffix='.db',dir=output);os.close(fd)
    try:
        build_sqlite(t,staging,meta);checks['build_sqlite']={'status':'PASS'}
        checks['run_regression_tests']=run_regression_tests(staging,t,output,master)
        if not review:
            tested={r['profile_id'] for r in checks['run_regression_tests']['matrix'] if r['actual']=='VALIDATED'}
            expected={r['profile_id'] for r in t['02_Requirements']}
            if not tested>=expected:raise MasterError('Release requires real approved full-diet regression coverage of every nutrient profile')
        # Runtime does not need this UI/config text file. No nutrient concentrations are duplicated here.
        config={'schema_version':6,'production_ready':meta['production_ready'],'data_content_sha256':data_hash,
                'runtime_policy':json.loads(t['18_Versions'][0]['runtime_config_json']),
                'supplement_selection_guides':t['21_Supplement_Guides'],
                'supplement_quality_guides':t['22_Quality_Guides'],
                'nutrient_categories':sorted({r['display_category'] for r in t['01_Nutrients']}),
                'status_text_zh':{'VALIDATED':'全部适用营养校验通过且具有匹配的专业审查记录。','NO_VALID_RECIPE':'没有满足全部硬约束的配方。','NEEDS_REVIEW':'证据或制作验证不足。','REQUIRES_PROFESSIONAL_REVIEW':'需要专业营养或临床审查。','AUTO_RECIPE_BLOCKED':'当前状况禁止自动配方。','UNSUPPORTED':'本版本不支持此用途或生命阶段。'}}
        cfg=output/'.rules.json.tmp';cfg.write_text(json.dumps(config,ensure_ascii=False,indent=2))
        os.replace(staging,output/'nutrition.db');os.replace(cfg,output/'rules.json')
        checks['artifact_sha256']=hashlib.sha256((output/'nutrition.db').read_bytes()).hexdigest()
        (output/'qa'/'build_report.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2))
    finally:
        if Path(staging).exists():Path(staging).unlink()
    return checks

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--master',type=Path,default=DEFAULT/'Master.xlsx');ap.add_argument('--output',type=Path,default=DEFAULT)
    ap.add_argument('--review',action='store_true',help='Create a clearly marked review database, never a production release')
    args=ap.parse_args()
    try:
        result=build(args.master,args.output,review=args.review)
        print(json.dumps({'data_checks':'PASS','tests':'PASS','clinical_release':result['clinical_release'],'output':str(args.output)},ensure_ascii=False,indent=2))
    except (MasterError,ValueError,KeyError,OSError,zipfile.BadZipFile,ET.ParseError,sqlite3.Error) as e:print('BUILD BLOCKED: '+str(e),file=sys.stderr);sys.exit(2)

if __name__=='__main__':main()
