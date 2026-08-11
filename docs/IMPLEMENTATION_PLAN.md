# 实施计划

## 1. 技术边界

初始版本是一个 Skill 型 Codex 插件，而不是远端服务或 MCP 应用。确定性部分使用 Python 标准库和本地可选工具；需要视觉判断的部分由 Codex Main agent 根据 Skill 指令调度 Luna 子代理。

## 2. 仓库组成

- 仓库级 Marketplace，指向 `plugins/visual-inspection`；包名与命令为 `visual-inspection` / `$visual-inspection`。
- 插件 manifest、Skill、审计策略、JSON Schema 与确定性辅助脚本。
- 独立的公开 fixtures、测试、CI、文档、许可证与贡献说明。
- README 图像使用自绘 SVG 和由公共 fixture 产生的可复现报告资产。

## 3. 实施阶段

1. 持久化 PRD、系统设计、实施计划、测试计划与决策记录，并提交文档基线。
2. 使用 Plugin Creator scaffold 建立有效 manifest 与仓库 Marketplace。
3. 实现图位发现、SHA-256 计算、安全 PDF/LaTeX 证据准备和账本写入。
4. 实现要求账本、任务/发现 Schema 和运行完整性校验。
5. 编写 Skill：它规定 Main agent 的检查顺序、Luna 锁定、任务指令包、并发限制、失败升级和只读边界。
6. 创建手工重绘公开 fixture 与回归测试。
7. 运行静态、单元、集成和真实 Luna 烟雾测试；修复全部问题。
8. 生成 README 图，编写英文主 README、完整中文 README、贡献与隐私材料。
9. 校验插件、视觉检查 README/fixture 图、整理 Git 提交。

## 4. 实现约定

- Python 脚本不请求网络、不发送数据、不修改输入。
- 所有 JSON 均使用 UTF-8、稳定排序和可重复生成的标识符。
- 输出目录由调用者显式指定或由运行目录生成；脚本拒绝写到待审计目标内部。
- 外部命令通过参数数组调用，不拼接 shell 字符串。
- `pdftoppm`、`pdfimages` 与 `xelatex` 缺失时输出明确诊断，不伪造视觉证据。
- 版本化审计策略与 Schema 伴随插件发布；报告记录其版本。

## 5. Git 计划

1. `docs: add approved product foundation`
2. `feat: scaffold marketplace and figure acceptance skill`
3. `feat: add deterministic inventory and run validation`
4. `test: add public visual regression fixtures`
5. `docs: publish bilingual product guide and contribution materials`

公开远程、推送、标签与 PR 仅在拥有实际 GitHub 目标和用户授权时进行。
