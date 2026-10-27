# Agent-first Paper Workflow（中文入口）

[English](README.md) | 简体中文

**Git 是记录，Agent 做机械工作，你决定什么是对的。**

这是一个用于**私有**论文仓库的 GitHub 模板：编码 Agent（Claude Code、Codex、
Cursor）可以在里面安全修改，而不用 Git 的合作导师能直接读 PDF 审阅。

它不是编辑器、不是 LaTeX 编译器、不是 SaaS、也不是新的 CLI。它就是一组文件：
一份论文样例、一份契约（`AGENTS.md`）、三个技能、两步 GitHub Actions，以及四个
职责单一、限制写清楚的脚本。

```
你的论文仓库（私有）
├── AGENTS.md             Agent 唯一需要遵守的契约
├── CLAUDE.md             只指向 AGENTS.md，不存第二份规则
├── skills/               paper-edit / paper-review / paper-release
├── main.tex + sections/  论文正文（附带一份纯合成样例）
├── .latexmkrc            构建配置；它是 Perl，所以它算代码
├── .github/workflows/    只在可信分支上构建
└── tools/                PDF 差异、压缩包检查、审阅包、发布审计
```

## 为什么要做

Overleaf 让每个共享者都必须手动同步，而且没有 Agent 能安全操作的可审查历史。
私有 Git 仓库解决了历史问题，却让导师更难读——除非 Agent 把每次修改都变成
**PDF 加摘要**。

这个模板要填的缺口不是“AI 写 LaTeX”（已经有不少项目做得好，见
[docs/competitor-audit.md](docs/competitor-audit.md)），而是围绕一篇**真实的、
已在写的论文**的安全与审阅闭环：Agent 在自己的范围内工作、导师能读懂的差异、
以及不会悄悄执行别人代码的构建。

## 快速开始（Windows / macOS / Linux）

前置条件：Git、带 `latexmk` 与 `bibtex` 的 TeX 发行版（TeX Live 或 MiKTeX）、
Python 3.10+（本地工作台用）。**编译论文不需要任何 API Key**，也不需要
`pip install` 任何包。

### 1. 打开工作台（交互式，推荐）

双击对应系统的启动器：

| 系统 | 文件 |
|---|---|
| Windows | `start-ui.bat` |
| macOS | `start-ui.command` |
| Linux | `start-ui.sh` |

浏览器会打开 `http://127.0.0.1:8765/`，上面是三个带编号的步骤：
**环境体检**（装了什么、缺什么）、**编译**（一个按钮、真实日志、高亮第一个错误）、
**预览**（最新 PDF，以及用 VS Code 打开本项目）。再往下是 Agent 提示词生成器和
只读 Git 面板。

启动器从脚本自身位置定位项目，所以在任何工作目录下双击都能用。它只负责找
Python，不负责找 TeX：没有 TeX 时工作台照样启动，只是编译按钮被禁用并说明原因。

### 2. 命令行编译（进阶）

```bash
latexmk                                   # 生成 build/main.pdf
```

然后替换样例内容：改 `sections/*.tex`、`main.tex` 和 `references.bib`。
样例是刻意合成的，不含任何人的未发表工作。

端口、是否开浏览器、编译超时都可以在命令行指定：

```bash
python ui/server.py --port 8765 --no-browser --print-url --build-timeout 120
```


## 怎么用

| 你想做的事 | 对 Agent 说的话 | 你会得到 |
|---|---|---|
| 润色一段文字 | “用 paper-edit，只润色 §2.2 的语言” | 分支、改动、构建、guardrail、变更记录 |
| 看改了什么 | “用 paper-review，比较 main 和 agent/…” | 摘要、PDF 差异、审阅包 |
| 发给导师 | “打包审阅” | `dist/review-pack/`：PDF、差异、清单 |
| 冻结投稿版本 | “用 paper-release，阶段 submission” | 含提交号、PDF 哈希、环境的快照 |

Agent 只在 `agent/<日期>-<短名>` 分支工作，永不直接改 `main`，永不推送。

## 哪些被强制，哪些没有

| 检查项 | 工具 | 是否强制 |
|---|---|---|
| 论文仍能编译 | `latexmk` | 是，看退出码 |
| 纯润色任务里数字/公式/引用/标签/作者未变 | `tools/check_invariants.py` | 是，退出码 `2` 阻止提交 |
| 发布前无个人信息与凭据 | `tools/publish_audit.py` | 是，退出码 `2` 阻止发布 |
| 压缩包不会逃出目标目录 | `tools/zip_inspect.py` | 是，禁止自动解压 |
| PDF 差异里**真的**包含改动 | `tools/pdf_diff.py` | 是，抽取文本校验 |
| **科学结论正确** | — | **否，从不声称** |
| **参考文献真实存在** | — | **否；guardrail 只比对 key，不验证真伪** |

引用 guardrail 之前先读 [docs/guardrail.md](docs/guardrail.md)，那里写了已知漏检。

## 安全模型（一段话）

`.latexmkrc` 是 Perl，以你的权限执行；`latex-action` 的 `pre_compile` 是任意 bash。
因此 CI **只构建可信分支**，绝不构建 fork 的 PR，权限 `contents: read`，无 secrets，
不开 `-shell-escape`。这去掉了一类风险，但**不等于**不可信文档就安全了。细节与残余
风险见 [docs/security.md](docs/security.md)。

