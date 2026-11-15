# GitHub 作业提交步骤

作业截止：**11 月 30 日**。最终提交物是 GitHub 仓库链接。本文件按“内容确认—本地检查—上传—提交链接”列出操作。仓库目前没有远程地址，尚未发布。

## 一、已确认的项目设置

- 作者：侯冠伊、徐炳涵。
- 仓库：公开。
- 海报：不放入此次仓库。
- 许可证：当前不添加。公开仓库允许查看项目，但不代表授予复制、修改和再发布权限；若课程要求许可证，由全部作者同意后再添加。

已知作业要求是 GitHub 仓库链接，并在 README 清楚描述 Agent/Skill。若老师另有演示视频、报告或人工数学复核要求，再按老师要求补充。

## 二、在本机做提交前检查

1. 打开 PowerShell，进入项目目录：

   ```powershell
   cd "C:\Users\hougu\Documents\Codex\2026-11-02\du\outputs\condition-archaeologist-project"
   ```

2. 运行工程检查：

   ```powershell
   python -X utf8 scripts/check_project.py
   ```

   最终提交前以本次重新运行的结果为准；检查摘要和各项日志写入 `reports/current/engineering-summary.json`。

3. 本机打开网页做一次人工操作检查：双击 `web/启动网页.cmd`，访问 `http://127.0.0.1:8765/`，查看四科示例、报告切换和下载。真实模型测试会消耗账户额度；只有团队决定测试且预算明确后，才用本机令牌运行，不要把令牌写入仓库。

4. 检查 Git 待提交文件：

   ```powershell
   git status --short
   ```

   确认没有 `.env`、API 令牌、个人隐私文件或不应公开的内容。`.gitignore` 会排除常见本地密钥文件，但仍要人工检查。

5. 检查 README 对版本、四科范围、运行方式、Skill 流程、评测证据和限制的描述。

## 三、创建 GitHub 仓库

1. 登录 GitHub，点击 **New repository**。
2. 仓库名可用 `condition-archaeologist`，选择 **Public**。
3. 如果本地项目已有 README、不要勾选在 GitHub 上自动创建 README、LICENSE 或 `.gitignore`，避免第一次推送冲突。需要许可时先完成团队确认。
4. 创建后复制 GitHub 显示的仓库 HTTPS 地址。不要把访问令牌发到聊天。

## 四、把本地项目推送到 GitHub

在项目目录的 PowerShell 中，将 `<GitHub仓库HTTPS地址>` 替换为刚复制的地址：

```powershell
git remote add origin https://github.com/你的用户名/condition-archaeologist.git
git add README.md CHANGELOG.md .gitignore .github docs evaluation reports requirements-dev.txt scripts skill web
git status --short
```

海报不属于此次提交。`git add` 命令明确列出需要上传的文件夹，不会加入 `poster/`。在 `git status` 中确认没有密钥、令牌或个人隐私材料后，再执行：

```powershell
git commit -m "Prepare Condition Archaeologist course project"
git push -u origin main
```

如果 Git 提示缺少用户名或邮箱，按 GitHub 账户设置本机 Git 身份；不要把密码或个人访问令牌写入命令、README 或项目文件。若提交过程提示远程已有内容或发生冲突，先停止并检查，不要强制覆盖远程仓库。

## 五、检查链接并交作业

- [ ] 在浏览器打开刚推送的仓库链接，确认 README 首页能清楚说明 Agent/Skill 是什么、输入什么、按什么流程分析、输出什么以及适用范围。
- [ ] 确认仓库中能找到完整 `skill/` 和 `web/` 目录、评测说明和真实检查记录。
- [ ] 确认仓库为公开，仓库页面能正常访问且不包含令牌、个人隐私材料或未授权文件。
- [ ] 把仓库主页链接提交给老师，最好在 11 月 30 日前留出时间处理权限或推送问题。

## 当前状态说明

- 已有：项目目录、README、完整 Skill 和网页、评测工具、检查脚本及当前工程检查记录。
- 已验证：工程自动检查通过；这不等同于真实模型能力评分、独立人工审阅或形式化证明。
- 尚未完成：真实浏览器人工验收、GitHub 仓库创建与推送、向老师提交链接。
- 当前版本标识保持 Skill 1.0.0、Web 0.1.1，网页默认端口 8765。
