"""Rules learned from Owen's 40 hand-finished sittings (Oct 2026). Every change is a tool action:
Combine with next (texts joined by a blank line, speaker carried over if the first block has none),
Split block, relabel, or editing the Speaker box. No text is retyped or dropped."""
import json, re, os, sys, uuid, glob, collections
sys.path.insert(0, '/home/user/Hansard/Audit code used for this run/hansard_auto_audit')
import pdfparse
def norm(t): return re.sub(r'[^a-z0-9]', '', (t or '').lower())
TALLY_KW = r'(?:AYES|NOES|ABSTENTIONS?|ABSTENSIONS?|ABSENTIONS?)'
ROLE = re.compile(r'speaker|chair|leader|whip|clerk', re.I)

def combine(E, i, log, why):
    """Tool's Combine with next on E[i-1]: E[i] is joined onto it. A heading/other/scene keeps no speaker."""
    p, c = E[i - 1], E[i]
    if not p['speaker'] and not p['speaker_title'] and (c['speaker'] or c['speaker_title']):
        p['speaker'], p['speaker_title'] = c['speaker'], c['speaker_title']
    p['text'] = '\n\n'.join(x for x in (p['text'], c['text']) if x)
    log.append((why, c['text'][:60])); del E[i]

def r1_names(E, turns, log):
    """Empty Speaker box, a role in Title: put back the name Mzalendo dropped.
    (a) name stuck at the start of the text: '(Hon. Lusaka) Yes, ...' -> Speaker '(Hon. Lusaka)'
    (b) the PDF prints 'Role (Name)' for this turn -> Speaker '(Name)'. Never invented: only a name the source prints."""
    for e in E:
        if e['label'] != 'speech' or e['speaker'] or not ROLE.search(e['speaker_title'] or ''): continue
        m = re.match(r'^\s*(\((?:Hon|Sen|Dr|Prof|Eng|Rev|Mr|Mrs|Ms)\.?[^()]*(?:\([^()]*\)[^()]*)?\))\s*:?\s+(?=[A-Z])', e['text'])
        if m and len(m.group(1)) <= 45 and re.search(r'[A-Za-z]{3,}', m.group(1)[5:]):
            e['speaker'] = m.group(1); e['text'] = e['text'][m.end():]; log.append(('name moved from text to Speaker', m.group(1))); continue
        k = norm(e['text'])[:40]
        if len(k) < 15: continue
        hit = [spk for spk, t in turns if k in t]
        if len(hit) != 1: continue
        mm = re.search(r'(\((?:Hon|Sen|Dr|Prof|Eng|Rev|Mr|Mrs|Ms)\.?[^()]*(?:\([^()]*\)[^()]*)?\))\s*$', hit[0])
        role = norm(re.sub(r'\(.*', '', hit[0]))
        if mm and role and norm(e['speaker_title']).endswith(role[-8:]):
            e['speaker'] = mm.group(1); log.append(('name from PDF into Speaker', mm.group(1)))

def r2_tallies(E, log):
    """Division tallies broken into pieces: ': Nil', 'Nil', ': 0', a bare 'NOES' etc. go back into the block before."""
    i = 1
    while i < len(E):
        c, p = E[i], E[i - 1]
        if c['label'] == 'deleted' or p['label'] == 'deleted': i += 1; continue
        t, pt = c['text'].strip(), p['text'].strip()
        frag = re.fullmatch(r':?\s*(?:Nil|\d{1,3})\.?', t, re.I)
        if frag and re.search(TALLY_KW + r'\s*:?\s*$', pt, re.I):
            combine(E, i, log, 'tally piece joined'); continue
        if re.fullmatch(TALLY_KW + r'\s*:?', t, re.I) and re.search(TALLY_KW, pt, re.I) and c['label'] in ('heading', 'speech', 'other'):
            combine(E, i, log, 'tally keyword joined'); continue
        i += 1

def r4_bill_numbers(E, log):
    """'(SENATE BILLS NO. 11 OF 2017)' on its own goes into the bill-title heading before it."""
    i = 1
    while i < len(E):
        c, p = E[i], E[i - 1]
        if p['label'] == 'heading' and c['label'] != 'deleted' and re.fullmatch(
                r'\(\s*(?:SENATE|NATIONAL\s+ASSEMBLY)\s+BILLS?\s+NO\.?\s*\d+\s+(?:OF|0F)\s+\d{4}\s*\)', c['text'].strip(), re.I):
            combine(E, i, log, 'bill number joined to title'); c = None; continue
        i += 1

