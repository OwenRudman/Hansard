"""Post-run safety checks added for the 12th Senate run (run after run_batch.py).
Moves sittings out of ready/ when the audit could not actually check them:
  - empty sittings (Mzalendo page has no text)
  - PDFs whose layout pdfparse.py doesn't recognise (speaker paragraphs not indented 120-135pt),
    so the name / new-speaker checks never ran.
usage: python3 postcheck.py <out_dir> <pdf_dir>
"""
import csv, json, os, re, shutil, sys, collections
import pymupdf

def speaker_indent(pdf):
    doc = pymupdf.open(pdf); ind = collections.Counter()
    for pg in list(doc)[1:6]:
        for b in pg.get_text('dict')['blocks']:
            for l in b.get('lines', []):
                sp = [s for s in l['spans'] if s['text'].strip()]
                if sp and 'Bold' in sp[0]['font'] and re.match(r'^[^:]{3,80}:', ''.join(s['text'] for s in l['spans'])):
                    ind[round(l['bbox'][0])] += 1
    return ind.most_common(1)[0][0] if ind else None

def main(out, pdf_dir):
    path = f'{out}/summary.csv'; rows = list(csv.DictReader(open(path)))
    for r in rows:
        reasons = []
        if r['status'] in ('ready', 'check') and str(r['blocks']) == '0':
            reasons.append("Empty sitting: the Mzalendo page has no transcript text, so there is nothing to label. "
                           "Needs a decision (skip, or transcribe from the PDF).")
        elif r['status'] in ('ready', 'check') and r.get('pdf'):
            x = speaker_indent(os.path.join(pdf_dir, r['pdf']))
            if x is None or not 120 <= x <= 135:
                reasons.append(f"PDF layout not recognised by the parser (speaker lines start at x={x}, expected 120-135), "
                               "so the speaker-name and new-speaker checks did not run on this sitting. "
                               "Check speakers and block splits by hand.")
        if not reasons:
            continue
        name = r['file']; src = f"{out}/{r['status']}/{name}.json"; dst = f"{out}/check/{name}.json"
        if r['status'] == 'ready':
            shutil.move(src, dst)
        ff = f'{out}/check/{name} - flags.txt'
        old = open(ff).read() if os.path.exists(ff) else ''
        n_old = int(r['flags'] or 0)
        body = ''.join(f"{n_old + k}. whole sitting\n   {t}\n\n" for k, t in enumerate(reasons, 1))
        if old:
            old = re.sub(r'^(.*?): \d+ to check', lambda m: f"{m.group(1)}: {n_old + len(reasons)} to check", old, count=1)
            open(ff, 'w').write(old + body)
        else:
            open(ff, 'w').write(f"{name}: {len(reasons)} to check.\n\n" + body)
        r['status'] = 'check'; r['flags'] = n_old + len(reasons)
        print('moved/flagged:', name, '|', reasons[0][:60])
    with open(path, 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)

if __name__ == '__main__':
    main(*sys.argv[1:3])


def flag_unleveled_headings(out):
    """Headings Suggest hierarchy left without a level are usually mislabeled front matter or fragments
    (and the processing instructions ask for unassigned levels to be reported). Flag each one and leave it unreviewed."""
    path = f'{out}/summary.csv'; rows = list(csv.DictReader(open(path)))
    for r in rows:
        name = r['file']; src = f"{out}/{r['status']}/{name}.json"
        if not os.path.exists(src):
            continue
        raw = open(src, encoding='utf-8').read(); d = json.loads(raw)
        hits = [(k + 1, e) for k, e in enumerate(d['entries']) if e['label'] == 'heading' and not e['level']]
        if not hits:
            continue
        for _, e in hits:
            e['reviewed'] = False
        dst = f"{out}/check/{name}.json"
        with open(dst, 'w', encoding='utf-8') as fh:
            fh.write(json.dumps(d, indent=2, ensure_ascii=False))
        if src != dst:
            os.remove(src)
        ff = f'{out}/check/{name} - flags.txt'; old = open(ff).read() if os.path.exists(ff) else ''
        n_old = int(r['flags'] or 0)
        body = ''.join(f"{n_old + k}. block {b} [heading]\n   Suggest hierarchy gave this heading no level. "
                       f"Check whether it is really a heading (front matter and fragments should be other/deleted).\n"
                       f"   Text: \"{' '.join(e['text'].split())[:110]}\"\n\n" for k, (b, e) in enumerate(hits, 1))
        if old:
            old = re.sub(r'^(.*?): \d+ to check', lambda m: f"{m.group(1)}: {n_old + len(hits)} to check", old, count=1)
            open(ff, 'w').write(old + body)
        else:
            open(ff, 'w').write(f"{name}: {len(hits)} to check. Flagged blocks are left unreviewed, so 'Go to first unreviewed' in the tool steps through them.\n\n" + body)
        r['status'] = 'check'; r['flags'] = n_old + len(hits)
        print('unleveled headings:', name, len(hits))
    with open(path, 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)


PAGE_MARKER = re.compile(r'^\s*Page \d+ of \w+day,\s*\d{1,2}(st|nd|rd|th)\s*\w+,?\s*\d{4}(\s*,?\s*at\s*\d{1,2}[.:]\d{2}\.?\s*[ap]\.?\s*m\.?)?\.?\s*$', re.I)

def delete_page_markers(out):
    """Page markers the cleaner missed (e.g. 'Page 3 of Tuesday, 3rdAugust, 2021 At 2.30 P.m.' - no space after 3rd).
    Marked deleted exactly as the tool's red X does (label 'deleted', original_label = old label, level cleared,
    speaker kept). Left unreviewed and flagged once per sitting, since speech pieces either side may need combining."""
    path = f'{out}/summary.csv'; rows = list(csv.DictReader(open(path)))
    for r in rows:
        name = r['file']; src = f"{out}/{r['status']}/{name}.json"
        if not os.path.exists(src):
            continue
        d = json.load(open(src, encoding='utf-8')); hits = []
        for k, e in enumerate(d['entries']):
            if e['label'] != 'deleted' and PAGE_MARKER.match(e['text']):
                if not e['original_label']:
                    e['original_label'] = e['label']
                e['label'] = 'deleted'; e['level'] = ''; e['reviewed'] = False; hits.append(k + 1)
        if not hits:
            continue
        dst = f"{out}/check/{name}.json"
        with open(dst, 'w', encoding='utf-8') as fh:
            fh.write(json.dumps(d, indent=2, ensure_ascii=False))
        if src != dst:
            os.remove(src)
        ff = f'{out}/check/{name} - flags.txt'; old = open(ff).read() if os.path.exists(ff) else ''
        n_old = int(r['flags'] or 0)
        body = (f"{n_old + 1}. blocks {', '.join(map(str, hits))}\n   {len(hits)} page markers ('Page N of <date>') the cleaner missed "
                f"were marked deleted. Where the speech blocks just above and below one of them are the same speech, combine them.\n\n")
        if old:
            old = re.sub(r'^(.*?): \d+ to check', lambda m: f"{m.group(1)}: {n_old + 1} to check", old, count=1)
            open(ff, 'w').write(old + body)
        else:
            open(ff, 'w').write(f"{name}: 1 to check. Flagged blocks are left unreviewed, so 'Go to first unreviewed' in the tool steps through them.\n\n" + body)
        r['status'] = 'check'; r['flags'] = n_old + 1
        print('page markers deleted:', name, len(hits))
    with open(path, 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
