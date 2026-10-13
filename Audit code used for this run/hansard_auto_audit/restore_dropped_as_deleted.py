"""Put back blocks that an earlier fix dropped outright, as the editor's X would leave them: label 'deleted',
original_label = the label it had, text and id unchanged, in the same place. Then re-run Suggest hierarchy."""
import json, glob, os, sys, re, csv, subprocess
def run(backup, out, start):
    total = 0
    for f in sorted(glob.glob(backup + '/*/*.json')):
        name = os.path.basename(f)
        if name < start: continue
        cur = glob.glob(f"{out}/*/{glob.escape(name)}")
        if not cur: continue
        src = cur[0]; d = json.load(open(src, encoding='utf-8')); E = d['entries']; ids = {e['id'] for e in E}
        O = json.load(open(f))['entries']
        gone = [(k, e) for k, e in enumerate(O) if e['id'] not in ids and '-inserted-' in e['id']]
        if not gone: continue
        newpos_shift = []
        for k, e in gone:
            pred = O[k - 1]['id']
            at = max((j for j, x in enumerate(E) if x['id'] == pred or x['id'].startswith(pred + '-')), default=None)
            if at is None: print('  could not place', name, e['text'][:50]); continue
            b = dict(e); b['original_label'] = b['original_label'] or b['label']; b['label'] = 'deleted'; b['level'] = ''
            E.insert(at + 1, b); newpos_shift.append(at + 2); total += 1
        for k, x in enumerate(E, 1): x['order'] = k
        tmp = src + '.tmp.json'
        with open(tmp, 'w', encoding='utf-8') as fh: fh.write(json.dumps(d, indent=2, ensure_ascii=False))
        subprocess.run(['node', '/home/user/Hansard/Audit code used for this run/harness.js', tmp, src, '--suggest'], check=True,
                       env=dict(os.environ, NODE_PATH='/opt/node22/lib/node_modules'))
        os.remove(tmp)
        ff = os.path.join(os.path.dirname(src), name[:-5] + ' - flags.txt')
        if os.path.exists(ff):   # block numbers at or after each re-inserted block move down by one
            ins = sorted(newpos_shift)
            def mv(n):
                n = int(n)
                for p in ins:
                    if n >= p: n += 1
                return str(n)
            tx = open(ff).read()
            tx = re.sub(r'^(\d+\. block )(\d+)', lambda m: m.group(1) + mv(m.group(2)), tx, flags=re.M)
            tx = re.sub(r'^(\d+\. blocks )([\d, ]+)', lambda m: m.group(1) + ', '.join(mv(x) for x in m.group(2).split(', ')), tx, flags=re.M)
            open(ff, 'w').write(tx)
        print(name[:19], 'restored as deleted:', len(newpos_shift))
    rows = list(csv.DictReader(open(f'{out}/summary.csv')))
    for r in rows:
        g = glob.glob(f"{out}/*/{glob.escape(r['file'])}.json")
        if g: r['blocks'] = len(json.load(open(g[0]))['entries'])
    with open(f'{out}/summary.csv', 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    print('total restored:', total)
if __name__ == '__main__':
    run(*sys.argv[1:4])
