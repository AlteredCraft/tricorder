"""Download immutable SD captures over the local LAN and verify size/identity/SHA-256."""
import argparse
import hashlib
import json
from pathlib import Path
import re
from urllib.request import build_opener, ProxyHandler


def public_name(name):
    return isinstance(name,str) and len(name)<=90 and bool(re.fullmatch(r'ab-[a-z0-9-]+\.(raw|json)',name))


def validate_capture(capture_id, metadata, raw):
    if metadata.get('capture_id') != capture_id:
        raise ValueError('Capture identity mismatch')
    if type(metadata.get('size_bytes')) is not int or len(raw) != metadata['size_bytes']:
        raise ValueError('Capture size mismatch')
    if hashlib.sha256(raw).hexdigest() != metadata.get('sha256'):
        raise ValueError('Capture SHA-256 mismatch')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    opener=build_opener(ProxyHandler({}))
    def get(path,limit):
        with opener.open(args.url.rstrip('/')+path,timeout=20) as response:
            data=response.read(limit+1)
        if len(data)>limit:raise ValueError('Response exceeds size bound')
        return data
    listing=json.loads(get('/test-files',32768))
    names=listing.get('files')
    if not isinstance(names,list) or len(names)>128 or any(not public_name(n) for n in names):
        raise ValueError('Invalid public file listing')
    records=[]
    for name in sorted(set(names)):
        if not name.endswith('.json'):continue
        capture_id=name[:-5]
        record={'capture_id':capture_id,'status':'fail'}
        try:
            meta_bytes=get('/test-file/'+name,32768)
            metadata=json.loads(meta_bytes)
            raw=get('/test-file/'+capture_id+'.raw',1152000)
            # Retain downloads before assessment; failed bytes remain evidence.
            (args.output/name).write_bytes(meta_bytes)
            (args.output/(capture_id+'.raw')).write_bytes(raw)
            validate_capture(capture_id,metadata,raw)
            record.update(status='pass',size_bytes=len(raw),sha256=metadata['sha256'],format=metadata.get('format'))
        except Exception as error:
            record['error']=str(error)
        records.append(record)
    orphans=sorted(n for n in names if n.endswith('.raw') and n[:-4]+'.json' not in names)
    summary={'status':'pass' if records and all(r['status']=='pass' for r in records) and not listing.get('truncated') and not orphans else 'incomplete',
             'captures':records,'orphan_raw_files':orphans,'listing_truncated':bool(listing.get('truncated')),
             'scope':'Stored byte integrity only; synthetic storage files are not acoustic or A/B evidence.'}
    (args.output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2))
    if summary['status']!='pass':raise SystemExit(1)


if __name__=='__main__':main()
