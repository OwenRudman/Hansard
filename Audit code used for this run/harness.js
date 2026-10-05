// node harness.js in.json out.json [--suggest] [--keep-levels]
const { chromium } = require('playwright'); const fs=require('fs'), path=require('path');
(async()=>{
  const [,, inp, outp, ...flags] = process.argv;
  const data = JSON.parse(fs.readFileSync(inp,'utf8'));
  const browser = await chromium.launch({executablePath:'/opt/pw-browsers/chromium'}).catch(()=>chromium.launch());
  const ctx = await browser.newContext(); await ctx.route('**/*', r => r.request().url().startsWith('file:') ? r.continue() : r.abort());
  const page = await ctx.newPage(); page.on('dialog', d=>d.dismiss()); page.on('pageerror', e=>console.error('PAGEERR', e.message));
  await page.goto('file://'+path.resolve(__dirname,'sample.html'),{waitUntil:'load'});
  const res = await page.evaluate(({data,flags})=>{
    const editor=document.getElementById('editor');
    editor.dataset.sourceUrl = data.source_url || editor.dataset.sourceUrl;
    const tpl=[...editor.querySelectorAll('.entry')].find(e=>e.dataset.label==='speech').cloneNode(true);
    editor.querySelectorAll('.entry').forEach(e=>e.remove());
    const keep = flags.includes('--keep-levels');
    for (const en of data.entries) {
      const s=tpl.cloneNode(true);
      s.className='entry'; s.dataset.label=en.label; s.dataset.originalLabel=en.original_label||''; s.dataset.level= keep ? (en.level||'') : '';
      delete s.dataset.inheritedLevel;
      s.querySelector('.label-select').value=en.label;
      s.querySelector('.level-select').value= keep && en.label==='heading' ? (en.level||'') : '';
      s.querySelector('.entry-id').textContent=en.id;
      s.querySelector('.speaker-input').textContent=en.speaker||'';
      s.querySelector('.title-input').textContent=en.speaker_title||'';
      s.querySelector('.editable-text').textContent=en.text||'';
      if (en.reviewed) s.classList.add('reviewed');
      editor.appendChild(s);
      if (typeof syncEntryLabelUI==='function') syncEntryLabelUI(s,en.label);
      if (keep && en.cutout) markCutout(s,true);
    }
    applyInheritedLevels();
    if (flags.includes('--suggest')) suggestHierarchy();
    const out=collectEntries(); out.source_url=data.source_url; return out;
  },{data,flags});
  fs.writeFileSync(outp, JSON.stringify(res,null,2)); await browser.close();
})();
