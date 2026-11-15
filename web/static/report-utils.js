/* Shared report presentation and export logic; no network calls. */
(function(root, factory) {
  const api=factory();
  if(typeof module==='object' && module.exports)module.exports=api;
  else root.ReportUtils=api;
})(typeof globalThis!=='undefined'?globalThis:this,function(){
  'use strict';
  const labels={indispensable:'不可删',removable:'删后仍成立',implied:'被其余条件推出',joint:'组合删除失效',type_constraint:'需重写定义',unresolved:'尚未判定',statement_issue:'原命题有误'};
  const evidenceLabels={candidate:'候选构造',mathematical_argument:'数学论证',unresolved:'证据不足'};
  const states={analyzed:'已分析',unresolved:'尚未判定',not_analyzed:'未分析'};
  function coverage(report){
    const hypotheses=report.theorem.hypotheses.map(h=>{
      const items=report.interventions.filter(i=>i.intervention.removed.length===1&&i.intervention.removed[0]===h.id);
      return {...h,state:items.some(i=>i.judgment!=='unresolved')?'analyzed':items.length?'unresolved':'not_analyzed',intervention_ids:items.map(i=>i.task_id)};
    });
    return {hypotheses,total:hypotheses.length,...Object.fromEntries(Object.keys(states).map(k=>[k,hypotheses.filter(h=>h.state===k).length]))};
  }
  function evidenceText(item){
    const kinds=[...new Set(item.evidence.map(e=>e.kind))];
    return kinds.length?kinds.map(k=>evidenceLabels[k]||k).join(' · '):'未提供证据';
  }
  function appendClarification(original,addition,limit=6000){
    if(!addition.trim())throw new Error('请先填写补充说明。');
    const result=original+'\n补充说明：'+addition.trim();
    if(result.length>limit)throw new Error('补充后超过6000字，请先精简原定理或补充说明；内容尚未提交或截断。');
    return result;
  }
  function markdown(current){
    if(!current)return '';
    const r=current.report,m=current.meta||{},c=coverage(r),lines=['# 条件考古学分析报告','',
      current.mode==='example'?'类型：预置示例；未调用实时模型。':'类型：模型生成；未运行计算或独立复核。',
      'Skill版本：'+(m.skill_version||'未知')+'；网页版本：'+(m.web_version||'未记录'),
      '请求编号：'+(m.request_id||'示例')+'；模型返回名称：'+(m.model||'未调用'),
      '接口：'+(m.api_mode||'未调用')+'；耗时（秒）：'+(m.elapsed_seconds??'未记录'),
      '分析预算：'+(m.analysis_budget?JSON.stringify(m.analysis_budget):'预置示例'),
      '服务返回用量：'+(m.usage?JSON.stringify(m.usage):'未返回；不能据此推算费用'),
      'Skill提示词SHA256：'+(m.skill_prompt_sha256||'未记录'),
      '证据状态：'+(m.evidence_level||'未记录'),'',
      '## 原始输入','',m.input_theorem||'未记录','',
      '## 本报告采用的定理表述','',r.theorem.statement,'',r.summary,'',
      '## 对象、定义与量词','',...[...r.theorem.objects,...r.theorem.definitions,...r.theorem.quantifiers].map(x=>'- '+x),'',
      '## 原假设','',...r.theorem.hypotheses.map(h=>'- '+h.id+'：'+h.text),'',
      '## 原结论','',...r.theorem.conclusions.map(x=>'- '+x.id+'：'+x.text),'',
      '## 单项覆盖情况','',...c.hypotheses.map(h=>'- '+h.id+'：'+states[h.state]+'；干预：'+(h.intervention_ids.join('、')||'无')),'',
      '覆盖统计仅针对已提取条件；不证明提取完整或数学判断正确。'];
    for(const i of r.interventions){
      lines.push('','## '+i.task_id+' · '+(i.intervention.removed.join('、')||'原命题')+'：'+labels[i.judgment],'');
      if(i.intervention.replacement)lines.push('替代条件：'+i.intervention.replacement.text,'');
      if(i.witness)lines.push('反例：'+i.witness,'');
      lines.push('保留条件核对论证：','',...i.retained_checks.map(x=>'- '+x.id+'：'+x.argument));
      if(i.replacement_checks.length)lines.push('','替代条件核对：','',...i.replacement_checks.map(x=>'- '+x.id+'：'+x.argument));
      if(i.target_failure)lines.push('','失效结论 '+i.target_failure.id+'：'+i.target_failure.argument);
      lines.push('','理由：'+i.argument,'','实际证据：','',...i.evidence.map(e=>'- '+(evidenceLabels[e.kind]||e.kind)+'：'+e.scope));
      if(i.dependencies.length)lines.push('','依赖说明：'+i.dependencies.join('；'));
      if(i.uncertainties.length)lines.push('','尚缺证据：'+i.uncertainties.join('；'));
      if(i.next_steps.length)lines.push('','后续步骤：'+i.next_steps.join('；'));
    }
    if(r.dependency_map.length)lines.push('','## 条件关系','',...r.dependency_map.map(e=>'- '+e.from_ids.join('+')+' → '+e.to_id+'；'+e.kind+'；背景：'+e.context+'；'+e.argument+'；证据：'+e.intervention_ids.join('、')));
    lines.push('','## 未覆盖范围','',...r.remaining_work.map(x=>'- '+x));
    if(r.questions.length)lines.push('','## 需要确认的问题','',...r.questions.map(x=>'- '+x));
    return lines.join('\n')+'\n';
  }
  return {labels,evidenceLabels,states,coverage,evidenceText,appendClarification,markdown};
});
