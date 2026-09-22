"""Read one provider-specific key locally, without shell evaluation or logging."""
import os
from pathlib import Path


def load_api_key(provider, path=None, *, environ=None):
    names={'openai':'OPENAI_API_KEY','openrouter':'OPENROUTER_API_KEY'}
    if provider not in names:raise ValueError('Unknown API provider')
    name=names[provider]
    if path is None:
        key=(os.environ if environ is None else environ).get(name,'')
    else:
        path=Path(path)
        if path.stat().st_size>16384:raise ValueError('API configuration exceeds size bound')
        values={}
        for line in path.read_text().splitlines():
            line=line.strip()
            if not line or line.startswith('#'):continue
            if '=' not in line:raise ValueError('Invalid API configuration assignment')
            key_name,value=line.split('=',1);key_name=key_name.strip();value=value.strip()
            if key_name in values:raise ValueError('Duplicate API configuration assignment')
            if len(value)>=2 and value[0]==value[-1] and value[0] in ('\"',"'"):
                value=value[1:-1]
            values[key_name]=value
        key=values.get(name,'')
    if not isinstance(key,str) or not 1<=len(key)<=512 or any(ord(c)<33 or ord(c)>126 for c in key):
        raise ValueError(f'Missing or invalid {name} in local configuration')
    return key
