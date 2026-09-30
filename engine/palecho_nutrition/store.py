import hashlib, json, sqlite3
from pathlib import Path
from .master import SCHEMA

class Store:
    """Immutable, local, read-only database. No connector or HTTP dependency."""
    def __init__(self,path):
        self.path=Path(path).resolve()
        self.connection=None
        if self.path.is_dir():
            manifest=json.loads((self.path/'manifest.json').read_text())
            names={'meta.json',*(f'tables/{spec["table"]}.json' for spec in SCHEMA.values())}
            if manifest.get('format')!='nora-plain-data-v1' or set(manifest.get('files',{}))!=names:
                raise ValueError('Invalid plain data manifest')
            def load(name):
                source=self.path/name
                if source.is_symlink() or not source.is_file():raise ValueError('Invalid plain data file')
                data=source.read_bytes()
                if hashlib.sha256(data).hexdigest()!=manifest['files'][name]:
                    raise ValueError('Plain data integrity mismatch: '+name)
                return json.loads(data)
            self.meta=load('meta.json')
            self.tables={spec['table']:load(f'tables/{spec["table"]}.json') for spec in SCHEMA.values()}
        else:
            self.connection=sqlite3.connect(self.path.as_uri()+'?mode=ro&immutable=1',uri=True)
            self.connection.row_factory=sqlite3.Row
            self.meta={r['key']:json.loads(r['value']) for r in self.connection.execute('SELECT key,value FROM build_metadata')}
            self.tables={}
            for spec in SCHEMA.values():
                rows=[dict(r) for r in self.connection.execute('SELECT * FROM "'+spec['table']+'" ORDER BY "'+spec['pk']+'"')]
                for r in rows:
                    for c,t in spec['columns'].items():
                        if t=='BOOLEAN' and r[c] is not None:r[c]=bool(r[c])
                self.tables[spec['table']]=rows
        if self.meta.get('schema_version')!=6:raise ValueError('Unsupported nutrition schema; rebuild from Master')
        for spec in SCHEMA.values():
            rows=self.tables[spec['table']]
            if not isinstance(rows,list) or any(not isinstance(r,dict) or set(r)!=set(spec['columns']) for r in rows):
                raise ValueError('Invalid nutrition table: '+spec['table'])
            ids=[r[spec['pk']] for r in rows]
            if ids!=sorted(ids) or len(ids)!=len(set(ids)):
                raise ValueError('Invalid nutrition table ordering: '+spec['table'])
        self.config=json.loads(self.tables['versions'][0]['runtime_config_json'])

    def rows(self,name):return self.tables[name]
    def keyed(self,name,key):return {r[key]:r for r in self.rows(name)}
    def close(self):
        if self.connection is not None:self.connection.close()
    def __enter__(self):return self
    def __exit__(self,*args):self.close()

def matches(condition,context):
    """Deliberately tiny, total predicate language. Missing values NEVER match."""
    for k,want in condition.items():
        if k not in context or context[k] is None:return False
        got=context[k]
        if isinstance(want,dict):
            for op,v in want.items():
                if op=='in':
                    if got not in v:return False
                    continue
                if type(got) not in (int,float):return False
                if op=='gt' and not got>v:return False
                if op=='gte' and not got>=v:return False
                if op=='lt' and not got<v:return False
                if op=='lte' and not got<=v:return False
                if op=='eq' and got!=v:return False
                if op not in {'gt','gte','lt','lte','eq'}:raise ValueError('Unsupported predicate')
        elif type(got) is not type(want) or got!=want:return False
    return True
