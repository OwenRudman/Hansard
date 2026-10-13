"""Undo scene splits of numbered list items: '(a) ...', '(ii) ...', '(3) ...' inside a speech were split out as
scenes. Put the speech back together with the tool's Combine with next (texts joined with a blank line; the first
block keeps its id and speaker), then re-run the tool's Suggest hierarchy."""
import json, re, os, sys, csv, glob, subprocess
EN = re.compile(r'^\s*\(\s*(?:[a-z]{1,2}|[ivxl]{1,5}|\d{1,3})\s*\)\s*\S')
def base(i): return i.split('-split-')[0]
def fix(E):
    new, newpos, joins = [], {}, 0
    chain = None   # base id of the speech currently being put back together
    for k, e in enumerate(E, 1):
        last = new[-1] if new else None
        is_item = e['label'] == 'scene' and '-split-' in e['id'] and EN.match(e['text'])
        if is_item and last is not None and last['label'] == 'speech' and base(last['id']) == base(e['id']):
            last['text'] = last['text'] + '\n\n' + e['text']; last['reviewed'] = last['reviewed'] and e['reviewed']
            newpos[k] = len(new); chain = base(e['id']); joins += 1; continue
        if chain and e['label'] == 'speech' and '-split-' in e['id'] and base(e['id']) == chain and last is not None \
                and last['label'] == 'speech' and base(last['id']) == chain:
            last['text'] = last['text'] + '\n\n' + e['text']; last['reviewed'] = last['reviewed'] and e['reviewed']
            newpos[k] = len(new); continue
        chain = None
        new.append(e); newpos[k] = len(new)
    return new, newpos, joins
def apply(out, start='0000'):
    rows = list(csv.DictReader(open(f'{out}/summary.csv'))); total = 0
    for r in rows:
        if r['file'] < start: continue
        f = glob.glob(f"{out}/*/{glob.escape(r['file'])}.json")
        if not f: continue
        src = f[0]; d = json.load(open(src, encoding='utf-8'))
        new, newpos, joins = fix(d['entries'])
        if not joins: continue
        for k, e in enumerate(new, 1): e['order'] = k
        d['entries'] = new; tmp = src + '.tmp.json'
        with open(tmp, 'w', encoding='utf-8') as fh: fh.write(json.dumps(d, indent=2, ensure_ascii=False))
        subprocess.run(['node', '/home/user/Hansard/Audit code used for this run/harness.js', tmp, src, '--suggest'], check=True,
                       env=dict(os.environ, NODE_PATH='/opt/node22/lib/node_modules'))
        os.remove(tmp)
        ff = os.path.join(os.path.dirname(src), f"{r['file']} - flags.txt")
        if os.path.exists(ff):
            tx = open(ff).read()
            tx = re.sub(r'^(\d+\. block )(\d+)', lambda m: m.group(1) + str(newpos.get(int(m.group(2)), m.group(2))), tx, flags=re.M)
            tx = re.sub(r'^(\d+\. blocks )([\d, ]+)', lambda m: m.group(1) + ', '.join(str(newpos.get(int(x), x)) for x in m.group(2).split(', ')), tx, flags=re.M)
            open(ff, 'w').write(tx)
        r['blocks'] = len(new); total += joins
    with open(f'{out}/summary.csv', 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    print('numbered items put back into their speeches:', total)
if __name__ == '__main__':
    apply(sys.argv[1], sys.argv[2])
