/* Browser interaction tests. API intercepts below are explicit test fixtures,
   never live model results or mathematical capability scores. */
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const fs=require('node:fs');
const path=require('node:path');
const assert=require('node:assert/strict');
const ROOT=path.resolve(__dirname,'..');
const examples=JSON.parse(fs.readFileSync(path.join(ROOT,'examples.json'),'utf8'));
const out=path.join(ROOT,'reports');fs.mkdirSync(out,{recursive:true});
const base=process.env.CA_WEB_TEST_URL||'http://127.0.0.1:8765';
const checks=[];const errors=[];
function passed(name){checks.push(name);}
(async()=>{
  const browser=process.env.CA_WEB_TEST_CDP?await chromium.connectOverCDP(process.env.CA_WEB_TEST_CDP):await chromium.launch({headless:true,...(process.env.CA_WEB_TEST_BROWSER?{executablePath:process.env.CA_WEB_TEST_BROWSER}:{})});
  try{
    const page=await browser.newPage({viewport:{width:1440,height:1100},deviceScaleFactor:1});
    page.on('pageerror',e=>errors.push(String(e)));
    await page.goto(base);await page.locator('#report-section').waitFor({state:'visible'});
    assert.equal(await page.locator('#analyze-button').isDisabled(),true);
    assert.match(await page.locator('#report-summary').innerText(),/连续性/);passed('Unconfigured live service disabled; example explicitly labeled');
    await page.screenshot({path:path.join(out,'desktop-preview.png'),fullPage:true});
    await page.locator('.condition-button').nth(1).click();assert.match(await page.locator('#intervention-detail').innerText(),/x\+1/);passed('Condition selection changes counterexample and checks');
    await page.locator('#tab-overview').click();assert.equal(await page.locator('#overview-panel').isVisible(),true);assert.match(await page.locator('#overview-panel').innerText(),/量词/);passed('Original theorem, objects, quantifiers and hypotheses visible');
    await page.locator('#tab-dependency').click();assert.equal(await page.locator('.dependency-edge').count(),3);passed('Evidence-qualified dependencies rendered');
    const downloadPromise=page.waitForEvent('download');await page.locator('#export-button').click();const download=await downloadPromise;const saved=await download.path();const reportText=fs.readFileSync(saved,'utf8');assert.match(reportText,/预置示例/);assert.match(reportText,/H3/);assert.match(reportText,/未覆盖范围/);passed('Full report downloads with all interventions and evidence boundary');
    await page.locator('#feedback-button').click();await page.locator('#feedback-input').fill('测试问题记录：核验保留条件。');const feedbackPromise=page.waitForEvent('download');await page.locator('#download-feedback').click();const feedback=await feedbackPromise;const item=JSON.parse(fs.readFileSync(await feedback.path(),'utf8'));assert.equal(item.kind,'user_feedback_not_reviewed');assert.equal(item.source.mode,'example');passed('Feedback exports a local unreviewed record, no automatic RSI');
    for(const [subject,key] of [['高等代数','al'],['实分析','ra'],['复分析','ca'],['数学分析','ma']]){
      await page.getByRole('button',{name:subject,exact:true}).click();await page.locator('#example-button').click();
      await page.waitForFunction(key=>document.getElementById('report-summary').textContent.includes(key),examples[key].summary.slice(0,8));
      assert.equal(await page.locator('.condition-button').count(),examples[key].interventions.length);
    }passed('All four subject examples load and switch correctly');
    await page.getByRole('button',{name:'第一次使用？ ↗'}).click();assert.equal(await page.locator('#reading-dialog').isVisible(),true);await page.keyboard.press('Escape');passed('Reading guide opens and keyboard dismisses');
    await page.setViewportSize({width:390,height:844});
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth),false);await page.screenshot({path:path.join(out,'mobile-preview.png'),fullPage:true});passed('390px mobile layout has no horizontal page overflow');
    await page.setViewportSize({width:1440,height:1100});
    await page.route('**/api/config',route=>route.fulfill({json:{live_ready:true,access_code_required:true,skill_version:'1.0.0'}}));
    await page.reload();await page.locator('#analyze-button:not([disabled])').waitFor();await page.locator('#analyze-button').click();assert.equal(await page.locator('#service-dialog').isVisible(),true);
    await page.locator('#access-code').fill('fixture-code');await page.locator('#save-access-code').click();passed('Group access code requested and retained only for current page');
    let submitted;
    await page.route('**/api/analyze',async route=>{
      submitted=route.request().postDataJSON();assert.equal(route.request().headers()['x-access-code'],'fixture-code');
      const report=structuredClone(examples.ma);report.summary='<img src=x onerror="window.injection=true"> 测试文本';
      await route.fulfill({json:{mode:'live',report,meta:{skill_version:'1.0.0',elapsed_seconds:1,evidence_level:'TEST FIXTURE; NOT LIVE MODEL'}}});
    });
    await page.locator('#analyze-button').click();await page.waitForFunction(()=>document.getElementById('report-summary').textContent.includes('测试文本'));
    assert.equal(submitted.subject,'数学分析');assert.match(submitted.theorem,/连续/);
    assert.equal(await page.locator('#example-banner').isVisible(),false);passed('Live-route fixture submits selected subject and full theorem');
    assert.equal(await page.locator('#report-summary img').count(),0);assert.equal(await page.evaluate(()=>window.injection),undefined);passed('Model strings displayed as text, never executable HTML');
    await page.unroute('**/api/analyze');
    await page.route('**/api/analyze',route=>{
      const report=structuredClone(examples.ma);Object.assign(report,{status:'clarification',summary:'Lebesgue收敛定理有多个常见版本。',interventions:[],dependency_map:[],questions:['你指控制收敛定理还是单调收敛定理？']});
      return route.fulfill({json:{mode:'live',report,meta:{skill_version:'1.0.0',evidence_level:'TEST FIXTURE'}}});
    });
    await page.locator('#analyze-button').click();await page.locator('#clarification-section').waitFor({state:'visible'});assert.equal(await page.locator('#report-section').isVisible(),false);passed('Ambiguity displays a clarification form, no fabricated completed report');
    await page.unroute('**/api/analyze');await page.route('**/api/analyze',route=>route.fulfill({status:502,json:{error:'模型输出未完成，未计为有效报告。'}}));
    await page.locator('#clarification-input').fill('我指控制收敛定理。');await page.getByRole('button',{name:'补充后重新分析'}).click();await page.locator('#error-message').waitFor({state:'visible'});assert.match(await page.locator('#error-message').innerText(),/未完成/);assert.equal(await page.locator('#report-section').isVisible(),false);passed('Incomplete output presents failure without fabricated success');
    assert.equal(errors.length,0);passed('No uncaught browser JavaScript errors');
    fs.writeFileSync(path.join(out,'browser-tests.json'),JSON.stringify({status:'pass',checks,check_count:checks.length,uncaught_errors:errors,live_model_calls:0,api_test_method:'Explicit browser route fixtures; not real API or mathematics evaluation',screenshots:['desktop-preview.png','mobile-preview.png']},null,2));
    process.stdout.write(JSON.stringify({status:'pass',checks:checks.length,live_model_calls:0}));
  }finally{await browser.close();}
})().catch(e=>{fs.writeFileSync(path.join(out,'browser-test-failure.txt'),String(e.stack));console.error(e);process.exitCode=1;});
