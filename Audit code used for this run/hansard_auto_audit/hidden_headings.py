import json, re, os, sys, csv, glob, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pdfparse
def ntok(w): return re.sub(r'[^A-Z0-9]', '', w.upper())
def is_up(w):
    letters = re.sub(r'[^A-Za-z]', '', w)
    return bool(letters) and letters.isupper()
def find(E, heads):
    """yield (block index, start char, end char, pdf heading) for hidden headings"""
    present = set(ntok(e['text']) for e in E if e['label'] == 'heading' and '-inserted-' not in e['id'])
    used = set(); spans = set()
    start = next((k + 1 for k, e in enumerate(E) if re.fullmatch(r'\s*PRAYERS?\.?\s*', e['text'], re.I)), 0)
    for i, e in enumerate(E):
        if i < start or e['label'] in ('heading', 'deleted'): continue
        toks = [(m.group(0), m.start(), m.end()) for m in re.finditer(r'\S+', e['text'])]
        for h in heads:
            if h['n'] in used: continue
            H = [ntok(w) for w in h['t'].split() if ntok(w)]
            if len(H) < 3 or ntok(h['t']) in present: continue
            best = None
            for a in range(len(toks)):
                if not is_up(toks[a][0]) or ntok(toks[a][0]) not in H: continue
                for s in [k for k, x in enumerate(H) if x == ntok(toks[a][0])]:
                    b, k = a, s
                    while b < len(toks) and k < len(H) and is_up(toks[b][0]) and ntok(toks[b][0]) == H[k]:
                        b += 1; k += 1
                    n = b - a
                    if n >= 3 and n >= 0.6 * len(H) and (best is None or n > best[2]):
                        best = (a, b, n)
            if best:
                a, b, n = best
                if sum(c.isupper() for c in h['t']) < 0.75 * max(1, sum(c.isalpha() for c in h['t'])): continue
                def hl(w):  # heading-like token: all-caps letters, or a number/symbol
                    letters = re.sub(r'[^A-Za-z]', '', w)
                    return (letters.isupper() if letters else True) and ntok(w) != 'THAT'
                while a > 0 and hl(toks[a-1][0]) and not re.search(r'[.:;!?]["”’)]*$', toks[a-1][0]) and ntok(toks[a-1][0]) != 'THAT': a -= 1
                while b < len(toks) and hl(toks[b][0]) and ntok(toks[b][0]) != 'THAT' and not re.search(r'[.:;!?]["”’)]*$', toks[b-1][0]): b += 1
                while b > a and not re.sub(r'[^A-Za-z0-9]', '', toks[b-1][0]): b -= 1   # no trailing bare punctuation
                while a < b and re.fullmatch(r'[A-Z]', ntok(toks[a][0]) or '') and len(H) and ntok(toks[a][0]) not in H: a += 1
                while b > a + 1 and ntok(toks[b-1][0]) in ('I', 'A') and ntok(toks[b-1][0]) != H[-1]: b -= 1
                cover = sum(1 for t in toks[a:b] if ntok(t[0]) in H) / len(H)
                if (i, a) in spans: continue
                if b == len(toks) and cover < 0.9:
                    nxt = next((x for x in E[i+1:] if x['label'] != 'deleted'), None)
                    rest = H[H.index(ntok(toks[b-1][0])) + 1:] if ntok(toks[b-1][0]) in H else []
                    first = re.match(r'\s*(\S+)', nxt['text']) if nxt else None
                    if rest and first and ntok(first.group(1)) == rest[0]:
                        spans.add((i, a)); used.add(h['n']); yield i, toks[a][1], toks[b-1][2], h, 'PARTIAL'; continue
                spans.add((i, a))
                st, en = toks[a][1], toks[b - 1][2]
                if st == 0 and en >= len(e['text'].rstrip()) - 1: continue  # whole block: a relabel, not a split
                ins = [j for j, x in enumerate(E) if x['label'] == 'heading' and '-inserted-' in x['id'] and ntok(x['text']) == h['n'] and abs(j - i) <= 8]
                if any(ntok(x['text']) == h['n'] for x in E if x['label'] == 'heading' and '-inserted-' in x['id']) and not ins: continue
                used.add(h['n']); yield i, st, en, h, (ins[0] if ins else None)


# ---- apply (added after Owen's review: AUDIT ON DISTRIBUTION OF TEACHERS... left inside a speech) ----
import uuid, subprocess
HERE = os.path.dirname(os.path.abspath(__file__))

def _clone(src, text, suffix, label):
    p = dict(src); p['id'] = f"{src['id']}-split-{suffix}-{uuid.uuid4()}"; p['text'] = text; p['label'] = label
    p['level'] = ''
    if label != 'speech':   # the tool clears the speaker tag on anything that isn't a speech
        p['speaker'] = ''; p['speaker_title'] = ''
    return p

