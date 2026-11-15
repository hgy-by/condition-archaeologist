'use strict';
const $ = id => document.getElementById(id);
const labels = ReportUtils.labels;
const exampleIds = {'数学分析':'ma','高等代数':'al','实分析':'ra','复分析':'ca'};
let subject='数学分析', current=null, selected=0, busy=false, accessCode='', config={live_ready:false};
function el(tag, cls, text){const node=document.createElement(tag);if(cls)node.className=cls;if(text!==undefined)node.textContent=String(text);return node;}
function append(parent,...nodes){parent.append(...nodes);return parent;}
function para(text,cls){return el('p',cls,text);}
function sectionLabel(text){return el('span','detail-section-label',text);}
function error(message){$('error-message').textContent=message;$('error-message').hidden=false;}
function clearError(){$('error-message').hidden=true;}
function count(){$('char-count').textContent=`${$('theorem-input').value.length} / 6000`;}
function setBusy(value){busy=value;$('loading').hidden=!value;$('analyze-button').disabled=value||!config.live_ready;$('example-button').disabled=value;$('theorem-input').disabled=value;$('analysis-depth').disabled=value;document.querySelectorAll('.subject').forEach(b=>b.disabled=value);}
function setSubject(value){subject=value;document.querySelectorAll('.subject').forEach(b=>{const active=b.dataset.subject===value;b.classList.toggle('selected',active);b.setAttribute('aria-pressed',String(active));});}
function openDialog(id){const dialog=$(id);if(!dialog.open)dialog.showModal();}
async function request(url,options){const response=await fetch(url,{cache:'no-store',...options});let body;try{body=await response.json();}catch{throw new Error('网页服务返回格式异常，请检查本地服务是否仍在运行。');}if(!response.ok)throw new Error(body.error||'请求未完成。');return body;}
function tab(name){for(const t of ['analysis','overview','dependency']){const active=t===name;$(`tab-${t}`).classList.toggle('active',active);$(`tab-${t}`).setAttribute('aria-selected',String(active));$(`${t}-panel`).hidden=!active;}}
function tag(label){const neutral=['implied','removable','type_constraint'].includes(label);return el('span','judgment-tag'+(neutral?' neutral':label==='unresolved'?' unknown':''),labels[label]||label);}
function detail(index){
  selected=index;const r=current.report,item=r.interventions[index],box=$('intervention-detail');box.replaceChildren();
  [...$('condition-list').children].forEach((b,i)=>{b.classList.toggle('selected',i===index);b.setAttribute('aria-pressed',String(i===index));});
  const removed=item.intervention.removed;
  const heading=item.judgment==='statement_issue'?'先检查原命题':removed.length?'删除 '+removed.join('、')+' 之后':'检查对象与定义';
  const head=el('div','detail-header'),headText=el('div');append(headText,el('h3','',heading),para(item.intervention.replacement?'替代条件：'+item.intervention.replacement.text:'固定对象范围，保留其余原假设。'));
  append(head,headText,el('span','evidence-tag',(current.mode==='example'?'示例 · ':'模型 · ')+ReportUtils.evidenceText(item)));box.append(head);
  box.append(sectionLabel(item.witness?'具体对象与反例主张':item.judgment==='unresolved'?'当前未解决的部分':'判断与证明'));
  box.append(el('div','witness-block',item.witness||item.argument));
  const checks=el('div','checks-section');checks.append(sectionLabel('逐项核对保留条件'));
  if(!item.retained_checks.length)checks.append(para('本次干预没有其他独立编号的保留假设；对象与定义背景仍然固定。','empty-note'));
  for(const check of item.retained_checks){const line=el('div','check-row'),p=el('p');append(p,el('strong','',check.id),document.createTextNode(check.argument));append(line,el('span','check-icon','·'),p);checks.append(line);}
  checks.append(para('下列内容是核对论证，尚未经本页计算工具或独立审阅确认。','empty-note'));box.append(checks);
  if(item.replacement_checks.length){const s=el('div','checks-section');s.append(sectionLabel('核对替代条件'));for(const c of item.replacement_checks)s.append(para(c.id+' · '+c.argument));box.append(s);}
  if(item.target_failure){const failure=el('div','failure-block');append(failure,sectionLabel(item.target_failure.id+' · 原结论在哪里失效'),para(item.target_failure.argument));box.append(failure);}
  const argument=el('div','argument-block');append(argument,sectionLabel('这个条件为什么起作用'),para(item.argument));box.append(argument);
  if(item.uncertainties.length){const s=el('div','failure-block');s.append(sectionLabel('尚缺的证据'));for(const x of item.uncertainties)s.append(para(x));box.append(s);}
  const proof=el('div','argument-block');proof.append(sectionLabel('实际证据与适用范围'));for(const e of item.evidence)proof.append(para((ReportUtils.evidenceLabels[e.kind]||e.kind)+'：'+e.scope));box.append(proof);
  if(item.next_steps.length){const s=el('div','argument-block');s.append(sectionLabel('可以继续探索'));for(const x of item.next_steps)s.append(para(x));box.append(s);}
}
function renderOverview(r){
  const box=$('overview-panel'),t=r.theorem;box.replaceChildren();
  append(box,el('h3','','你的原始输入'),para(current.meta.input_theorem||'未记录'),el('h3','','本报告采用的表述'),para(t.statement));
  for(const [name,items] of [['对象与范围',t.objects],['定义与约定',t.definitions],['量词',t.quantifiers]]){if(!items.length)continue;box.append(el('h3','',name));for(const x of items)box.append(para(x));}
  box.append(el('h3','','独立编号的假设'));for(const h of t.hypotheses){const line=el('p','hypothesis-line');append(line,el('strong','',h.id),document.createTextNode(h.text));box.append(line);}
  box.append(el('h3','','需要成立的结论'));for(const c of t.conclusions)box.append(para(c.id+' · '+c.text));
}
function renderDependencies(r){
  const box=$('dependency-panel');box.replaceChildren(el('h3','','有证据支持的条件关系'),para('每一条关系只在所列保留条件的背景下成立。单项不可删不等于找到了完整的最小条件集。'));
  if(!r.dependency_map.length){box.append(para('本次没有足够证据绘制条件关系，不能自动从相邻条件推断依赖。'));return;}
  for(const edge of r.dependency_map){const line=el('div','dependency-edge'),nodes=el('div','dependency-nodes'),text=el('div');append(nodes,el('b','',edge.from_ids.join(' + ')),document.createTextNode('  →  '),el('b','',edge.to_id));append(text,para(edge.kind+' · '+edge.context),para(edge.argument),el('small','','证据：'+edge.intervention_ids.join('、')));append(line,nodes,text);box.append(line);}
}
function render(data){
  current=data;const r=data.report;clearError();$('clarification-section').hidden=true;
  if(r.status==='clarification'){renderClarification(r);return;}
  $('report-section').hidden=false;$('report-summary').textContent=r.summary;
  const cov=ReportUtils.coverage(r);$('report-count').textContent=`${cov.total} 个已提取条件 · ${cov.analyzed} 已分析 · ${cov.unresolved} 未判定 · ${cov.not_analyzed} 未分析`;
  const coverageBox=$('coverage-card');coverageBox.replaceChildren(para('单项覆盖：'+cov.hypotheses.map(h=>h.id+' '+ReportUtils.states[h.state]).join('；')),para('仅统计已提取条件。组合反例不代替各条件单删分析；已分析不代表数学已核验。','muted'));
  $('report-provenance').textContent='Skill '+data.meta.skill_version+' · 网页 '+(data.meta.web_version||'未记录')+' · 模型 '+(data.meta.model||'未调用')+' · 用量 '+(data.meta.usage?JSON.stringify(data.meta.usage):'未返回');
  $('example-banner').hidden=data.mode!=='example';
  $('condition-count').textContent=r.interventions.length+' 项干预';
  const list=$('condition-list');list.replaceChildren();
  r.interventions.forEach((item,i)=>{const button=el('button','condition-button');button.type='button';const top=el('span','condition-top');append(top,el('span','condition-id',item.intervention.removed.join(' + ')||'原命题'),tag(item.judgment));const removed=new Set(item.intervention.removed);const name=removed.size?item.hypotheses.filter(h=>removed.has(h.id)).map(h=>h.text).join('；'):'保留全部原假设，检查原结论';append(button,top,el('span','condition-text',name));button.addEventListener('click',()=>detail(i));list.append(button);});
  detail(0);renderOverview(r);renderDependencies(r);tab('analysis');
  const remaining=$('remaining-card');remaining.replaceChildren();remaining.hidden=!r.remaining_work.length;
  if(r.remaining_work.length){remaining.append(el('strong','','尚未覆盖的部分'));for(const x of r.remaining_work)remaining.append(para(x));}
  $('report-evidence').textContent=data.mode==='example'?'预置示例解析 · 未调用实时模型 · 未作形式化验证':'模型生成 · '+(data.meta.elapsed_seconds??'?')+' 秒 · 各项证据见详情；尚未进行计算或独立复核';
}
function renderClarification(r){
  $('report-section').hidden=true;const box=$('clarification-section');box.hidden=false;box.replaceChildren(el('h2','','先确认定理的含义'),para(r.summary));
  const ul=el('ul');for(const q of r.questions)ul.append(el('li','',q));box.append(ul);
  const md=el('button','secondary-button','下载澄清记录 Markdown'),json=el('button','secondary-button','下载澄清记录 JSON');
  md.addEventListener('click',()=>download('条件考古学-澄清.md',markdown(),'text/markdown;charset=utf-8'));
  json.addEventListener('click',()=>download('条件考古学-澄清.json',JSON.stringify(current,null,2),'application/json;charset=utf-8'));append(box,md,json);
  const label=el('label','','补充你采用的版本、定义或完整题目');label.htmlFor='clarification-input';const input=el('textarea');input.id='clarification-input';input.rows=3;input.maxLength=4000;
  const button=el('button','primary-button','补充后重新分析');button.addEventListener('click',()=>{if(!input.value.trim()){input.focus();return;}try{$('theorem-input').value=ReportUtils.appendClarification($('theorem-input').value,input.value);count();runAnalysis();}catch(e){error(e.message);}});append(box,label,input,button);
}
async function showExample(){
  if(busy)return;clearError();
  try{const data=await request('/api/example?id='+exampleIds[subject]);$('theorem-input').value=data.report.theorem.statement;count();render(data);}catch(e){error(e.message);}
}
async function runAnalysis(){
  if(busy)return;clearError();if(!config.live_ready){openDialog('service-dialog');return;}
  if(config.access_code_required&&!accessCode){openDialog('service-dialog');return;}
  const theorem=$('theorem-input').value.trim();if(theorem.length<8||theorem.length>6000){error('请输入8—6000字的完整定理。');$('theorem-input').focus();return;}
  setBusy(true);$('report-section').hidden=true;$('clarification-section').hidden=true;
  try{const data=await request('/api/analyze',{method:'POST',headers:{'Content-Type':'application/json',...(accessCode?{'X-Access-Code':accessCode}:{})},body:JSON.stringify({theorem,subject,depth:$('analysis-depth').value})});render(data);$('report-section').hidden||$('report-title').scrollIntoView({behavior:'smooth',block:'start'});}catch(e){error(e.message);}finally{setBusy(false);}
}
function markdown(){return ReportUtils.markdown(current);}
function download(name,content,type){const url=URL.createObjectURL(new Blob([content],{type}));const link=el('a');link.href=url;link.download=name;document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);}
document.querySelectorAll('[data-subject]').forEach(b=>b.addEventListener('click',()=>setSubject(b.dataset.subject)));
document.querySelectorAll('[data-dialog]').forEach(b=>b.addEventListener('click',()=>openDialog(b.dataset.dialog)));
document.querySelectorAll('.close-dialog').forEach(b=>b.addEventListener('click',()=>b.closest('dialog').close()));
document.querySelectorAll('dialog').forEach(d=>d.addEventListener('click',e=>{if(e.target===d){const r=d.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)d.close();}}));
document.querySelectorAll('.tab').forEach((b,index)=>{b.addEventListener('click',()=>tab(b.id.replace('tab-','')));b.addEventListener('keydown',e=>{if(!['ArrowLeft','ArrowRight','Home','End'].includes(e.key))return;e.preventDefault();const tabs=[...document.querySelectorAll('.tab')],next=e.key==='Home'?0:e.key==='End'?2:(index+(e.key==='ArrowRight'?1:2))%3;tabs[next].click();tabs[next].focus();});});
$('example-button').addEventListener('click',showExample);$('analyze-button').addEventListener('click',runAnalysis);$('theorem-input').addEventListener('input',count);
$('nav-examples').addEventListener('click',()=>{showExample();$('input-title').scrollIntoView({behavior:'smooth'});});$('nav-analysis').addEventListener('click',()=>$('input-title').scrollIntoView({behavior:'smooth'}));
$('service-button').addEventListener('click',()=>openDialog('service-dialog'));
$('save-access-code').addEventListener('click',()=>{accessCode=$('access-code').value;$('access-code').value='';$('service-dialog').close();});
$('export-button').addEventListener('click',()=>{if(current)download('条件考古学-'+current.report.task_id+'.md',markdown(),'text/markdown;charset=utf-8');});
$('export-json-button').addEventListener('click',()=>{if(current)download('条件考古学-'+current.report.task_id+'.json',JSON.stringify(current,null,2),'application/json;charset=utf-8');});
$('feedback-button').addEventListener('click',()=>openDialog('feedback-dialog'));
$('download-feedback').addEventListener('click',()=>{const input=$('feedback-input');input.required=true;if(!input.reportValidity())return;download('条件考古学-问题记录.json',JSON.stringify({kind:'user_feedback_not_reviewed',created_at:new Date().toISOString(),comment:input.value,source:current},null,2),'application/json;charset=utf-8');$('feedback-dialog').close();});
async function init(){count();try{config=await request('/api/config');$('service-status').textContent=config.live_ready?'模型配置已填写':'示例模式 · 尚未接通模型';$('live-help').textContent=config.live_ready?'真实分析会向管理员配置的模型服务发送定理，并消耗模型额度。配置存在不等于实际调用已验证。':'接通模型服务后可分析任意输入；下方示例可直接体验。';$('service-explanation').textContent=config.live_ready?'模型配置已填写，实际分析是否可用须以请求结果为准。点击“开始真实分析”后才会发送定理；本页不保存在服务器，模型服务的数据政策由管理员确认。':'当前仅提供预置示例。使用“启动ChatECNU.cmd”可在本机输入学校令牌；其他服务由管理员配置后重启网页。';$('access-code-area').hidden=!config.access_code_required;setBusy(false);}catch(e){$('service-status').textContent='本地服务未连接';error(e.message);}await showExample();}
init();
