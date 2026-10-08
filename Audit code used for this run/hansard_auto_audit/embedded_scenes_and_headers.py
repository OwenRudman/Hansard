import json, re, os, sys, csv, glob, collections, uuid, subprocess
sys.path.insert(0, '/home/user/Hansard/Audit code used for this run/hansard_auto_audit')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/../mh')
import pdfparse
from merged import pdf_for
def key(t): return re.sub(r'\s+', '', t)
def pat(t):
    cs = [c for c in t if not c.isspace()]
    return r'\s*'.join(re.escape(c) for c in cs)
def find(E, scenes):
    """yield (block index, start, end) for PDF scenes embedded inside speech blocks (spacing ignored)"""
    have = collections.Counter(key(e['text']) for e in E if e['label'] == 'scene')
    budget = collections.Counter(key(s) for s in scenes)
    for k in list(budget): budget[k] -= have.get(k, 0)
    out = []
    uniq = sorted(set(scenes), key=len, reverse=True)
    for i, e in enumerate(E):
        if e['label'] != 'speech': continue
        spans = []
        for s in uniq:
            ks = key(s)
            if budget[ks] <= 0 or len(re.sub(r'[^A-Za-z]', '', s)) < 6: continue
            for m in re.finditer(pat(s), e['text']):
                if budget[ks] <= 0: break
                if any(not (m.end() <= a or m.start() >= b) for a, b in spans): continue
                if m.start() == 0 and m.end() >= len(e['text'].rstrip()): continue   # whole block: a relabel, leave
                spans.append((m.start(), m.end())); budget[ks] -= 1
        for a, b in sorted(spans): out.append((i, a, b))
    return out
def scenes_of(n, rows):
    pdfparse.PDF_OVERRIDE = pdf_for(n, rows)
    return [it['t'] for it in pdfparse.items(n[:10]) if it['k'] == 'S' and it['t'].startswith(('(', '[')) and it['t'].rstrip().endswith((')', ']'))]
if __name__ == '__main__':
    R = '/home/user/Hansard/12th Senate - audit results'
    rows = {r['file']: r['pdf'] for r in csv.DictReader(open(f'{R}/summary.csv'))}
    tot = 0; files = 0; ex = collections.Counter()
    for n in sorted(rows):
        f = glob.glob(f"{R}/*/{glob.escape(n)}.json")
        if not f: continue
        E = json.load(open(f[0]))['entries']
        if not E: continue
        hits = find(E, scenes_of(n, rows))
        if hits:
            files += 1; tot += len(hits)
            for i, a, b in hits: ex[' '.join(E[i]['text'][a:b].split())[:60]] += 1
            if n.startswith('2018-02-20'):
                for i, a, b in hits: print('  2018-02-20 block', i + 1, repr(E[i]['text'][a:b]))
    print('scenes to split out:', tot, 'in', files, 'sittings'); print(ex.most_common(25))

M = r'(?:January|February|March|April|May|June|July|August|September|October|November|December)'
HEADER = re.compile(M + r'\s+\d{1,2}\s*,\s*\d{4}\s*(?:SENATE|PARLIAMENTARY)\s*DEBATES\s*\d{1,5}\b|(?:SENATE|PARLIAMENTARY)\s*DEBATES\s*\d{1,5}\s*' + M + r'\s+\d{1,2}\s*,\s*\d{4}', re.I)
def is_caps(s):
    L = re.sub(r'[^A-Za-z]', '', s); return bool(L) and sum(c.isupper() for c in L) > 0.8 * len(L)
def apply(out):
    rows = {r['file']: r['pdf'] for r in csv.DictReader(open(f'{out}/summary.csv'))}
    allrows = list(csv.DictReader(open(f'{out}/summary.csv'))); tot_s = tot_h = 0
    for r in allrows:
        n = r['file']; f = glob.glob(f"{out}/*/{glob.escape(n)}.json")
        if not f or str(r['blocks']) == '0': continue
        src = f[0]; d = json.load(open(src, encoding='utf-8')); E = d['entries']
        cuts = collections.defaultdict(list)
        for i, a, b in find(E, [s for s in scenes_of(n, rows) if not is_caps(s)]):
            cuts[i].append((a, b, 'scene'))
        for i, e in enumerate(E):
            if e['label'] == 'deleted': continue
            for m in HEADER.finditer(e['text']):
                if not any(not (m.end() <= a or m.start() >= b) for a, b, _ in cuts[i]): cuts[i].append((m.start(), m.end(), 'deleted'))
        cuts = {k: v for k, v in cuts.items() if v}
        if not cuts: continue
        new, newpos = [], {}
        for i, e in enumerate(E):
            newpos[i + 1] = len(new) + 1
            if i not in cuts: new.append(e); continue
            # the tool's Split block, one selection at a time, working along the block
            t = e['text']; cur = e; base = 0
            for a, b, lab in sorted(cuts[i]):
                before = t[base:a].strip(); mid = t[a:b].strip(); base = b
                rest = t[b:].strip()
                if before:
                    p = dict(cur); p['id'] = f"{cur['id']}-split-before-{uuid.uuid4()}"; p['text'] = before; new.append(p)
                sel = dict(cur); sel['id'] = f"{cur['id']}-split-selected-{uuid.uuid4()}"; sel['text'] = mid; sel['level'] = ''
                if lab == 'scene':
                    sel['label'] = 'scene'; sel['speaker'] = ''; sel['speaker_title'] = ''; tot_s += 1
                else:   # the red X: deleted, remembers it was a speech, speaker kept
                    sel['original_label'] = sel['original_label'] or cur['label']; sel['label'] = 'deleted'; tot_h += 1
                new.append(sel)
                aft = dict(cur); aft['id'] = f"{cur['id']}-split-after-{uuid.uuid4()}"; aft['text'] = rest; cur = aft
            if cur['text']: new.append(cur)
        for k, e in enumerate(new, 1): e['order'] = k
        d['entries'] = new; tmp = src + '.tmp.json'
        with open(tmp, 'w', encoding='utf-8') as fh: fh.write(json.dumps(d, indent=2, ensure_ascii=False))
        subprocess.run(['node', '/home/user/Hansard/Audit code used for this run/harness.js', tmp, src, '--suggest'], check=True,
                       env=dict(os.environ, NODE_PATH='/opt/node22/lib/node_modules'))
        os.remove(tmp)
        ff = os.path.join(os.path.dirname(src), f'{n} - flags.txt')
        if os.path.exists(ff):
            tx = open(ff).read()
            tx = re.sub(r'^(\d+\. block )(\d+)', lambda m: m.group(1) + str(newpos.get(int(m.group(2)), m.group(2))), tx, flags=re.M)
            tx = re.sub(r'^(\d+\. blocks )([\d, ]+)', lambda m: m.group(1) + ', '.join(str(newpos.get(int(x), x)) for x in m.group(2).split(', ')), tx, flags=re.M)
            open(ff, 'w').write(tx)
        r['blocks'] = len(new)
        print(n, '| blocks changed:', len(cuts))
    with open(f'{out}/summary.csv', 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=list(allrows[0].keys())); w.writeheader(); w.writerows(allrows)
    print('scenes split out:', tot_s, '| page headers deleted:', tot_h)