## 从 Overleaf 迁移

不要把 ZIP 直接解压进仓库。按
[docs/migrate-from-overleaf.md](docs/migrate-from-overleaf.md) 操作：先保留原始
ZIP 和 baseline PDF，用 `tools/zip_inspect.py` 检查压缩包，手工拷入文件，并在
Agent 动任何东西之前把 baseline 提交上去。

## 不用 Git 也能审阅

[docs/collaborate-without-git.md](docs/collaborate-without-git.md) 说明了审阅包里
有什么、导师该看哪里、以及这个包**刻意不声称**什么。

## 本地工作台

`start-ui.bat`（Windows）/ `start-ui.command`（macOS）/ `start-ui.sh`（Linux）
会在浏览器里打开一个页面，覆盖新手真正需要的五件事。它是本仓库的控制面板，
不是编辑器。

| 面板 | 做什么 | 明确不做 |
|---|---|---|
| 环境体检 | 检查 Git、Python、latexmk、LaTeX 引擎、BibTeX、Perl，以及可选的 VS Code 和 latexdiff；说明缺什么、为什么、官方安装命令 | 从不替你安装任何东西 |
| 编译 | 后台运行 `latexmk`，显示真实状态、退出码、耗时、日志尾部和第一个错误 | 从不同时跑两个编译；从不执行自定义命令 |
| 预览 | 以 `no-store` 提供 `build/main.pdf`，装了 VS Code 就打开本项目 | 从不读取其他任何文件 |
| Agent 提示词 | 从 `sections/*.tex` 生成限定范围的任务提示词 | 从不调用模型，从不发送任何内容 |
| Git | 显示分支、`git status --porcelain`、`git diff --stat` 和 guardrail | 永不 commit、branch、checkout、reset、push |

安全设计：只绑定 `127.0.0.1`；每个请求都校验 `Host` 头（因此 DNS rebinding
进不来）；要求会话 Cookie，其 token 走 URL fragment 而不是 query string 或日志；
任何会改变状态的请求都校验 `Origin`；不输出任何 CORS 头。编译是固定命令、有超时、
日志有上限。完整威胁模型和刻意不做的事见 [docs/UI-ADR.md](docs/UI-ADR.md)。

**离开你机器的内容：没有。** 没有模型 API、没有遥测、没有外部字体/脚本/图片。
如果你随后把生成的提示词交给某个 Agent，是那个工具按它自己的政策决定发什么——
两者是分开的。

## 环境要求（实测记录）

| | 最低 | 本机实测 |
|---|---|---|
| Python | 3.10+（只用标准库） | 3.13.9 |
| Git | 2.23（需要 `git switch`） | Windows 11 上 2.55.0 |
| TeX Live | 2023，`latexmk` ≥ 4.7 | TeX Live 2025，`latexmk` 4.86a |
| `latexdiff` + `latexpand` | 较新版本 | `latexdiff` 1.3.4，`latexpand` 1.7.2 |
| Python（仅工具） | 3.10，仅标准库 | 3.13.9 |
| `pdftotext`（差异校验，可选） | — | 已安装（Poppler） |

`xelatex` / `lualatex` 由 TeX Live 支持，但本模板**只测过 `pdflatex`**。需要时改
`.latexmkrc` 的 `$pdf_mode` 并自行验证字体，样例没有覆盖这条路径。

## 常见问题

**必须用 VS Code 吗？** 不必。任何编辑器都可以，LaTeX Workshop 只是最省事的
“保存即编译”。

**Agent 能替我写新的科学内容吗？** 能写你明确要求的文字。它不得编造结果、文献或
数字；`AGENTS.md` §4 把这些区域设为只读，除非你另行授权。

**guardrail 能证明论文没被改坏吗？** 不能。它报告指定类别里的 token 变化。句子重排或
上下文替换可以一个 token 都不变而含义全变。

**需要 API Key 吗？** 不需要。这里没有任何代码调用模型，Agent 自带。

## 限制

- 样例论文的数字是编的，不要引用。
- 只测过 `pdflatex`。IEEEtran 兼容，但没有随仓库分发（类文件有自己的许可证）；
  真实 IEEE 项目请把出版社原始文件留在你的私有仓库里。
- 跨平台状态如实记录在 [tests/SELFTEST.md](tests/SELFTEST.md)：Windows 在本机实测，
  macOS 为 `BLOCKED`，Linux 仅 GitHub Runner 层面的结论。
- 四个脚本是维护成本。它们存在是因为每个都补上了现有工具补不了的缺口，且都写明了限制。

## 许可证

MIT。第三方组件是**依赖**而非拷贝，见
[docs/competitor-audit.md](docs/competitor-audit.md) 与
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

## 致谢

本项目刻意不去重复这些工作：
[paper-lab](https://github.com/JoseAntonioNuevo/paper-lab)、
[latex-paper-skills](https://github.com/yunshenwuchuxun/latex-paper-skills)、
[paperops](https://github.com/giacomolanciano/paperops)、
[alfred](https://github.com/dreadnode/alfred)、
[PaperKit](https://github.com/peternicholls/PaperKit)，以及在 CI 里真正负责编译的
[`xu-cheng/latex-action`](https://github.com/xu-cheng/latex-action)。
