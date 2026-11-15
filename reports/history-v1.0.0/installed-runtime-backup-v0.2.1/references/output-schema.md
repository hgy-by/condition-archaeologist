# 输出规范

完整定理请求使用顶层 theorem（准确表述、假设、结论）、interventions（下述单任务对象的数组）、dependency_map、remaining_work。每个 intervention 带独立编号；逐条件及组合干预不能互相覆盖。单项评测仍使用下述单对象格式，不把多项任务挤入一个 witness 字段。

遇到空空间、域或积分定义等教材约定时，优先明确写出可行版本并条件化分析；只有歧义阻止合理分析时才向用户确认。非空性常与存在性结论有关，不能不核验就判为冗余。

面向用户：先给定理的准确解释、范围和假设编号，再逐条件列：干预、新命题、数学状态、对象、所有保留假设核对、失效结论、证据及缺口。最后给有标注的依赖关系和待审事项。

机器评测输出为单个 JSON 对象：
```
{
  "task_id": "输入中的任务编号",
  "hypotheses": [{"id":"H1","text":"具体假设"}],
  "intervention": {"removed":["H1"],"replacement":null},
  "judgment":"indispensable",
  "witness":"明确的数学对象，或 null",
  "retained_checks":[{"id":"H2","argument":"逐项论证"}],
  "replacement_checks":[],
  "target_failure":{"id":"C1","argument":"精确否定结论"},
  "argument":"整体理由或删后成立的证明",
  "evidence":[{"kind":"mathematical_argument","artifact":null,"scope":"覆盖的具体义务"}],
  "dependencies":[],
  "uncertainties":[],
  "next_steps":[],
  "cost":{"elapsed_seconds":null,"model_calls":null,"tool_calls":null,"usd":null}
}
```
示意字段不是默认答案；实际报告要替换为真实内容。无法解决时 judgment=unresolved，witness=null，说明缺口。cost 的 null 表示未采集，不得填 0 冒充已测。human_reviewed/formal_checked 必须附对应审阅/证明产物。

删除后假设核对覆盖全部保留ID；弱化时还须在replacement_checks中逐条核验替代条件。对于removable/implied，target_failure=null，给删后成立的证明；不能写成“结论失败”。对于原命题有误的statement_issue，intervention.removed=[]，保留原命题全部假设，给满足原假设却推翻原结论的反例。

给数字置信概率前先说明含义；首版默认不用概率。图边必须有背景条件、目标结论、证据和未探索组合说明。
