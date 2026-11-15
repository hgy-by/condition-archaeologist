# AI复核的策略迭代

当前选择AI模式，不需要用户逐题签字。运行文件references/rsi.md前半保留原独立人工路径，末节AI模式适用于当前使用；独立路径没有被冒充完成。evaluation/ai-rsi-policy.json沿用原数值门槛，明确由AI接纳，evaluation/rsi-policy.json保留原独立人工政策。

1. 保存开发任务失败记录：输入/输出、实际版本摘要、失败类型、所有保留条件、预期收益和回归风险。AI检查数学后记录reviewer_type=ai、姓名标识、日期、具体理由及证据文件sha256。未经复核不进入正式候选来源。
2. 形成proposal，source_case_ids只能来自已AI复核的development证据；编辑只进隔离目录。不能从验证/盲测答案反向提规则。
3. 用同一模型、权限、采样和预算比较原版与候选。案例家族不用于规则设计；为每份实际输出做新的AI数学审阅并保存摘要，汇总为ai_reviewed_internal。
4. AI门槛：至少8家族，配对成功增益≥0.05，2000次家族重抽样区间下界>0，反例精确率不下降，证据诚实性全部通过。任务隔离或资源不明时拒绝，不降低门槛凑通过。
5. AI接纳记录必须绑定候选摘要和门槛报告摘要；候选变动立即作废。保存旧版，安装为明确的维护动作，不随调用自动发生。
6. 退化时生成rollback记录并恢复匹配摘要的基线运行文件；保留候选、失败和拒绝原因。安装备份在reports/installed-runtime-backup-v0.2.2。

可运行命令（文件参数必须是真实生成的材料，不是空模板）：

```powershell
python evaluation/ai_rsi.py stage --proposal proposal.json --source condition-archaeologist --destination candidate-skill --evidence reviewed-development.json --out stage.json
python evaluation/ai_rsi.py gate --baseline baseline-score.json --candidate candidate-score.json --policy evaluation/ai-rsi-policy.json --out gate.json
python evaluation/ai_rsi.py accept --gate gate.json --stage stage.json --decision AI-acceptance.json --out accepted.json
python evaluation/ai_rsi.py rollback --acceptance accepted.json --reason "实际退化证据" --out rollback.json
```

proposal须有author/rationale/risk/baseline_tree_hash/source_case_ids/edits（每项path、content）；evidence数组每项含task_id/reviewer_type/reviewer/reviewed_at/reason/pool=development/mathematical_review_passed=true/artifact/artifact_sha256。两个score的dataset_digest/config_digest及任务集一致，skill_tree_hash不同，pool=isolated_validation、reference_exposure=false、candidate_rule_sources_disjoint=true。per_task各含task_id/family_id/success，metrics含witness_precision/evidence_honesty。不能只填隔离布尔值而无实际隔离证据。

AI-acceptance含reviewer_type=ai/reviewer/reviewed_at/reason/accept=true/candidate_tree_hash/gate_digest。最终接纳仍是AI内部证据，不是独立人工认证。软件单测使用明确标记的合成样例验证可接纳、拒绝、摘要变动及回滚；这不是现实RSI收益。

本次实际比较文件old-new-paired-reports.json与actual-AI-RSI-gate.json；其决定为reject_or_collect_more_evidence。不得把完整任务确认4/4解释为通过该收益门槛。日常辅助版已发布；下一轮优化只有真实隔离收益才能称已证明提升。
