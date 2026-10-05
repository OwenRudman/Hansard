"""Label-stage auditor for cleaned Mzalendo Hansard JSON, using the PDF as reference.
Applies Owen's conventions learned from his finished files. Every operation mirrors a
Hansard-tool action (relabel, split, combine-with-next, insert block, mark deleted)."""
import json, re, uuid, sys, copy
import pdfparse

def norm(t):
    return re.sub(r'[^a-z0-9]', '', (t or '').lower())

DIV_RE = re.compile(r'^\s*(AYES|NOES|ABSTENTIONS?)\b', re.I)

def upper_ratio(t):
    letters = [c for c in t if c.isalpha()]
    return sum(c.isupper() for c in letters) / max(1, len(letters))

def pdf_reference(d):
    """PDF items with normalized text and offsets into one stream."""
    its = pdfparse.items(d)
    stream, out = '', []
    for it in its:
        t = it['t']
        kind = it['k']
        if kind == 'H':
            # filter: real headings are caps-dominant or short italic lines; motion text is not
            short_ital = it['ital'] and len(t.split()) <= 8
            if not (upper_ratio(t) > 0.75 or short_ital):
                kind = 'P'
            if re.match(r'^(The House met|The Senate rose|The Senate adjourned)', t):
                kind = 'X'
            if t.startswith(('(', '[')):
                kind = 'S'
            if DIV_RE.match(t) or re.match(r'^[\d\s:.,-]*$', t) or re.match(r'^(Nil\.?|NIL)$', t):
                kind = 'P'
            if re.match(r'^(PARLIAMENT OF KENYA|THE SENATE|THE HANSARD|THE NATIONAL ASSEMBLY)$', t.strip()) or re.match(r'^(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),', t.strip()):
                kind = 'X'
        n = norm((it.get('spk', '') + ' ') if False else t)
        out.append(dict(k=kind, t=t, spk=it.get('spk', ''), ital=it.get('ital'), bold=it.get('bold'), p=it['p'],
                        start=len(stream), end=len(stream) + len(n), n=n))
        stream += n
    return out, stream

def new_id(base, kind):
    return f"{base}-{kind}-{uuid.uuid4()}"

def blank(id_, label, text, speaker='', title=''):
    return dict(order=0, id=id_, label=label, level='', cutout=False, original_label='',
                speaker=speaker, speaker_title=title, reviewed=True, text=text)

