"""Export the original nutrition database as inspectable, unencrypted JSON."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from palecho_nutrition.store import Store


def write(path,value):
    data=(json.dumps(value,ensure_ascii=False,allow_nan=False,indent=2)+'\n').encode()
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('database',type=Path)
    parser.add_argument('output',type=Path)
    args=parser.parse_args()
    if args.output.exists():parser.error('output directory already exists')
    args.output.mkdir(parents=True)
    with Store(args.database) as source:
        files={'meta.json':write(args.output/'meta.json',source.meta)}
        for name,rows in source.tables.items():
            rel='tables/'+name+'.json'
            files[rel]=write(args.output/rel,rows)
    write(args.output/'manifest.json',{'format':'nora-plain-data-v1','files':files})
    print(f'Exported {len(files)} plaintext files to {args.output}')


if __name__=='__main__':main()
