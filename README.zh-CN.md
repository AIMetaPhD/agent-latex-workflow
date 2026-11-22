# Agent-first Paper Workflow（中文指南）

[English](README.md) | 简体中文

**Git 是事实记录，Agent 承担机械与润色工作，研究者决定科学真实性。**

这是一个面向科研人员的 **私有** LaTeX 论文仓库 GitHub 模板。它让编程 Agent（如 Claude Code、Codex、Cursor、VS Code Copilot 等）能够在受控的边界内安全地修改论文，并为不使用 Git 的导师与合作者自动生成可直观审阅的 PDF 差异与变更摘要。

本项目**不是**另一个在线编辑器，**不是** LaTeX 编译器封装，**不是** SaaS，也**不造**重型的自研 CLI。它是一套工程化、经过实测的模板规范：包含 100% 合成的多文件论文样本、一份核心契约（`AGENTS.md`）、三个关键 Agent Skills、轻量安全的 CI 构建流，以及四个边界明确的单用途审计与验证工具。

```
你的论文仓库（私有）
├── AGENTS.md             Agent 唯一遵守的执行契约（限定修改范围与只读区域）
├── CLAUDE.md             入口引导，严格指向 AGENTS.md，防止规则漂移
├── skills/               paper-edit / paper-review / paper-release
├── main.tex + sections/  多文件合成论文（开箱即用，支持公式/表格/交叉引用）
├── .latexmkrc            构建配置（输出隔离至 build/，严格禁用 shell-escape）
├── .github/workflows/    安全 CI 构建（仅在可信分支构建，最小权限）
└── tools/                PDF 差异比对、Overleaf 迁移检查、审阅包生成、发布前脱敏
```

## 为什么选择本工作流

- **告别 Overleaf 的手动同步困境**：利用私有 GitHub 仓库作为唯一的版本真值源，拥有完整的提交历史与分支隔离。
- **保护学术不变量（Guardrail）**：严防 Agent 在润色时悄悄修改实验数值、数学公式、文献引用 Key 或作者单位。一旦越界，强制阻断并由人工确认。
- **兼顾非 Git 合作者（导师审阅）**：一键生成由 `paper-clean.pdf`、`paper-diff.pdf` 和非技术性 `review-summary.md` 组成的审阅包，导师无需安装 Git 或配置 TeX 即可审阅。
- **安全第一**：禁用 `-shell-escape`，严格防范不可信构建与外部恶意 LaTeX 代码注入。

## 快速上手

### 前置条件

- **Git**（≥ 2.23）
- **TeX 发行版**：安装包含 `latexmk` 与 `bibtex` 的 TeX Live 或 MiKTeX
- **Python**（≥ 3.10，仅需标准库，无需安装任何 pip 第三方包）

编译与本地管理论文**无需任何外部模型 API Key**。

### 1. 从模板创建仓库

在 GitHub 页面点击 **Use this template** 创建你自己的**私有（Private）**论文仓库，并克隆到本地：

```bash
git clone <你的私有仓库链接>
cd <你的仓库目录>
```

### 2. 验证本地编译

使用原生 `latexmk` 驱动编译：

```bash
latexmk
```

编译产物会自动输出至 `build/main.pdf`，终端会显示耗时与退出码。

### 3. 替换为你的真实论文

将合成样本替换为你自己的正文内容：
- 文档结构与宏包配置：`main.tex`
- 正文各章节分片：`sections/*.tex`
- 文献库：`references.bib`

## 与 Agent 协同写作流程

无论使用 Claude Code、Cursor 还是 Codex，请指示 Agent 遵守根目录的 `AGENTS.md`：

| 任务场景 | 给 Agent 的指令提示 | 交付物与保障 |
|---|---|---|
| 语言润色 | “遵循 AGENTS.md 和 skills/paper-edit，润色 §2.2，纯语言模式” | 独立分支、单句单行、编译检查、学术护栏检测、变更报告 |
| 审阅差异 | “遵循 skills/paper-review，对比 main 与 agent/...” | 变更概述、多文件 PDF 差异、生成对比报告 |
| 发送导师 | “打包审阅成果 review pack” | `dist/review-pack/` 内含完整 PDF、差异标注与清单 |
| 定稿快照 | “遵循 skills/paper-release，生成投稿快照” | 记录 Git Commit SHA、PDF 校验和与编译环境的快照 Tag |

Agent 默认在独立的分支（如 `agent/<日期>-<描述>`）上操作，严禁直接向 `main` 提交，严禁强制推送。

## 自动化检查与防护矩阵

| 检查项 | 工具 | 拦截标准 |
|---|---|---|
| 编译正常通过 | `latexmk` | 退出码非 0 则报错阻断 |
| 润色时数字/公式/引用未被改动 | `tools/check_invariants.py` | 检测到变动退出码为 2，强制人工审批 |
| 源码无个人隐私、凭据泄露 | `tools/publish_audit.py` | 扫描工作区与 Git 历史，拦截泄露 |
| Overleaf 压缩包安全性 | `tools/zip_inspect.py` | 拦截路径穿越（Zip Slip）、软链接与可执行脚本 |
| 多文件 PDF 差异标注 | `tools/pdf_diff.py` | 校验差异文本提取与可见性 |
| **科学真实性证明** | — | **绝不承诺；由研究者本人全权负责** |

关于护栏的设计范围与已知漏报边界，请参阅 [docs/guardrail.md](docs/guardrail.md)。

## 从 Overleaf 迁移已有论文

切勿直接在工作区解压不可信来源的 ZIP。请参阅 [docs/migrate-from-overleaf.md](docs/migrate-from-overleaf.md)：
1. 留存导出的原始 ZIP 和基准 PDF 作为基准底稿；
2. 运行 `python tools/zip_inspect.py <overleaf-export.zip>` 进行安全性排查；
3. 手动复制文件入库并完成初次 Commit，在干净状态下再引入 Agent。

## 验证测试套件

如需验证本模板在你当前电脑上的全套护栏与工具可用性，请运行：

```bash
python test_verify.py
```

## 开源许可证

本项目基于 MIT License 开源。关于引用的外部依赖与行为说明，详见 [LICENSE](LICENSE) 与 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
