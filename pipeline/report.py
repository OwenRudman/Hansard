import csv,re,glob,os,collections,json
rows=list(csv.DictReader(open('out/summary.csv')))
st=collections.Counter(r['status'].split()[0] if r['status'].startswith('ERROR') else r['status'] for r in rows)
print('sittings',len(rows),dict(st))
fl=sum(int(r['flags']) for r in rows if r['flags'] not in ('',None))
print('total flags',fl)
types=collections.Counter(); per=collections.defaultdict(collections.Counter)
def kind(reason):
    for k,p in [('name in PDF does not match Speaker/Title','^Name check: PDF says .*block says'),('speech with no speaker','block has no speaker|^Speech with no speaker'),('PDF shows new speaker inside a block','new speaker'),
                ('text not found in PDF',"find this text in the PDF"),('heading removed from box, not confirmed in PDF',"couldn't find that heading|but the PDF heading here is"),('Quorum/Division cutout placed by Suggest hierarchy','cutout'),('heading with no level from Suggest hierarchy','gave this heading no level'),
                ('PDF layout not recognised (checks did not run)','layout not recognised'),('empty sitting on Mzalendo','Empty sitting'),('page markers marked deleted','page markers'),
                ('Mzalendo date/duplicate problem','Mzalendo')]:
        if re.search(p,reason,re.I): return k
    return 'other: '+reason[:70]
for f in glob.glob('out/check/* - flags.txt'):
    name=os.path.basename(f).replace(' - flags.txt','')
    txt=open(f).read()
    for m in re.finditer(r'^\d+\. .*\n   (.*)$',txt,re.M):
        k=kind(m.group(1)); types[k]+=1; per[name][k]+=1
for k,v in types.most_common(): print(f'  {v:5d}  {k}')
yr=collections.defaultdict(lambda:[0,0,0,0])
for r in rows:
    y=r['file'][:4]; yr[y][0]+=1
    if r['flags'] not in ('',None): yr[y][1]+=int(r['flags']); yr[y][2]+=int(r['blocks'] or 0); yr[y][3]+= r['status']=='check'
for y in sorted(yr):
    n,f,b,c=yr[y]; print(y,'sittings',n,'flags',f,'flags/sitting %.2f'%(f/n),'flags/1000 blocks %.1f'%(1000*f/max(b,1)),'check',c)
manual=['2017-08-31','2017-09-13','2017-09-14','2017-09-26','2017-09-27','2017-09-28','2017-10-10','2017-10-11','2017-10-12','2017-11-07','2017-11-08','2017-11-09','2017-11-29']
print('done manually:',[(r['file'][:10],r['status'],r['flags']) for r in rows if r['file'][:10] in manual])
print('failures:',[(r['file'],r['status']) for r in rows if r['status'] not in ('ready','check')])
for d in ['2020-08-11','2020-08-17']:
    for r in rows:
        if r['file'].startswith(d): print(r)