class Auditor:
    def __init__(self, d, entries):
        self.d = d
        self.E = copy.deepcopy(entries)
        self.ref, self.stream = pdf_reference(d)
        self.log = []
        self.flags = []   # (entry dict, reason)

    # ---------- tool actions ----------
    def tool_split(self, src, before, mid, after, mid_label, after_label=None, after_spk=None):
        """Mirror the tool's split: every piece is a copy of the source with a new
        <id>-split-<before|selected|after>-<uuid> id, then the selected piece is relabelled."""
        out = []
        for txt, suf in ((before, 'before'), (mid, 'selected'), (after, 'after')):
            if not txt:
                continue
            p = dict(src); p['id'] = f"{src['id']}-split-{suf}-{uuid.uuid4()}"; p['text'] = txt
            p['level'] = ''; p['cutout'] = False
            if suf == 'selected':
                p['label'] = mid_label
            if suf == 'after' and after_label:
                p['label'] = after_label
            if suf == 'after' and after_spk is not None:
                p['speaker'], p['speaker_title'] = after_spk
            if p['label'] not in ('speech',):
                p['speaker'] = ''; p['speaker_title'] = ''
            out.append(p)
        return out

    def tool_insert_after(self, i, label, text):
        """Mirror the tool's insert-block button: new block right after E[i], id <E[i].id>-inserted-<uuid>."""
        src = self.E[i]
        base = src['id'].split('-inserted-')[0]
        b = blank(f"{base}-inserted-{uuid.uuid4()}", label, text)
        self.E.insert(i + 1, b)
        return b

    def flag(self, e, reason):
        self.flags.append((e, reason))

    # ---------- locating text in the PDF stream ----------
    def locate(self, text, after=0, tail=False):
        n = norm(text)
        if not n:
            return None
        for L in (60, 40, 25, 15):
            key = n[-L:] if tail else n[:L]
            if len(key) < min(L, len(n)):
                key = n
            i = self.stream.find(key, after)
            if i < 0:
                i = self.stream.find(key, max(0, after - 3000))
            if i >= 0:
                return i + (len(key) if tail else 0)
        return None

    def item_at(self, pos):
        if pos is None:
            return None
        for k, it in enumerate(self.ref):
            if it['start'] <= pos < it['end'] or (it['start'] == pos == it['end']):
                return k
        return None

    # ---------- passes ----------
    def front_matter(self):
        E = self.E
        for i, e in enumerate(E[:4]):
            m = re.match(r'^(PARLIAMENT OF KENYA\s+THE SENATE)\s+(THE HANSARD.*)$', e['text'].strip(), re.S)
            if m and e['label'] == 'other':
                pieces = self.tool_split(e, m.group(1), m.group(2), '', 'deleted')
                pieces[1]['original_label'] = 'other'
                E[i:i + 1] = pieces
                self.log.append(('front-matter split', m.group(1)))
                break
        for e in E[:8]:
            if e['label'] != 'heading' and norm(e['text']) in ('prayer', 'prayers'):
                e['label'] = 'heading'; self.log.append(('PRAYER->heading', e['text']))

    def heading_texts(self):
        return [it for it in self.ref if it['k'] == 'H']

    CAPS_RUN = re.compile(r"^((?:[A-Z][A-Z'’.,/&-]*\s+){0,8}[A-Z][A-Z'’.,/&-]{2,})(?=\s+[A-Z]?[a-z(]|\s*$)")

    def pdf_turn(self, e, after=0):
        """PDF item where this block's text starts, and whether a bold speaker name opens it there."""
        pos = self.locate(e['text'], after=after)
        k = self.item_at(pos)
        if k is None:
            return pos, None, ''
        it = self.ref[k]
        return pos, k, (it['spk'] if it['spk'] and it['start'] >= pos - 3 else '')

    def headings_before_item(self, k):
        """PDF headings between the previous paragraph and item k (what the PDF shows at that point)."""
        hs = []
        j = k - 1
        while j >= 0 and self.ref[j]['k'] in ('H', 'S', 'X'):
            if self.ref[j]['k'] == 'H':
                hs.insert(0, self.ref[j])
            j -= 1
        return hs

    def fix_speaker_fields(self):
        """Headings that Mzalendo glued into the Speaker/Title boxes ('STATEMENTS The Deputy Speaker',
        '(PAPERS LAID The Senate Majority Leader)'): look up the heading the PDF shows right before that
        speaker's turn, make sure it exists as a heading block there (insert it if not), then strip the
        heading text out of the box."""
        i = 0
        while i < len(self.E):
            e = self.E[i]
            if e['label'] != 'speech':
                i += 1; continue
            if re.match(r'^\(?\s*(AYES|NOES|ABSTENTIONS?|ABSENTIONS?)\s*:?\s*\)?$', (e['speaker'] or e['speaker_title']).strip(), re.I):
                e['label'] = 'other'; e['speaker'] = ''; e['speaker_title'] = ''
                self.log.append(('division word in speaker box -> other', e['text'][:30])); i += 1; continue
            junk = []
            for fld in ('speaker', 'speaker_title'):
                v = e[fld]
                paren = v.strip().startswith('(') and v.strip().endswith(')')
                core = v.strip()[1:-1].strip() if paren else v.strip()
                m = self.CAPS_RUN.match(core)
                if m and len(re.sub(r'[^A-Z]', '', m.group(1))) >= 4 and not re.match(r'^(SEN|HON|DR|PROF|MR|MRS|MS|ENG|REV|AMB)\.?$', m.group(1)):
                    rest = core[m.end():].strip()
                    junk.append(m.group(1).strip())
                    e[fld] = (f'({rest})' if paren and rest else rest)
            if not junk:
                i += 1; continue
            # what heading does the PDF show at this point?
            _, k, _ = self.pdf_turn(e)
            pdf_heads = self.headings_before_item(k) if k is not None else []
            # headings already sitting right above this block
            j = i - 1; above = []
            while j >= 0 and self.E[j]['label'] in ('heading', 'scene'):
                if self.E[j]['label'] == 'heading':
                    above.append(norm(self.E[j]['text']))
                j -= 1
            inserted = 0
            if pdf_heads:
                for h in pdf_heads:
                    if h['n'] in above or any(h['n'] in x for x in above):
                        continue
                    self.tool_insert_after(i - 1 + inserted, 'heading', h['t']); inserted += 1
                    self.log.append(('heading from PDF inserted (was in speaker box)', h['t']))
                matched = any(norm(jk) in h['n'] or h['n'] in norm(jk) for jk in junk for h in pdf_heads)
                if not matched:
                    self.flag(e, f"Speaker/Title box had '{' / '.join(junk)}', but the PDF heading here is '{' / '.join(h['t'] for h in pdf_heads)}'. Removed it from the box; check the heading.")
            else:
                for jk in junk:
                    if norm(jk) in above:
                        continue
                    b = self.tool_insert_after(i - 1 + inserted, 'heading', jk); inserted += 1
                    self.flag(b, f"Removed '{jk}' from the Speaker/Title box and made it a heading, but couldn't find that heading in the PDF at this point. Check it.")
            self.log.append(('cleaned speaker box', ' / '.join(junk)))
            i += 1 + inserted

    def ordered_positions(self):
        """Locate every block in reading order, never searching backwards past the previous block,
        so stock phrases ('On a point of order, Mr. Speaker, Sir') land on the right occurrence."""
        pos, cur = [], 0
        for e in self.E:
            n = norm(e['text']); p = None
            if n:
                for L in (80, 60, 40, 25, 15):
                    key = n[:L] if len(n) >= L else n
                    i = self.stream.find(key, cur)
                    if i >= 0 and i - cur < 20000:
                        p = i; break
            pos.append(p)
            if p is not None:
                cur = p + max(1, min(len(n), 40) - 1)
        return pos

    def turn_at(self, p):
        k = self.item_at(p)
        if k is None:
            return None, ''
        it = self.ref[k]
        return k, (it['spk'] if it['spk'] and it['start'] >= p - 3 else '')

    # ---------- checks that only flag ----------
    STOP = {'sen', 'hon', 'the', 'dr', 'prof', 'eng', 'rev', 'amb', 'mr', 'mrs', 'ms', 'madam', 'speaker', 'deputy', 'temporary',
            'majority', 'minority', 'leader', 'senate', 'chairperson', 'chairman', 'chair', 'whip', 'of', 'and', 'cabinet', 'secretary',
            'member', 'for', 'jnr', 'snr', 'clerk', 'house', 'national', 'assembly', 'county', 'mp', 'arch', 'gen', 'lt', 'col', 'capt', 'maj'}

    @staticmethod
    def _tok(s):
        s = (s or '').replace('’', "'").lower()
        s = re.sub(r"[^a-z' ]", ' ', s).replace("'", '')
        return [w for w in s.split() if w]

    def check_names(self):
        """Name check: the name/role the PDF prints for this turn must be consistent with the block's
        Speaker/Title boxes. Mzalendo sometimes swaps in the wrong person's full name."""
        import Levenshtein
        P = self.ordered_positions()
        for e, pos in zip(self.E, P):
            if e['label'] != 'speech' or pos is None:
                continue
            k, spk = self.turn_at(pos)
            if not spk:
                continue
            pdf_names = [w for w in self._tok(spk) if w not in self.STOP and len(w) >= 3]
            mine = set(self._tok(e['speaker'] + ' ' + e['speaker_title']))
            if pdf_names:
                def close(w, m):
                    return w == m or (len(w) >= 5 and len(m) >= 5 and (w in m or m in w or Levenshtein.distance(w, m) <= 2))
                if not any(close(w, m) for w in pdf_names for m in mine):
                    self.flag(e, f"Name check: PDF says '{spk}', block says '{e['speaker']} {e['speaker_title']}'.")
            else:
                roles = [w for w in self._tok(spk) if w in ('speaker', 'deputy', 'temporary', 'chairperson', 'chairman')]
                if roles and not any(r in mine for r in roles) and not e['speaker_title'] and not e['speaker']:
                    self.flag(e, f"Name check: PDF says '{spk}', block has no speaker.")

    def check_turns(self):
        """Every new speaker turn in the PDF should start a block. A turn that starts in the middle of a
        block means two people's words are in one block."""
        import Levenshtein
        starts = self.ordered_positions()
        located = [(p, e) for p, e in zip(starts, self.E) if p is not None]
        spans = []
        for n_, (p, e) in enumerate(located):
            nxt = located[n_ + 1][0] if n_ + 1 < len(located) else len(self.stream)
            spans.append((p, min(nxt, p + len(norm(e['text']))), e))
        def same_person(pdf_spk, e):
            a_ = [w for w in self._tok(pdf_spk) if w not in self.STOP and len(w) >= 3]
            b_ = set(self._tok(e['speaker'] + ' ' + e['speaker_title']))
            if not a_:
                return any(r in b_ for r in self._tok(pdf_spk) if r in ('speaker', 'chairperson', 'chairman'))
            return any(w == m or (len(w) >= 5 and len(m) >= 5 and (w in m or m in w or Levenshtein.distance(w, m) <= 2)) for w in a_ for m in b_)
        for it in self.ref:
            if it['k'] != 'P' or not it['spk']:
                continue
            p = it['start']
            for s0, s1, e in spans:
                if s0 + 25 < p < s1 - 25 and e['label'] in ('speech', 'other'):
                    if e['label'] == 'speech' and same_person(it['spk'], e):
                        break
                    self.flag(e, f"PDF shows a new speaker ('{it['spk']}') starting inside this block: \"{it['t'][:60]}...\". May need a split.")
                    break

    def check_unlocated(self):
        P = self.ordered_positions()
        for e, p in zip(self.E, P):
            if e['label'] in ('deleted',) or len(norm(e['text'])) < 12 or p is not None:
                continue
            if self.locate(e['text']) is None and self.locate(e['text'], tail=True) is None:
                self.flag(e, "Couldn't find this text in the PDF. Check it against the PDF.")

    def check_speakerless(self):
        for e in self.E:
            if e['label'] == 'speech' and not e['speaker'] and not e['speaker_title']:
                self.flag(e, "Speech with no speaker.")

    def split_hidden_headings(self):
        """A PDF heading whose text sits inside a non-heading block -> split it out (tool: split)."""
        heads = [it for it in self.heading_texts() if len(it['n']) >= 10]
        changed = True
        while changed:
            changed = False
            for i, e in enumerate(self.E):
                if e['label'] in ('heading', 'deleted'):
                    continue
                txt = e['text']
                for h in heads:
                    # find heading text in raw text, allowing flexible whitespace
                    pat = r'\s*'.join(re.escape(w) for w in h['t'].split())
                    m = re.search(pat, txt)
                    if not m or (m.start() == 0 and m.end() == len(txt.rstrip())):
                        if m and m.start() == 0 and m.end() >= len(txt.rstrip()) - 1 and e['label'] in ('other', 'scene', 'speech') and not e['speaker']:
                            e['label'] = 'heading'; e['text'] = h['t']; changed = True
                            self.log.append(('relabel ->heading', h['t']))
                            break
                        continue
                    before, after = txt[:m.start()].strip(), txt[m.end():].strip()
                    if upper_ratio(h['t']) < 0.75:
                        # mixed-case headings (First Reading etc.) are only real when they stand alone
                        continue
                    after_label, after_spk = None, None
                    if after and before:
                        pos = self.locate(after); k = self.item_at(pos)
                        spk = self.ref[k]['spk'] if k is not None and self.ref[k]['start'] >= (pos or 0) - 3 else ''
                        if spk:
                            after_label, after_spk = 'speech', spk_name(spk)
                    pieces = self.tool_split(e, before, m.group(0).strip(), after, 'heading', after_label, after_spk)
                    for p in pieces:
                        if p['label'] == 'heading' and norm(p['text']) == h['n']:
                            p['text'] = h['t'] if norm(m.group(0)) == h['n'] else p['text']
                    self.E[i:i + 1] = pieces
                    self.log.append(('split hidden heading', h['t']))
                    changed = True
                    break
                if changed:
                    break

    def merge_spurious_headings(self):
        """JSON 'heading' whose text is not a PDF heading but sits inside a speech paragraph
        (italicised words, quotes) -> combine back: prev speech + heading + following fragment."""
        heads_n = {it['n'] for it in self.heading_texts()}
        i = 1
        while i < len(self.E):
            e = self.E[i]
            nt = norm(e['text'])
            is_real = nt in heads_n or any(h in nt for h in heads_n if len(h) > 8) or any(nt in h and len(nt) > 0.6 * len(h) for h in heads_n) \
                or (upper_ratio(e['text']) > 0.9 and any(h.startswith(nt) or h.endswith(nt) for h in heads_n if len(nt) >= 8))
            if e['label'] == 'heading' and nt and not is_real:
                pp = self.locate(self.E[i - 1]['text'])
                pos = self.locate(e['text'], after=pp or 0)
                k = self.item_at(pos)
                prev = self.E[i - 1]
                if prev['label'] == 'scene' and prev['text'].count('(') > prev['text'].count(')') and not prev['text'].rstrip().endswith((')', ']')) and i + 1 < len(self.E) and self.E[i + 1]['label'] == 'scene':
                    nx = self.E[i + 1]
                    prev['text'] = (prev['text'].rstrip() + ' ' + e['text'].strip() + ' ' + nx['text'].lstrip()).replace('  ', ' ')
                    del self.E[i:i + 2]; self.log.append(('rejoined broken scene', prev['text'][:60])); continue
                if k is not None and self.ref[k]['k'] in ('P', 'S') and prev['label'] == 'speech':
                    prev['text'] = prev['text'].rstrip() + '\n\n' + e['text'].strip()
                    del self.E[i]
                    self.log.append(('merged spurious heading', e['text']))
                    # following fragment in same PDF paragraph
                    if i < len(self.E):
                        nx = self.E[i]
                        p2 = self.locate(nx['text']); k2 = self.item_at(p2)
                        if k2 == k and nx['label'] in ('speech', 'other'):
                            prev['text'] = prev['text'].rstrip() + '\n\n' + nx['text'].strip()
                            del self.E[i]
                            self.log.append(('merged fragment after spurious heading', nx['text'][:50]))
                    continue
            i += 1

    def fix_heading_blocks(self):
        TALLY = re.compile(r'^\s*(\d+\s*)?(AYES|NOES|ABSTENTIONS?|ABSENTIONS?)?\s*:?\s*\d*\s*$', re.I)
        i = 1
        while i < len(self.E):
            e = self.E[i]
            if e['label'] == 'heading':
                t = e['text'].strip()
                if not norm(t) and self.E[i - 1]['label'] in ('speech', 'other', 'scene'):
                    self.E[i - 1]['text'] = self.E[i - 1]['text'].rstrip() + '\n\n' + t
                    del self.E[i]; self.log.append(('punctuation-only heading merged back', t)); continue
                if t and TALLY.match(t) and self.E[i - 1]['label'] in ('speech', 'other'):
                    self.E[i - 1]['text'] = self.E[i - 1]['text'].rstrip() + '\n\n' + t
                    del self.E[i]; self.log.append(('tally heading merged back', t)); continue
                m = re.match(r'^(.*?\S)\s*(\((?:Question|Order|The|Motion|Bill)[^()]*(?:\([^()]*\)[^()]*)*\))\s*(.*)$', t, re.S)
                if m and not m.group(3):
                    self.E[i:i + 1] = self.tool_split(e, m.group(1), m.group(2), '', 'scene')
                    self.log.append(('heading/parenthetical split', t[:60])); i += 2; continue
            i += 1

    def fill_empty_speakers(self):
        for i, e in enumerate(self.E):
            if e['label'] == 'speech' and not e['speaker'] and not e['speaker_title']:
                j = i - 1
                while j > 0 and self.E[j]['label'] in ('heading', 'scene'):
                    j -= 1
                if j >= 0 and self.E[j]['label'] == 'speech' and (self.E[j]['speaker'] or self.E[j]['speaker_title']):
                    e['speaker'], e['speaker_title'] = self.E[j]['speaker'], self.E[j]['speaker_title']
                    self.log.append(('filled empty speaker', e['text'][:40]))

    def is_names_list(self, t):
        return len(re.findall(r'Sen\.[^;,]{0,45}?,\s*[A-Z][\w\'-]+(\s[A-Z][\w-]+)?\s+County', t)) >= 2 or (bool(DIV_RE.match(t)) and not self.is_tally(t))

    def is_tally(self, t):
        return bool(re.match(r'^\s*((AYES|NOES|ABSTENTIONS?|ABSENTIONS?)\s*:?\s*(\d+|Nil\.?)?\s*)+(The\s+"?Ayes"?\s+have it\.?)?\s*$', t.replace('\n', ' '), re.I)) or bool(re.match(r'^\s*\d+\s*(The\s+"?(Ayes|Noes)"?\s+have it\.?)?\s*$', t))

    def split_bill_titles(self):
        i = 0
        while i < len(self.E):
            e = self.E[i]
            if e['label'] == 'heading':
                parts = re.split(r'(?<=\))\s+(?=THE\s+[A-Z][A-Z ,()\'-]*BILL\b)', e['text'].strip())
                if len(parts) > 1:
                    blocks = self.tool_split(e, parts[0], ' '.join(parts[1:]), '', 'heading')
                    self.E[i:i + 1] = blocks; self.log.append(('one heading per bill', str(len(parts)))); i += len(parts); continue
            i += 1

    def carry_speaker(self):
        """Owen keeps 'other' only for front matter and division name lists; anything else said in a
        turn is speech. Vote tallies read by the Chair go into the Chair's speech."""
        i = 3
        while i < len(self.E):
            e = self.E[i]
            if e['label'] != 'other' or self.is_names_list(e['text']):
                i += 1; continue
            prev = self.E[i - 1]
            if self.is_tally(e['text']) and prev['label'] == 'speech':
                prev['text'] = prev['text'].rstrip() + '\n\n' + e['text'].strip()
                del self.E[i]; self.log.append(('tally merged into chair speech', e['text'][:30])); continue
            if self.is_tally(e['text']):
                i += 1; continue
            pos = self.locate(e['text']); k = self.item_at(pos)
            if k is not None and self.ref[k]['k'] == 'P' and self.ref[k]['spk'] and self.ref[k]['start'] >= (pos or 0) - 3:
                e['label'] = 'speech'; e['speaker'], e['speaker_title'] = spk_name(self.ref[k]['spk'])
            else:
                j = i - 1
                while j > 0 and self.E[j]['label'] != 'speech':
                    j -= 1
                if j <= 0:
                    i += 1; continue
                e['label'] = 'speech'; e['speaker'], e['speaker_title'] = self.E[j]['speaker'], self.E[j]['speaker_title']
            self.log.append(('other->speech', e['text'][:50]))
            i += 1

    def split_embedded_scenes(self):
        scenes = [it for it in self.ref if it['k'] == 'S' and len(it['n']) >= 8]
        i = 0
        while i < len(self.E):
            e = self.E[i]
            if e['label'] == 'speech':
                for sc in scenes:
                    pat = r'\s*'.join(re.escape(w) for w in sc['t'].split())
                    m = re.search(pat, e['text'])
                    if m and (m.start() > 0 or m.end() < len(e['text'].rstrip())):
                        before, mid, after = e['text'][:m.start()].strip(), m.group(0), e['text'][m.end():].strip()
                        self.E[i:i + 1] = self.tool_split(e, before, mid, after, 'scene')
                        self.log.append(('split embedded scene', mid[:50]))
                        break
            i += 1

    def merge_continuations(self):
        """'other' (or misattributed fragment) that continues the previous speaker's turn in the PDF
        -> combine into previous speech (tool: combine with next, joins with blank line)."""
        i = 1
        while i < len(self.E):
            e, prev = self.E[i], self.E[i - 1]
            if e['label'] == 'other' and prev['label'] == 'speech' and not DIV_RE.match(e['text']):
                p0 = self.locate(prev['text'])
                pe = (p0 + len(norm(prev['text']))) if p0 is not None else self.locate(prev['text'], tail=True)
                ps = self.locate(e['text'], after=max(0, (pe or 0) - 200))
                if pe is not None and ps is not None and ps > (p0 if p0 is not None else pe - 5):
                    pe = min(pe, ps)
                    between = [it for it in self.ref if it['start'] >= pe - 2 and it['end'] <= ps + 2 and it['k'] in ('H', 'S')]
                    k = self.item_at(ps)
                    new_turn = k is not None and self.ref[k]['spk'] and self.ref[k]['start'] >= ps - 3
                    if not between and not new_turn:
                        prev['text'] = prev['text'].rstrip() + '\n\n' + e['text'].strip()
                        del self.E[i]
                        self.log.append(('merged continuation', e['text'][:50]))
                        continue
                    if not between and new_turn:
                        e['label'] = 'speech'; e['speaker'], e['speaker_title'] = spk_name(self.ref[k]['spk'])
                        self.log.append(('other->speech new turn', e['text'][:50]))
            i += 1

    def insert_missing_headings(self):
        """PDF headings absent from the JSON -> insert a heading block at the right place."""
        present = [norm(e['text']) for e in self.E if e['label'] == 'heading']
        allj = ' '.join(present)
        for it in self.heading_texts():
            if it['n'] in present or len(it['n']) < 4:
                continue
            if any(it['n'] in p for p in present):
                continue
            # find the JSON block whose PDF position follows this heading
            target = None
            for j, e in enumerate(self.E):
                pos = self.locate(e['text'])
                if pos is not None and pos >= it['end'] - 2:
                    target = j; break
            if target is None:
                continue
            if target == 0:
                continue
            self.tool_insert_after(target - 1, 'heading', it['t'])
            present.append(it['n'])
            self.log.append(('inserted missing heading', it['t']))

    def run(self):
        self.front_matter()
        self.fix_speaker_fields()
        self.split_hidden_headings()
        self.merge_spurious_headings()
        self.fix_heading_blocks()
        self.split_bill_titles()
        self.split_embedded_scenes()
        self.merge_continuations()
        self.insert_missing_headings()
        for _ in range(3):
            n = len(self.E)
            self.carry_speaker()
            self.fill_empty_speakers()
            self.merge_continuations()
            if len(self.E) == n:
                break
        self.fix_speaker_fields()
        self.check_names()
        self.check_turns()
        self.check_unlocated()
        self.check_speakerless()
        flagged = {id(e) for e, _ in self.flags}
        for k, e in enumerate(self.E):
            e['order'] = k + 1
            e['reviewed'] = id(e) not in flagged
        return self.E

    def flag_report(self):
        rows = []
        order = {id(e): k + 1 for k, e in enumerate(self.E)}
        P = self.ordered_positions()
        page = {}
        for e, p in zip(self.E, P):
            k = self.item_at(p) if p is not None else None
            page[id(e)] = self.ref[k]['p'] if k is not None else None
        for e, reason in sorted(self.flags, key=lambda f: order.get(id(f[0]), 0)):
            rows.append(dict(block=order.get(id(e)), pdf_page=page.get(id(e)), id=e['id'], label=e['label'], speaker=e['speaker'],
                             text=e['text'][:120].replace('\n', ' '), reason=reason))
        return rows

def spk_name(s):
    """PDF 'The Deputy Speaker (Sen. (Prof.) Kindiki)' -> ('The Deputy Speaker', '(Sen. (Prof.) Kindiki)')"""
    s = (s or '').strip()
    m = re.match(r'^(.*?)\s*(\(.*\))\s*$', s)
    if m and m.group(1):
        return m.group(1).strip(), m.group(2).strip()
    return s, ''

if __name__ == '__main__':
    d, inp, outp = sys.argv[1:4]
    data = json.load(open(inp))
    A = Auditor(d, data['entries'])
    data['entries'] = A.run()
    json.dump(data, open(outp, 'w'), indent=2, ensure_ascii=False)
    json.dump(A.flag_report(), open(outp.replace('.json', '.flags.json'), 'w'), indent=1, ensure_ascii=False)
    for l in A.log:
        print(*l, sep=' | ')
