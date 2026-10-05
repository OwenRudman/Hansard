"""Batch Label-stage audit.
usage: python3 run_batch.py <cleaned_json_dir> <pdf_dir> <out_dir>
out_dir/ready/  -> no flags: final files, levels set by the tool's Suggest hierarchy, every block reviewed
out_dir/check/  -> flagged files (flagged blocks left unreviewed) + '<name> - flags.txt'
out_dir/summary.csv
"""
import json, os, re, sys, glob, subprocess, csv, shutil
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pdfparse, auditor

def pick_pdf(d_date, entries, pdf_dir):
    cands = glob.glob(os.path.join(pdf_dir, f'{d_date}*.pdf'))
    if len(cands) <= 1:
        return cands[0] if cands else None
    # several sittings that day: choose the PDF where the most block text is found
    best, score = None, -1
    for c in cands:
        pdfparse.PDF_OVERRIDE = c
        ref, stream = auditor.pdf_reference(d_date)
        n = sum(1 for e in entries[:60] if auditor.norm(e['text'])[:40] and auditor.norm(e['text'])[:40] in stream)
        if n > score: best, score = c, n
    return best

def main(src, pdf_dir, out):
    os.makedirs(f'{out}/ready', exist_ok=True); os.makedirs(f'{out}/check', exist_ok=True); os.makedirs(f'{out}/.work', exist_ok=True)
    rows = []
    for f in sorted(glob.glob(os.path.join(src, '*.json'))):
        data = json.load(open(f)); name = os.path.basename(f)[:-5]
        m = re.search(r'(\d{4}-\d\d-\d\d)', name); d = m.group(1)
        pdf = pick_pdf(d, data['entries'], pdf_dir)
        if not pdf:
            rows.append(dict(file=name, status='NO PDF', flags='', blocks=len(data['entries']))); continue
        pdfparse.PDF_OVERRIDE = pdf
        try:
            A = auditor.Auditor(d, data['entries']); data['entries'] = A.run(); flags = A.flag_report()
        except Exception as ex:
            rows.append(dict(file=name, status=f'ERROR {ex}', flags='', blocks='')); continue
        lab = f'{out}/.work/{name}.json'; json.dump(data, open(lab, 'w'), ensure_ascii=False)
        dest = f"{out}/{'check' if flags else 'ready'}/{name}.json"
        subprocess.run(['node', os.path.join(HERE, '..', 'harness.js'), lab, dest, '--suggest', '--keep-reviewed'], check=True,
                       env=dict(os.environ, NODE_PATH='/opt/node22/lib/node_modules'))
        out_entries = json.load(open(dest))['entries']
        cut = [k + 1 for k, e in enumerate(out_entries) if e['cutout']]
        if cut:
            flags.append(dict(block=cut[0], pdf_page=None, id='', label='', speaker='', text='',
                              reason=f"Suggest hierarchy placed a Quorum/Division cutout (blocks {cut[0]}-{cut[-1]}). Check where it ends."))
            if dest.endswith('.json') and '/ready/' in dest:
                shutil.move(dest, dest.replace('/ready/', '/check/')); dest = dest.replace('/ready/', '/check/')
        if flags:
            with open(f'{out}/check/{name} - flags.txt', 'w') as fh:
                fh.write(f"{name}: {len(flags)} to check. Flagged blocks are left unreviewed, so 'Go to first unreviewed' in the tool steps through them.\n\n")
                for n_, r in enumerate(flags, 1):
                    loc = f"block {r['block']}" + (f", PDF p.{r['pdf_page']}" if r.get('pdf_page') else '')
                    who = f" [{r['label']}{' | ' + r['speaker'] if r['speaker'] else ''}]" if r['label'] else ''
                    fh.write(f"{n_}. {loc}{who}\n   {r['reason']}\n" + (f"   Text: \"{r['text'][:110]}\"\n" if r['text'] else '') + "\n")
        rows.append(dict(file=name, status='check' if flags else 'ready', flags=len(flags), blocks=len(out_entries), pdf=os.path.basename(pdf)))
    with open(f'{out}/summary.csv', 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=['file', 'status', 'flags', 'blocks', 'pdf']); w.writeheader(); w.writerows(rows)
    for r in rows: print(r)

if __name__ == '__main__':
    main(*sys.argv[1:4])