def apply(out, pdf_for):
    """pdf_for(sitting name) -> PDF path. Splits PDF headings Mzalendo left inside blocks (the tool's Split block,
    selected piece relabelled heading), removes the misplaced copy the audit had inserted, flags headings broken
    across two blocks, then re-runs the tool's Suggest hierarchy on changed sittings."""
    path = f'{out}/summary.csv'; rows = list(csv.DictReader(open(path))); done = 0
    for r in rows:
        name = r['file']; f = glob.glob(f"{out}/*/{glob.escape(name)}.json")
        if not f or str(r['blocks']) == '0': continue
        src = f[0]; pdfparse.PDF_OVERRIDE = pdf_for(name)
        heads = [dict(t=it['t'], n=ntok(it['t'])) for it in pdfparse.items(name[:10]) if it['k'] == 'H']
        d = json.load(open(src, encoding='utf-8')); E = d['entries']
        cands = list(find(E, heads))
        if not cands: continue
        splits = collections.defaultdict(list); remove = set(); partial = []
        for i, st, en, h, ins in cands:
            if ins == 'PARTIAL': partial.append((i, E[i]['text'][st:en], h['t'])); continue
            splits[i].append((st, en))
            if ins is not None: remove.add(ins)
        new, newpos, newhead = [], {}, []
        for i, e in enumerate(E):
            if i in remove:
                newpos[i + 1] = None; continue
            newpos[i + 1] = len(new) + 1
            if i not in splits:
                new.append(e); continue
            t = e['text']; cur = 0; pieces = []
            for st, en in sorted(splits[i]):
                before = t[cur:st].strip(); mid = t[st:en].strip()
                if before: pieces.append(('before', before, e['label']))
                pieces.append(('selected', mid, 'heading')); cur = en
            after = t[cur:].strip()
            if after: pieces.append(('after', after, e['label']))
            for suf, txt, lab in pieces:
                p = _clone(e, txt, suf, lab); new.append(p)
                if lab == 'heading': newhead.append(p['id'])
        for k in list(newpos):
            if newpos[k] is None:   # a removed inserted heading: point at the heading that replaced it
                newpos[k] = next((j + 1 for j, x in enumerate(new) if x['id'] in newhead and j + 1 >= (newpos.get(k - 1) or 0) - 8), None)
        for k, e in enumerate(new, 1): e['order'] = k
        d['entries'] = new
        # re-run the tool's own Suggest hierarchy (levels and cutouts) exactly as the first run did
        tmp = src + '.tmp.json'
        with open(tmp, 'w', encoding='utf-8') as fh: fh.write(json.dumps(d, indent=2, ensure_ascii=False))
        subprocess.run(['node', os.path.join(HERE, '..', 'harness.js'), tmp, src, '--suggest'], check=True,
                       env=dict(os.environ, NODE_PATH='/opt/node22/lib/node_modules'))
        os.remove(tmp)
        d = json.load(open(src, encoding='utf-8')); E2 = d['entries']
        flags = []
        for i, txt, ht in partial:
            j = newpos[i + 1]; E2[j - 1]['reviewed'] = False
            flags.append(f"block {j} [{E2[j-1]['label']}]\n   The PDF heading '{ht}' is split across this block and the next one "
                         f"(this block has '{' '.join(txt.split())}'). Split it out and combine the two halves into one heading.")
        for j, x in enumerate(E2, 1):
            if x['id'] in newhead and not x['level']:
                x['reviewed'] = False
                flags.append(f"block {j} [heading]\n   Split this heading out of a block (the PDF shows it here), but Suggest hierarchy gave it no level. Check it.")
        with open(src, 'w', encoding='utf-8') as fh: fh.write(json.dumps(d, indent=2, ensure_ascii=False))
        ff = os.path.join(os.path.dirname(src), f'{name} - flags.txt')
        if os.path.exists(ff):
            t = open(ff).read()
            t = re.sub(r'^(\d+\. block )(\d+)', lambda m: m.group(1) + str(newpos.get(int(m.group(2))) or m.group(2)), t, flags=re.M)
            t = re.sub(r'^(\d+\. blocks )([\d, ]+)', lambda m: m.group(1) + ', '.join(str(newpos.get(int(x)) or x) for x in m.group(2).split(', ')), t, flags=re.M)
            open(ff, 'w').write(t)
        if flags:
            n_old = int(r['flags'] or 0)
            dst_dir = [x for x in os.listdir(out) if x.startswith('Needs human check')][0]
            if os.path.dirname(src) != f'{out}/{dst_dir}':
                os.replace(src, f'{out}/{dst_dir}/{name}.json'); src = f'{out}/{dst_dir}/{name}.json'
            ff = f'{out}/{dst_dir}/{name} - flags.txt'
            old = open(ff).read() if os.path.exists(ff) else f"{name}: 0 to check. Flagged blocks are left unreviewed, so 'Go to first unreviewed' in the tool steps through them.\n\n"
            old = re.sub(r'^(.*?): \d+ to check', lambda m: f"{m.group(1)}: {n_old + len(flags)} to check", old, count=1)
            open(ff, 'w').write(old + ''.join(f"{n_old + k}. {x}\n\n" for k, x in enumerate(flags, 1)))
            r['status'] = 'needs human check'; r['flags'] = n_old + len(flags)
        r['blocks'] = len(E2); done += 1
        print(name, '| split out:', sum(len(v) for v in splits.values()), '| misplaced inserted removed:', len(remove), '| flagged:', len(flags))
    with open(path, 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    print('sittings changed:', done)
