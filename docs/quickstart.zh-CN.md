# 中文快速上手（从零到一份能编译的论文仓库）

目标：30 分钟内得到一个**私有**论文仓库，能本地编译 PDF，能让 Agent 安全改稿，
能让导师只看 PDF 审阅。全程不需要 API Key，不需要联网调用模型。

## 0. 你需要装什么

必装：

- **Git**（Windows 建议 Git for Windows，自带 Git Bash）
- **TeX Live**（Windows 用 TeX Live 安装包，不要用精简版；需要 `latexmk`、`bibtex`、
  `latexdiff`、`latexpand` 四个命令）
- **Python 3.10+**（只给 `tools/` 里的脚本用，只用标准库，不需要 `pip install`）

可选：

- **VS Code + LaTeX Workshop**：保存即编译、点 PDF 跳源码
- **Poppler**（提供 `pdftotext`）：用来校验 diff PDF 里真的包含改动

验证：

```bash
git --version
latexmk -v
latexdiff --version
latexpand --version
python --version
```

四个命令都有输出才继续。缺 `latexdiff` / `latexpand`：`tlmgr install latexdiff`。

## 1. 建立你的仓库

```bash
git clone <模板地址> my-paper
cd my-paper
rm -rf .git
git init -b main
git add -A
git commit -m "chore: start from the agent-first paper template"
```

先编译一次，确认环境没问题：

```bash
latexmk
```

应当生成 `build/main.pdf`，4 页左右，含一张 TikZ 图、一张表、两个公式、两处引用。
**这一步不需要任何 AI 参与**。编译不过就先修环境，不要往下走。

## 2. 先读两份文件

- `AGENTS.md`：Agent 的行为契约。你自己也要读，因为它是你和 Agent 之间的约定。
- `docs/guardrail.md`：那个检查器能做什么、**不能**做什么。

一句话总结：Agent 负责分支、改稿、编译、差异、摘要；你负责科学内容是否正确。
任何涉及数字、公式、引用 key、作者信息、图片数据的改动，都必须你点头。

## 3. 用 Agent 改一段文字

对 Claude Code / Codex 说：

```
读 AGENTS.md，然后用 paper-edit 技能润色 sections/introduction.tex 的第一段，
只改语言，不要动数字、公式、引用和结论。先告诉我你打算改哪些文件。
```

正常流程是：

1. 它会先跑 `git status` / `git log` / `git rev-parse HEAD`，并声明要改哪些文件；
2. 建一个 `agent/<日期>-<短名>` 分支；
3. 改完跑 `latexmk`；
4. 跑 guardrail（`tools/check_invariants.py`）；
5. 给你一份 `Agent change record`。

如果它跳过了第 1 步或第 4 步，直接要求它补上。

## 4. 让导师审阅

```bash
python -I tools/pdf_diff.py --base main --target HEAD \
    --expect "你改动过的一句话" --out dist/review-pack
python -I tools/review_pack.py --out dist/review-pack \
    --pdf build/main.pdf --diff dist/review-pack/main-diff.pdf \
    --summary review-summary.md
```

把 `dist/review-pack/` 打包发过去。导师只需要能打开 PDF 的软件。
`MANIFEST.md` 会说明这个包里有什么、对应哪个 commit、缺了什么。

细节见 `docs/collaborate-without-git.md`。

## 5. 从 Overleaf 迁移旧论文

**不要**把 ZIP 直接解压进仓库。顺序是：

```bash
python -I tools/zip_inspect.py ~/Downloads/overleaf.zip   # 先只检查，不解压
```

`CLEAN` 才继续；`RISKY` 就按输出修（删掉 `.latexmkrc` 之类），再重新检查。
然后把文件**手工**拷进仓库，先提交一个 baseline，再让 Agent 动手。

完整步骤见 `docs/migrate-from-overleaf.md`。

## 6. 投稿前

```bash
python -I tools/publish_audit.py --deny "你的真实姓名" --deny "你的单位"
python -I tools/review_pack.py --snapshot dist/snapshots/submission \
    --pdf build/main.pdf --stage submission
```

第一行检查**整个 git 历史**里有没有邮箱、本机路径、密钥；第二行生成含 commit、
PDF 哈希、构建环境的快照。

注意：`tools/publish_audit.py` 只能按形状匹配，判断不了“这句话会不会暴露身份”。
双盲自查清单在 `skills/paper-release/SKILL.md` 里，必须人工过一遍。

## 7. 常见问题

**编译报找不到字体/宏包？** 装完整的 TeX Live，或缺什么用 `tlmgr install` 补。
不要为了跑通去改论文。

**Windows 上 `latexmk` 不认？** 用 TeX Live 安装目录里 `latexmk.exe` 的完整路径，
或把 TeX 的 `bin\windows` 加进 `PATH`。

**`latexdiff-vc` 报 “The system cannot find the path specified”？**
这是 Windows 上的已知问题（Perl 把 `( cd … ; … )` 交给了 `cmd.exe`）。
用 `tools/pdf_diff.py`，它走的是跨平台路径。证据见 `docs/pdf-diff.md`。

**guardrail 退出码 3 是什么？** 有文件解析不了，等于“没检查到”。这时不能说安全，
要说 `NOT_VERIFIED` 并说明原因。

**能不能让 Agent 直接 push / 发 Release？** 不能。`AGENTS.md` §9 规定这些必须你
明确授权，一次一授权。
