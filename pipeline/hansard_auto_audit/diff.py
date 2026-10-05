import json,sys
def s(v,n=150):
    v=str(v).replace('\n','⏎'); return v if len(v)<=n else v[:n-50]+' … '+v[-45:]
def show(revp,donep,levels=False):
    a=json.load(open(revp))['entries']; b=json.load(open(donep))['entries']
    ia={e['id']:e for e in a}; ib={e['id'] for e in b}
    for x in a:
        if x['id'] not in ib: print(f"  REMOVED {x['id']} [{x['label']}] {s(x['speaker']+' '+x['speaker_title'])} :: {s(x['text'])}")
    for y in b:
        x=ia.get(y['id'])
        if x is None:
            print(f"  NEW {y['id'][:40]} [{y['label']}{' L'+y.get('level','') if levels else ''}] spk={s(y['speaker'],60)!r} ttl={s(y['speaker_title'],60)!r} :: {s(y['text'])}")
            continue
        ch=[k for k in ('label','speaker','speaker_title','text') if x.get(k)!=y.get(k)]
        if ch: print(f"  CHG {y['id']} "+' | '.join(f"{k}: {s(x.get(k),90)!r} -> {s(y.get(k),90)!r}" for k in ch))
if __name__=='__main__': show(sys.argv[1],sys.argv[2])
