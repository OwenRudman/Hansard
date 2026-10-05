"""Compare an audited Hansard JSON (mine) against Owen's finished one."""
import json, re, sys, difflib, collections
import Levenshtein

def norm(t): return re.sub(r'[^a-z0-9]', '', (t or '').lower())

def charseq(entries):
    s, lab, blk, starts = [], [], [], set()
    for bi, e in enumerate(entries):
        n = norm(e['text'])
        if not n: continue
        starts.add(len(s))
        for c in n:
            s.append(c); lab.append(e['label']); blk.append(bi)
    return ''.join(s), lab, blk, starts

def score(mine, owen, verbose=False):
    A, la, ba, sa = charseq(mine); B, lb, bb, sb = charseq(owen)
    amap = {}
    for tag, i1, i2, j1, j2 in Levenshtein.opcodes(A, B):
        if tag == 'equal':
            for k in range(i2 - i1): amap[j1 + k] = i1 + k
    covered = len(amap) / max(1, len(B))
    # label agreement (char-weighted) over aligned chars
    same = sum(la[amap[j]] == lb[j] for j in amap)
    conf = collections.Counter((lb[j], la[amap[j]]) for j in amap if la[amap[j]] != lb[j])
    # block boundaries: Owen's block starts that I also start
    bstarts = sorted(sb); hit = sum(1 for j in bstarts if j in amap and amap[j] in sa)
    inv = {v: k for k, v in amap.items()}
    mine_starts_hit = sum(1 for i in sa if i in inv and inv[i] in sb)
    # headings: exact normalized text sets
    hm = [norm(e['text']) for e in mine if e['label'] == 'heading']
    ho = [norm(e['text']) for e in owen if e['label'] == 'heading']
    cm, co = collections.Counter(hm), collections.Counter(ho)
    h_common = sum((cm & co).values())
    # speakers: for each Owen speech block, compare speaker/title of my block at its first char
    sp_tot = sp_same = tt_same = 0; sp_diff = []
    first = {}
    for k, b in enumerate(bb): first.setdefault(b, k)
    for bi, e in enumerate(owen):
        if e['label'] != 'speech' or not norm(e['text']): continue
        j = first.get(bi)
        if j is None or j not in amap: continue
        m = mine[ba[amap[j]]]
        sp_tot += 1
        ok = norm(m['speaker']) == norm(e['speaker']); okt = norm(m['speaker_title']) == norm(e['speaker_title'])
        sp_same += ok; tt_same += okt
        if not (ok and okt): sp_diff.append((e['speaker'], e['speaker_title'], m['speaker'], m['speaker_title'], e['text'][:60]))
    lev_same = lev_tot = 0
    for j in amap:
        if lb[j] == 'heading' and la[amap[j]] == 'heading':
            lev_tot += 1
            lev_same += (mine[ba[amap[j]]].get('level', '') == owen[bb[j]].get('level', ''))
    res = dict(text_aligned=covered, label_agree=same / max(1, len(amap)),
               boundaries_recall=hit / max(1, len(bstarts)), boundaries_precision=mine_starts_hit / max(1, len(sa)),
               headings_owen=len(ho), headings_mine=len(hm), headings_matched=h_common,
               speakers_checked=sp_tot, speaker_agree=sp_same / max(1, sp_tot), title_agree=tt_same / max(1, sp_tot),
               heading_level_agree=lev_same / max(1, lev_tot), label_confusion=dict(conf.most_common(8)))
    if verbose:
        res['headings_missing'] = list((co - cm).elements()); res['headings_extra'] = list((cm - co).elements())
        res['speaker_diffs'] = sp_diff[:40]
    return res

if __name__ == '__main__':
    m = json.load(open(sys.argv[1]))['entries']; o = json.load(open(sys.argv[2]))['entries']
    r = score(m, o, verbose=True)
    for k, v in r.items(): print(f'{k}: {v}')
