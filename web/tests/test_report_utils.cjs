/* Node tests for actual export/coverage behavior; not real browser testing. */
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const U=require('../static/report-utils.js');
const examples=JSON.parse(fs.readFileSync(path.join(__dirname,'../examples.json'),'utf8'));
const sample=()=>JSON.parse(JSON.stringify(examples.ma));
test('four reports export assumptions, counterexamples and evidence scopes',()=>{
  for(const report of Object.values(examples)){
    const md=U.markdown({mode:'example',report,meta:{skill_version:'1.0.0',web_version:'0.1.1',input_theorem:'原始输入'}});
    assert.ok(md.includes('原始输入'));
    for(const i of report.interventions){
      if(i.witness)assert.ok(md.includes(i.witness));
      for(const e of i.evidence)assert.ok(md.includes(e.scope));
    }
  }
});
test('export preserves live provenance, usage, questions and next steps',()=>{
  const report=sample();report.questions=['需确认的版本'];report.interventions[0].next_steps=['进一步检查'];
  const md=U.markdown({mode:'live',report,meta:{skill_version:'1.0.0',web_version:'0.1.1',request_id:'request-42',model:'returned-model',api_mode:'chat_completions',usage:{total_tokens:123},skill_prompt_sha256:'hash',input_theorem:'用户原文'}});
  for(const s of ['request-42','returned-model','123','hash','用户原文','需确认的版本','进一步检查'])assert.ok(md.includes(s));
});
test('joint analysis cannot fill single coverage',()=>{
  const r=sample();r.interventions=[r.interventions[0]];r.interventions[0].intervention.removed=['H1','H2'];
  assert.equal(U.coverage(r).analyzed,0);assert.equal(U.coverage(r).not_analyzed,3);
});
test('unresolved is displayed separately from missing analysis',()=>{
  const r=sample();r.interventions=[r.interventions[0]];r.interventions[0].judgment='unresolved';
  const c=U.coverage(r);assert.equal(c.unresolved,1);assert.equal(c.not_analyzed,2);
});
test('evidence badge follows recorded kinds',()=>{
  assert.equal(U.evidenceText({evidence:[{kind:'candidate'},{kind:'unresolved'}]}),'候选构造 · 证据不足');
});
test('clarification is preserved intact or rejected before modification',()=>{
  assert.equal(U.appendClarification('原文',' 附加版本 '),'原文\n补充说明：附加版本');
  const original='甲'.repeat(5999);
  assert.throws(()=>U.appendClarification(original,'完整补充'),/尚未提交或截断/);
  assert.equal(original.length,5999);
});
test('clarification report can be exported without completed interventions',()=>{
  const r=sample();r.status='clarification';r.interventions=[];r.dependency_map=[];r.questions=['哪个版本？'];
  assert.ok(U.markdown({mode:'live',report:r,meta:{}}).includes('哪个版本？'));
});
