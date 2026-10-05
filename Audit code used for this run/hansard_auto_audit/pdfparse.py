import pymupdf as fitz, re, glob, json, sys
PDF_OVERRIDE = None
def pdf_for(d):
    if PDF_OVERRIDE:
        return PDF_OVERRIDE
    return glob.glob(f'pdf/{d} - *.pdf')[0]
def lines(d):
    doc=fitz.open(pdf_for(d)); out=[]
    for pn,p in enumerate(doc):
        W=p.rect.width; mid=W/2
        for b in p.get_text('dict')['blocks']:
            for l in b.get('lines',[]):
                spans=[s for s in l['spans'] if s['text'].strip()]
                if not spans: continue
                t=''.join(s['text'] for s in l['spans']).strip()
                x0,y0,x1,y1=l['bbox']
                f=spans[0]['font']; 
                if re.search(r'SENATE DEBATES|PARLIAMENTARY DEBATES',t) and y0<80: continue
                if re.match(r'^Disclaimer', t) or 'electronic version of the Official Hansard' in t or 'Hansard Editor' in t and y0>700: continue
                bold='Bold' in f; ital='Italic' in f
                cen = x0>138 and x1<505 and abs((x0+x1)/2-307)<40
                out.append(dict(p=pn+1,y=round(y0),x0=round(x0),x1=round(x1),t=t,bold=bold,ital=ital,cen=cen,size=round(spans[0]['size'],1),
                                bold_prefix=''.join(s['text'] for s in spans if 'Bold' in s['font']) if bold else ''))
    return out
def items(d):
    """group lines into items: H heading, S scene, P paragraph (with speaker if bold prefix)"""
    L=lines(d); its=[]
    for ln in L:
        t=ln['t']
        ITAL_HEAD = re.compile(r'^(First|Second|Third)\s+Reading|^Question\s+No|^(New\s+)?Clauses?\b|^Title\b|^(First|Second|Third|Fourth|Fifth)?\s*Schedule|^Part\b|^Vote\b', re.I)
        def open_bracket(x):
            return x.count('(')+x.count('[') > x.count(')')+x.count(']') and not x.rstrip().endswith((')',']'))
        if ln['cen'] and not (ln['x0']<=130):
            if its and its[-1]['k']=='S' and open_bracket(its[-1]['t']):
                its[-1]['t']+=' '+t; continue
            if ln['ital'] and not ITAL_HEAD.match(t) and not ln['bold']:
                kind='S'
            elif t.startswith(('(','[')):
                kind='S'
            else:
                kind='H'
            if kind=='H' and its and its[-1]['k']=='H' and its[-1]['p']==ln['p'] and ln['y']-its[-1]['y_end']<22 and its[-1]['bold']==ln['bold'] and its[-1]['ital']==ln['ital']:
                its[-1]['t']+=' '+t; its[-1]['y_end']=ln['y']; continue
            if kind=='S' and its and its[-1]['k']=='S' and ln['y']-its[-1]['y_end']<16 and not its[-1]['t'].rstrip().endswith((')',']')):
                its[-1]['t']+=' '+t; its[-1]['y_end']=ln['y']; continue
            its.append(dict(k=kind,t=t,p=ln['p'],y_end=ln['y'],bold=ln['bold'],ital=ln['ital']))
        elif ln['ital'] and not ln['bold'] and ln['x0']<=135 and len(t.split())<=10 and re.match(r'^((New\s+)?Clauses?\s|Title\b|(First|Second|Third|Fourth|Fifth)\s+Schedule|Schedule\b|Part\s|Section\s|Standing Order|Regulation\s|Article\s|Rule\s)',t) and (not its or its[-1]['k']!='P' or its[-1]['t'].rstrip().endswith(('.',':','?','!','-',')'))):
            its.append(dict(k='H',t=t,p=ln['p'],y_end=ln['y'],bold=False,ital=True,left=True))
        else:
            new_par = ln['x0']>=120 and ln['x0']<=135
            m=re.match(r'^([^:]{2,90}?)\s*:',t) if ln['bold'] and new_par and len(ln['bold_prefix'].strip())>=3 else None
            if m and not re.search(r'(Sen\.|Hon\.|Speaker|Chair|Leader|Whip|Clerk|Members?|Senators?|Mr\.|Dr\.|Prof|\b[A-Z][a-z]+$)', m.group(1)):
                m=None
            if m and re.match(r'^(AYES|NOES|ABSTENTIONS?|ABSENTIONS?)\b', t[:m.end()-1].strip(), re.I):
                m=None
            if m:
                spk=t[:m.end()-1].strip()
                its.append(dict(k='P',spk=spk,t=t[m.end():].strip(),p=ln['p'],y_end=ln['y'],bold=True,ital=False))
            elif its and its[-1]['k']=='P' and not new_par:
                its[-1]['t']+=' '+t
            elif its and its[-1]['k']=='P' and new_par:
                its[-1]['t']+='\n'+t
            else:
                its.append(dict(k='P',spk='',t=t,p=ln['p'],y_end=ln['y'],bold=ln['bold'],ital=ln['ital']))
    return its
if __name__=='__main__':
    for it in items(sys.argv[1]):
        if it['k']!='P': print(f"{it['k']} p{it['p']} {'B' if it['bold'] else ' '}{'I' if it['ital'] else ' '} {it['t'][:110]}")
        else: print(f"P p{it['p']} [{it.get('spk','')}] {it['t'][:70]!r}")
