const { chromium } = require('playwright');
const fs = require('fs'), path = require('path');
(async () => {
  const [,, inDir, outDir] = process.argv;
  fs.mkdirSync(outDir, {recursive:true});
  const browser = await chromium.launch({executablePath:'/opt/pw-browsers/chromium'}).catch(()=>chromium.launch());
  const ctx = await browser.newContext();
  await ctx.route('**/*', r => r.request().url().startsWith('file:') ? r.continue() : r.abort());
  const files = fs.readdirSync(inDir).filter(f=>f.endsWith('.html'));
  for (const f of files) {
    const page = await ctx.newPage();
    page.on('dialog', d => d.dismiss());
    try {
      await page.goto('file://' + path.resolve(inDir, f), {waitUntil:'load', timeout:120000});
      await page.waitForTimeout(300);
      const res = await page.evaluate(() => ({ data: collectEntries(), name: filenameBase() }));
      // filenameBase reads the source URL; mirror downloadJSON output exactly
      const out = JSON.stringify(res.data, null, 2);
      fs.writeFileSync(path.join(outDir, res.name + '.json'), out);
      console.log('OK', f, '->', res.name + '.json', res.data.entries.length);
    } catch (e) { console.log('FAIL', f, e.message.split('\n')[0]); }
    await page.close();
  }
  await browser.close();
})();
