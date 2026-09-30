"""Read the sole maintenance workbook without Excel, servers or formula evaluation."""
from pathlib import Path, PurePosixPath
import json, re, zipfile
import xml.etree.ElementTree as ET
from .units import number

SCHEMA=json.loads(Path(__file__).with_name('schema.json').read_text())
NS={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
REL='http://schemas.openxmlformats.org/officeDocument/2006/relationships'

class MasterError(ValueError): pass

def read_master(path):
    with zipfile.ZipFile(path) as z:
        if sum(i.file_size for i in z.infolist())>100_000_000:
            raise MasterError('Workbook exceeds 100 MB uncompressed safety limit')
        shared=[]
        if 'xl/sharedStrings.xml' in z.namelist():
            root=ET.fromstring(z.read('xl/sharedStrings.xml'))
            shared=[''.join(e.itertext()) for e in root.findall('m:si',NS)]
        rels={r.attrib['Id']:r.attrib['Target'] for r in ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))}
        workbook=ET.fromstring(z.read('xl/workbook.xml'))
        sheets=workbook.findall('m:sheets/m:sheet',NS)
        if {s.attrib['name'] for s in sheets}!=set(SCHEMA):
            raise MasterError('Expected exactly the versioned schema sheets; migrate schema for new sheets')
        out={}
        for sh in sheets:
            name=sh.attrib['name'];target=rels[sh.attrib['{'+REL+'}id']]
            if '://' in target or '..' in PurePosixPath(target).parts: raise MasterError('External/path traversal worksheet')
            file=target.lstrip('/') if target.startswith('/') else 'xl/'+target
            root=ET.fromstring(z.read(file));data={}
            for c in root.findall('m:sheetData/m:row/m:c',NS):
                ref=c.attrib['r']
                if c.find('m:f',NS) is not None: raise MasterError(f'{name}!{ref}: formulas prohibited; enter sourced values')
                match=re.fullmatch(r'([A-Z]+)([1-9][0-9]*)',ref)
                if not match: raise MasterError('Invalid cell address')
                col=0
                for ch in match[1]:col=col*26+ord(ch)-64
                row=int(match[2]); typ=c.attrib.get('t');v=c.find('m:v',NS)
                if typ=='inlineStr':val=''.join(c.find('m:is',NS).itertext())
                elif v is None:val=None
                elif typ=='s':val=shared[int(v.text)]
                elif typ=='b':
                    if v.text not in ['0','1']:raise MasterError('Invalid boolean')
                    val=v.text=='1'
                elif typ=='str':val=v.text
                elif typ in ['e','d']:raise MasterError(f'{name}!{ref}: unsupported cell type {typ}')
                else:val=number(float(v.text))
                if val=='':val=None
                if val is not None:data[(row,col)]=val
            columns=list(SCHEMA[name]['columns'])
            if [data.get((1,c+1)) for c in range(len(columns))]!=columns:
                raise MasterError(f'{name}: headers/order differ from schema')
            if any(c>len(columns) for r,c in data):raise MasterError(f'{name}: unknown extra columns')
            rows=[]
            for n in sorted({r for r,c in data if r>1}):
                row={h:data.get((n,i+1)) for i,h in enumerate(columns)}
                rows.append(row)
            if not rows:raise MasterError(f'{name}: empty required sheet')
            out[name]=rows
        return out

def by_table(tables):
    return {SCHEMA[k]['table']:v for k,v in tables.items()}
