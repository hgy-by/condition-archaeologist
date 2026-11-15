# 证据与计算边界

先验证对象类别和原定理版本，再验证每个保留条件，最后否定指定结论。全称条件不能靠有限采样证明；精确数优先于浮点。CAS 的 unknown/None 不是 False，求解器无输出不是无解证明。

工具 check_witness.py 接受结构化 JSON，不执行输入代码：
- matrix：有理矩阵 A；可检查 square、symmetric、invertible、diagonalizable、has_eigenvalue_in_field，field 为 real 或 complex；单独处理非方阵与未支持判定。不可实对角化不能单独推出无实特征值，使用明确的特征值字段。
- polynomial_endpoints：有理系数从高次到常数，有限有理端点 a<b；报告端点值、导数根及区间内临界点。多项式连续可微来自数学性质，脚本不负责原定理的域约束。
- spike_integral：结构 f_n=height·n^p·1_(0,n^(−q))，height有理、p整数、q正整数，n正整数；计算精确积分 height·n^(p−q)。支撑收缩、a.e.收敛、可测性仍需数学论证。
- rational_values：有理系数多项式分子/分母，报告原分母复根及指定点的值。极点与可去奇点需对照约分和声明定义域分析；不检验全局有界。

返回 partial_computation 表示仅局部义务被计算覆盖。每个 claim 都要通过才得到 claims_pass=true，缺少 claim 不能解释成完成验证。unsupported 表示未覆盖，不等于数学不成立。

任一已判定claim失败，整体claims_pass=false；没有失败但存在未知时返回null。命令行仅在claims_pass=true时成功退出。有理函数约分不会自动补定义原分母为零处的函数值。

保存完整输入、结果、脚本版本与运行时间。更一般案例依赖显式数学论证；本首版无通用形式化证明器，也无全自动数学判分器。

AI按审阅清单逐项检查时，保留具体数学理由与原回答摘要，标记ai_reviewed。审阅者可以指出并补充原回答省略的步骤，但要区分“原回答已写”与“审阅者补充”。给出不同于参考答案的有效对象应按保留义务和目标否定判定。用脚本汇总AI判断只属于内部评分，不会把AI判断变成形式化或独立人工证明。
