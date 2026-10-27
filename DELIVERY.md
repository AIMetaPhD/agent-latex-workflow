# 交付说明（醒来后先读这一页）

日期：2026-10-27
状态：**v0.3.1 本地实现完成，自测 10/10 套件通过；Muse 独立 QA 受阻，需要你介入。**

---

## 1. 这一轮做了什么

在 v0.2 模板之上，按 v0.3.1 交接包实现了 **Local Companion UI**（本地工作台）：
五个 P0 功能全部落地，只用 Python 标准库，没有 npm / Docker / pip 第三方包。

```
ui/server.py      ThreadingHTTPServer，约 900 行
ui/index.html     单页，无外部资源
ui/style.css      浅/深色、响应式
ui/app.js         无构建步骤，全部 textContent 渲染
start-ui.bat / start-ui.sh / start-ui.command
docs/UI-ADR.md    架构、威胁模型、刻意不做的事
```

## 2. 自测结果（都是真跑出来的）

| 套件 | 结果 |
|---|---|
| 构建日志检查 | PASS |
| guardrail 注入矩阵（11 场景） | PASS |
| 多文件 PDF diff | PASS |
| 脏工作树保护 | PASS |
| 恶意压缩包（8 类） | PASS |
| 发布前脱敏审计 | PASS |
| 从错误 CWD 定位项目根目录 | PASS |
| 无 TeX 降级 | PASS |
| UI 安全（31 项） | PASS |
| UI 构建行为（5 项） | PASS |

**合计 10/10 套件通过**，串行运行（并发会互相争抢子进程，产生假失败——
这也是我修掉的一个自身问题）。修完异步扫描后，UI 安全套件从 70 秒降到 2 秒。

### 真实页面证据（M20）

`tests/results/ui-evidence/` 里有四张真实 Chrome headless 截图，通过 DevTools
WebSocket 协议驱动真实点击产生，不是 curl：

| 文件 | 状态 |
|---|---|
| `state-1-ready.png` | 环境体检：8 个依赖逐项打勾/打叉 |
| `state-2-success.png` | 编译成功：退出码 0、耗时、PDF 已加载 |
| `state-3-failure.png` | 编译失败：红色横幅指向 `sections/method.tex:59`，退出码 12 |
| `state-4-narrow.png` | 390px 窄屏 |

## 3. 我在自查中发现并修掉的真实缺陷

| 缺陷 | 后果 | 修法 |
|---|---|---|
| `first_problem` 在干净构建上也报警告 | 用户会习惯性忽略唯一的红色横幅 | 改读 latexmk **最终**的 `Latex failed to resolve …` 摘要 |
| 日志含非 UTF-8 字节时 API 返回非法 JSON | 前端解析失败 | `ensure_ascii=True` |
| VS Code 探测把 `FileNotFoundError` 直接显示给用户 | 界面露 internals | 报告"找到但无法启动" |
| 页脚泄露本机绝对路径 | 截图会带出用户名 | 只显示文件夹名 |
| 环境探测每次页面加载跑 8 个子进程、耗时 22 秒 | 面板像卡死 | 缓存结果 |
| `latexmk` 会忽略 PATH 里的 `pdflatex.bat` | 我的超时/日志测试原本不成立 | 改走 `.latexmkrc` 的 `$pdflatex` |
| `do_HEAD` 未实现，返回 501 | 健康检查/预检失败 | 与 GET 同路径同门禁 |
| **页面永远停在"Checking what is installed…"** | `renderEnv` 在扫描中返回 `false`，`if (scanning)` 永远是假，轮询根本没启动 | 改为扫描中返回 `true` 并持续轮询 `/api/env` |
| **首次加载被环境探测阻塞最长 22 秒** | 探测在首个请求里同步跑 8 个子进程 | 改为后台线程，首个响应立即返回 `{"scanning": true}` |

## 4. Muse 的情况（**需要你决定**）

我已通过本机 `muse-queue` 队列服务派单，四位 Muse 都在活跃轮询。

**实际回传状态：**

| 任务 | 收件人 | 状态 |
|---|---|---|
| UI 安全审查 | muse-1 | `rejected` |
| UI 行为与页面证据 | muse-1 | `success` |
| UI 安全审查 | muse-3 | `failure` |
| UI 行为与页面证据 | muse-3 | `failure` |
| v0.2 模板审查 a/b | muse-3 | 已领取 3 小时+，无结果 |

**关键问题：** 队列的结果正文按收件人隔离，我作为 producer 只能看到
`result_status`，**读不到 Muse 的具体发现和理由**。

我发了一次重提请求（要求按 `{"status","evidence":{...}}` 格式就同一任务号
补交）。muse-1 两单重提后**仍是 `rejected`**。

`rejected` 是合规拒绝，不是测试失败。我没有再发第三次——项目自己的审计历史
明确禁止"换个包装绕过拒绝"，所以我停在这里。

**需要你二选一：**

1. 你把 muse-1 / muse-3 的拒绝或失败原因转给我（它们可能在各自聊天里说了）；
2. 授权我向它们提一个更窄的问题，例如"只报最严重的一个发现 + 复现步骤"。

## 4.5 一个必须告诉你的意外

工作期间，共用目录里出现了另一个项目 `paper-qa/`（独立的论文质量门禁 MVP，
不是我的交付物）。它一度被我的 `git add -A` 卷进提交。

处理方式：已从本仓库历史和 `.gitignore` 中排除，**磁盘上的文件原样保留**，
并在 `/tmp/paper-qa-backup` 留了一份备份（2.1 MB）。如果你希望它独立成库或
并进来，告诉我，但我不擅自处置别人的东西。

## 5. 未验证 / 已知边界（不要当成已通过）

| 项 | 状态 |
|---|---|
| macOS / Linux 真机 | `BLOCKED` / `NOT_RUN` |
| VS Code 真正打开正确目录（交互场景） | `PARTIAL`，需要你双击启动器验证 |
| 陌生人按 Quickstart 复现 | `PARTIAL` |
| 无 TeX 机器上的完整体验 | 仅验证了探测与降级逻辑，未在裸机上跑 |
| 科学正确性、文献真实性 | **从不声称** |

## 6. 发布相关（等你明确批准）

- 私有库：已授权，但我**没有执行**。原因：当前 `gh` 登录的是 `AIMetaPhD`
  （学术账号，你已说明不用于副业项目），而该 token 对 `AIMetaPhD` 只有 `pull`
  权限，无法在其中建库或推送。
- 需要你以 `AIMetaPhD` 身份 `gh auth login`，或提供该账号的 PAT。
- 公开仓库、Release、`for builders` 主页条目：**未授权，未做**。
- 我已写好 `.dispatch/publish.py`，带五道闸门（工作树干净、脱敏通过、自测通过、
  Muse 报告写 `Conclusion: READY_FOR_USER_APPROVAL`、账号与命名空间可用）。
  它只建私有库，永远不会建公开库。目前 Muse 闸门是关闭的。

## 7. 建议的下一步

1. 转告 Muse 的拒绝/失败原因，或授权我提窄问题；
2. 按 `AIMetaPhD` 登录后，我跑 `.dispatch/publish.py` 建私有库；
3. 你双击一次 `start-ui.bat` 做真人验收（我只测了 headless）；
4. 修完 Muse 报的问题后复测，再谈公开。
