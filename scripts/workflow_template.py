"""Adapt a reviewed ComfyUI API export with explicit parameter slots; never queue."""
import argparse
import copy
import json
from pathlib import Path
import urllib.request
from kit_config import URL

PARAMETERS={'prompt','negative','seed','steps','width','height','unet','clip','vae','prefix'}
def load(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def adapt(graph,slots,save):
    graph=copy.deepcopy(graph)
    if not graph or not all(isinstance(n,dict) and 'class_type' in n and 'inputs' in n for n in graph.values()):
        raise ValueError('Export API format from ComfyUI; UI nodes/links/subgraphs cannot be guessed')
    if graph.get(save,{}).get('class_type') not in ('SaveImage','SaveImageAdvanced'):raise ValueError('Select the final SaveImage or SaveImageAdvanced node ID')
    if '9' in graph and save!='9':
        replacement='poseloom_original_9'
        while replacement in graph:replacement+='x'
        graph[replacement]=graph.pop('9')
        for node in graph.values():
            for value in node['inputs'].values():
                if isinstance(value,list) and len(value)==2 and value[0]=='9':value[0]=replacement
        slots={k:[replacement if v[0]=='9' else v[0],v[1]] for k,v in slots.items()}
    if save!='9':
        graph['9']=graph.pop(save)
        for node in graph.values():
            for value in node['inputs'].values():
                if isinstance(value,list) and len(value)==2 and value[0]==save:value[0]='9'
        slots={k:['9' if v[0]==save else v[0],v[1]] for k,v in slots.items()}
    if not {'prompt','seed','width','height'}<=slots.keys():raise ValueError('Map prompt, seed, width and height')
    for parameter,(node,key) in slots.items():
        if parameter not in PARAMETERS or node not in graph or key not in graph[node]['inputs']:raise ValueError('Invalid slot: '+parameter)
        graph[node]['inputs'][key]='${'+parameter+'}'
    graph['9']['inputs']['filename_prefix']='${prefix}'
    return graph

def resolve(graph,values):
    def replace(value):
        if isinstance(value,str) and value.startswith('${') and value.endswith('}'):
            return values[value[2:-1]]
        if isinstance(value,dict):return {k:replace(v) for k,v in value.items()}
        if isinstance(value,list):return [replace(v) for v in value]
        return value
    return replace(graph)

def validate(graph,info):
    errors=[]
    for ident,node in graph.items():
        kind=node['class_type']
        if kind not in info:errors.append(f'{ident}: missing node {kind}');continue
        schema=info[kind].get('input',{})
        for key,spec in schema.get('required',{}).items():
            if spec[0]=='COMFY_AUTOGROW_V3':
                minimum=spec[1].get('template',{}).get('min',1)
                count=sum(k==key or k.startswith(key+'.') for k in node['inputs'])
                if count<minimum:errors.append(f'{ident}: input {key} requires at least {minimum} entries')
            elif key not in node['inputs']:errors.append(f'{ident}: missing input {key}')
        for key,value in node['inputs'].items():
            if isinstance(value,list) and len(value)==2 and isinstance(value[0],str) and isinstance(value[1],int):
                source=graph.get(value[0])
                if source is None:errors.append(f'{ident}.{key}: missing linked node');continue
                outputs=info.get(source['class_type'],{}).get('output',[])
                if not 0<=value[1]<len(outputs):errors.append(f'{ident}.{key}: invalid output index')
                else:
                    spec={**schema.get('required',{}),**schema.get('optional',{})}.get(key)
                    if spec and isinstance(spec[0],str) and spec[0]!='*' and outputs[value[1]]!='*' and spec[0]!=outputs[value[1]]:
                        errors.append(f'{ident}.{key}: linked type {outputs[value[1]]}, expected {spec[0]}')
                continue
            spec={**schema.get('required',{}),**schema.get('optional',{})}.get(key)
            if spec and isinstance(spec[0],list) and value not in spec[0]:errors.append(f'{ident}.{key}: unavailable selection {value}')
    return errors

def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    a=sub.add_parser('adapt');a.add_argument('--api',required=True);a.add_argument('--slots',required=True);a.add_argument('--save-node',required=True);a.add_argument('--output',type=Path,required=True)
    v=sub.add_parser('validate');v.add_argument('--api',required=True)
    args=p.parse_args();graph=load(args.api)
    if args.command=='adapt':
        graph=adapt(graph,load(args.slots),args.save_node)
        if args.output.exists():raise FileExistsError(args.output)
        args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(graph,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    else:
        with urllib.request.urlopen(URL+'/object_info',timeout=30) as r:info=json.load(r)
        errors=validate(graph,info);print(json.dumps({'errors':errors,'note':'Static check only; no GPU work submitted'},indent=2))
        if errors:raise SystemExit(1)

if __name__=='__main__':main()