def r5_rose(E, log):
    """'The Senate rose at 6.30 p.m.' inside a speech: Split block, selected piece = scene."""
    out = []
    for e in E:
        m = re.search(r'The Senate rose at \d{1,2}[.:]\d{2}\s*[ap]\.?\s*m\.?', e['text']) if e['label'] == 'speech' else None
        if not m or (m.start() == 0 and m.end() >= len(e['text'].rstrip())):
            out.append(e); continue
        before, mid, after = e['text'][:m.start()].strip(), e['text'][m.start():m.end()].strip(), e['text'][m.end():].strip()
        for txt, suf in ((before, 'before'), (mid, 'selected'), (after, 'after')):
            if not txt: continue
            p = dict(e); p['id'] = f"{e['id']}-split-{suf}-{uuid.uuid4()}"; p['text'] = txt
            if suf == 'selected': p['label'] = 'scene'; p['speaker'] = ''; p['speaker_title'] = ''
            out.append(p)
        log.append(('"The Senate rose" split out as scene', mid))
    E[:] = out

def r6_scenes(E, log):
    """Broken scenes: a piece that continues an unclosed '(' scene goes back into it; a speech that is only
    '( Question, that ... )' becomes a scene."""
    i = 1
    while i < len(E):
        c, p = E[i], E[i - 1]
        if p['label'] == 'scene' and c['label'] in ('scene', 'speech', 'heading', 'other') and \
                p['text'].count('(') > p['text'].count(')') and c['text'].count(')') > c['text'].count('(') and len(c['text']) < 300:
            combine(E, i, log, 'scene fragment joined'); continue
        i += 1
    for e in E:
        t = e['text'].strip()
        if e['label'] == 'speech' and re.match(r'^\(\s*Question,?\s+that\b', t) and t.endswith(')') and t.count('(') == t.count(')'):
            e['label'] = 'scene'; e['speaker'] = ''; e['speaker_title'] = ''; log.append(('(Question ...) relabelled scene', t[:50]))

def r7_heading_fragments(E, log):
    """A 'heading' that is really a scrap of the sentence before ('16A.', 'under sub-section') goes back into it."""
    i = 1
    while i < len(E):
        c, p = E[i], E[i - 1]
        t = c['text'].strip()
        if c['label'] == 'heading' and p['label'] == 'speech' and len(t.split()) <= 3 and (
                re.fullmatch(r'\d+[A-Z]?\.', t) or (t[:1].islower())):
            combine(E, i, log, 'heading fragment joined'); continue
        i += 1

def pdf_turns(pdf, date):
    pdfparse.PDF_OVERRIDE = pdf
    return [(it['spk'], norm(it['t'])) for it in pdfparse.items(date) if it['k'] == 'P' and it.get('spk')]

def apply_all(E, turns):
    log = []
    r1_names(E, turns, log); r2_tallies(E, log); r4_bill_numbers(E, log); r7_heading_fragments(E, log)
    return log


def apply_to(out, start, pdf_for, rows):
    """Apply the rules to every sitting from `start` on, renumber its flags list, re-run Suggest hierarchy."""
    import csv, subprocess
    allrows = list(csv.DictReader(open(f'{out}/summary.csv'))); tot = collections.Counter()
    for r in allrows:
        n = r['file']
        if n < start: continue
        f = glob.glob(f"{out}/*/{glob.escape(n)}.json")
        if not f or str(r['blocks']) == '0': continue
        src = f[0]; d = json.load(open(src, encoding='utf-8')); E = d['entries']
        before = [e['id'] for e in E]
        log = apply_all(E, pdf_turns(pdf_for(n, rows), n[:10]))
        if not log: continue
        for w, _ in log: tot[w] += 1
        pos = {x['id']: k for k, x in enumerate(E, 1)}
        newpos = {}; last = 1
        for k, i in enumerate(before, 1):
            if i in pos: last = pos[i]
            newpos[k] = last          # a combined block points at the block it went into
        for k, x in enumerate(E, 1): x['order'] = k
        tmp = src + '.tmp.json'
        with open(tmp, 'w', encoding='utf-8') as fh: fh.write(json.dumps(d, indent=2, ensure_ascii=False))
        subprocess.run(['node', '/home/user/Hansard/Audit code used for this run/harness.js', tmp, src, '--suggest'], check=True,
                       env=dict(os.environ, NODE_PATH='/opt/node22/lib/node_modules'))
        os.remove(tmp)
        ff = os.path.join(os.path.dirname(src), n + ' - flags.txt')
        if os.path.exists(ff):
            tx = open(ff).read()
            tx = re.sub(r'^(\d+\. block )(\d+)', lambda m: m.group(1) + str(newpos.get(int(m.group(2)), m.group(2))), tx, flags=re.M)
            tx = re.sub(r'^(\d+\. blocks )([\d, ]+)', lambda m: m.group(1) + ', '.join(str(newpos.get(int(x), x)) for x in m.group(2).split(', ')), tx, flags=re.M)
            open(ff, 'w').write(tx)
        r['blocks'] = len(E)
    with open(f'{out}/summary.csv', 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=list(allrows[0].keys())); w.writeheader(); w.writerows(allrows)
    return tot
