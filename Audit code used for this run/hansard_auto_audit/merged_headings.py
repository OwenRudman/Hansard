import json, re, os, sys, csv, glob, collections
sys.path.insert(0, '/home/user/Hansard/Audit code used for this run/hansard_auto_audit')
import pdfparse
def ntok(w): return re.sub(r'[^A-Z0-9]', '', w.upper())
def pdf_for(n, rows):
    if n.startswith('2018-11-25'): return '/home/user/work/pdfs419/2018-10-25 - Hansard Report - Thursday, 25th October, 2018.pdf'
    if n.startswith('2020-01-28-14'): return glob.glob('/home/user/work/pdfs419/2020-01-28*Afternoon*')[0]
    if n.startswith('2021-05-17'): return glob.glob('/home/user/work/pdfs419/2021-05-17*')[0]
    if n.startswith('2018-10-24'): return '/home/user/work/pdfs419/2018-10-24 - Hansard Report - Wednesday, 24th October, 2018.pdf'
    if n.startswith('2018-03-28'): return glob.glob('/home/user/work/pdfs419/2018-03-14*')[0]
    if n.startswith('2018-03-14'): return glob.glob('/home/user/work/pdfs419/2018-03-15*')[0]
    return '/home/user/work/pdfs419/' + rows[n]
def splits_for(text, heads):
    """If a heading block's text is 2+ consecutive PDF headings run together, return the char positions where each starts."""
    toks = [(m.group(0), m.start()) for m in re.finditer(r'\S+', text)]
    T = [ntok(t) for t, _ in toks]
    while T and not T[-1]: T.pop(); toks.pop()
    H = [[ntok(w) for w in h.split() if ntok(w)] for h in heads]
    for s in range(len(H)):
        k = 0; j = s; cuts = []
        while j < len(H) and k < len(T):
            h = H[j]
            seg = [x for x in T[k:k + len(h) + 3] if x]
            # allow Mzalendo to drop/alter one word: match >=85% of heading tokens in order at this point
            n = 0; m = 0; kk = k
            while kk < len(T) and m < len(h):
                if not T[kk]: kk += 1; continue
                if T[kk] == h[m]: n += 1; m += 1; kk += 1
                elif m + 1 < len(h) and T[kk] == h[m + 1]: m += 1
                else: break
            if n < max(2, 0.85 * len(h)) or n == 0: break
            cuts.append(toks[k][1]); k = kk; j += 1
        if len(cuts) >= 2 and k >= len(T):
            return merge_wraps(text, cuts)
    return None
CONN = {'OF','IN','ON','AND','THE','FOR','TO','BY','AT','FROM','WITH','A','AN','OR','INTO','AGAINST','REGARDING','BETWEEN'}
def merge_wraps(text, cuts):
    """Keep a heading the PDF wrapped (often across a page) in one piece."""
    out = [cuts[0]]
    for c in cuts[1:]:
        prev = text[out[-1]:c].split(); cur_end = cuts[cuts.index(c)+1] if cuts.index(c)+1 < len(cuts) else len(text)
        cur = text[c:cur_end].split()
        if not cur: continue
        p_last = ntok(prev[-1]) if prev else ''; c_first = ntok(cur[0])
        wrap = (p_last in CONN or c_first in CONN - {'THE', 'A', 'AN'} or len(cur) <= 2
                or (('BILL' in [ntok(w) for w in cur]) and c_first != 'THE') or cur[0].startswith('(')
                or text[out[-1]:c].count('(') > text[out[-1]:c].count(')'))
        if not wrap: out.append(c)
    return out if len(out) >= 2 else None
import uuid, subprocess
def apply(out):
    rows = {r['file']: r['pdf'] for r in csv.DictReader(open(f'{out}/summary.csv'))}
    allrows = list(csv.DictReader(open(f'{out}/summary.csv'))); total = 0
    for r in allrows:
        n = r['file']; f = glob.glob(f"{out}/*/{glob.escape(n)}.json")
        if not f or str(r['blocks']) == '0': continue
        src = f[0]; d = json.load(open(src, encoding='utf-8')); E = d['entries']
        if not any(e['label'] == 'heading' and len(e['text'].split()) >= 6 for e in E): continue
        pdfparse.PDF_OVERRIDE = pdf_for(n, rows)
        heads = [it['t'] for it in pdfparse.items(n[:10]) if it['k'] == 'H']
        start = next((k + 1 for k, e in enumerate(E) if re.fullmatch(r'\s*PRAYERS?\.?\s*', e['text'], re.I)), 0)
        new, newpos, changed = [], {}, 0
        for k, e in enumerate(E, 1):
            newpos[k] = len(new) + 1
            c = None
            if e['label'] == 'heading' and k > start and not re.search(r'PARLIAMENT OF KENYA|THE HANSARD', e['text']):
                c = splits_for(e['text'], heads)
            if not c:
                new.append(e); continue
            # the tool's Split block, one title at a time: select the next title, split, repeat on what is left
            t = e['text']; bounds = c + [len(t)]; cur = dict(e)
            for i in range(len(c) - 1):
                piece = t[bounds[i]:bounds[i + 1]].strip(); rest = t[bounds[i + 1]:].strip()
                sel = dict(cur); sel['id'] = f"{cur['id']}-split-selected-{uuid.uuid4()}"; sel['text'] = piece
                aft = dict(cur); aft['id'] = f"{cur['id']}-split-after-{uuid.uuid4()}"; aft['text'] = rest
                new.append(sel); cur = aft
            new.append(cur); changed += len(c)
        if not changed: continue
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
        r['blocks'] = len(new); total += changed
        print(n, '| headings now separate:', changed)
    with open(f'{out}/summary.csv', 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=list(allrows[0].keys())); w.writeheader(); w.writerows(allrows)
    print('total', total)

if __name__ == '__main__':
    R = '/home/user/Hansard/12th Senate - audit results'
    rows = {r['file']: r['pdf'] for r in csv.DictReader(open(f'{R}/summary.csv'))}
    tot = 0; files = 0
    for n in sorted(rows):
        f = glob.glob(f"{R}/*/{glob.escape(n)}.json")
        if not f: continue
        E = json.load(open(f[0]))['entries']
        if not any(e['label'] == 'heading' and len(e['text'].split()) >= 6 for e in E): continue
        pdfparse.PDF_OVERRIDE = pdf_for(n, rows)
        heads = [it['t'] for it in pdfparse.items(n[:10]) if it['k'] == 'H']
        hit = 0
        start = next((k + 1 for k, e in enumerate(E) if re.fullmatch(r'\s*PRAYERS?\.?\s*', e['text'], re.I)), 0)
        for k, e in enumerate(E, 1):
            if e['label'] != 'heading' or k <= start or re.search(r'PARLIAMENT OF KENYA|THE HANSARD', e['text']): continue
            c = splits_for(e['text'], heads)
            if c:
                hit += 1; tot += len(c)
                print(n[:19], k, len(c), '|', ' || '.join(e['text'][a:b].strip()[:80] for a, b in zip(c, c[1:] + [len(e['text'])])))
        files += bool(hit)
    print('heading blocks to split into', tot, 'headings, in', files, 'sittings')
