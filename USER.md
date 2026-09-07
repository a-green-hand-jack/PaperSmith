# PaperSmith 用户指南

本文把启动指南中的用户流程整理为可执行的使用约定。当前仓库仍是初始化 scaffold；下文的 `papersmith create`、`doctor`、`status`、`resume`、`validate` 和 Harbor task 交付流程是目标产品接口，只有对应实现和真实 provider-backed E2E 完成后才能对外宣称可用。

开发入口和当前仓库检查见 [DEV.md](DEV.md)，产品总览见 [README.md](README.md)。

## 第二阶段：用户怎么使用 PaperSmith

### 2.1 准备运行环境

| 依赖 | 用途 |
| --- | --- |
| Python 3.12 或更高版本，以及 `venv`、pip、`flock` | 安装产品及管理运行环境 |
| OpenCode 与已配置的模型服务 | 调用执行模型和审核模型 |
| Poppler：`pdfinfo`、`pdftotext` | 检查和提取原始 PDF |
| TeX 工具：`pdflatex`、`bibtex` | 编译模板、参考稿和论文提交 |
| Harbor 0.22.0 与可用的 Docker | 完成真实 oracle/nop 验收 |

本机安装器负责 Python wheel 及其依赖，不负责替用户完成 OpenCode 认证或安装全部系统工具。Docker 路径的依赖和受限挂载方式见第三阶段。[依据：安装器][installer]、[包依赖][pyproject]、[环境检查][cli]

### 2.2 安装并选择模型

在可信的仓库副本中执行：

```bash
git clone https://github.com/a-green-hand-jack/paperbench-harbor.git
cd paperbench-harbor

sh install.sh
export PATH="$HOME/.local/bin:$PATH"
papersmith --version
```

安装器将产品构建为 wheel，默认安装到 `~/.local/share/papersmith/venv`，在 `~/.local/bin` 提供命令入口。运行时不依赖源码目录；再次执行安装器可以升级。安装源与路径可通过 `PAPERSMITH_SOURCE`、`PAPERSMITH_PREFIX`、`PAPERSMITH_BIN_DIR`、`PAPERSMITH_PYTHON` 指定。[依据：安装器][installer]

完成 OpenCode 的模型服务配置后，查看实际可用的模型标识，并替换下面两个占位值。`EXEC_MODEL` 和 `REVIEW_MODEL` 是本文示例使用的 shell 变量，通过命令参数传给 PaperSmith。

```bash
opencode models

EXEC_MODEL='provider/execution-model'
REVIEW_MODEL='provider/review-model'

papersmith doctor \
  --model "$EXEC_MODEL" \
  --review-model "$REVIEW_MODEL" \
  --json
```

`doctor` 检查依赖和模型发现，不发起付费模型调用。模型出现在列表中不代表认证已经验证成功，实际调用仍可能因权限、额度或网络而失败。[依据：环境检查实现][cli]

### 2.3 先检查请求，再创建第一道任务

使用源码仓库之外的独立工作目录，并先以 `--describe` 检查请求：

```bash
RUN_DIR="$HOME/papersmith-runs/materials-demo"
REQUEST='寻找适合完整科研论文写作任务的材料科学论文，要求来源可访问、许可依据明确、结果材料充分'

papersmith create "$REQUEST" \
  --count 1 \
  --output "$RUN_DIR" \
  --model "$EXEC_MODEL" \
  --review-model "$REVIEW_MODEL" \
  --describe --headless --json
```

请求预览不会调用模型，也不会创建任务工作区。确认目标、选择策略和模型后，移除 `--describe` 正式运行：

```bash
papersmith create "$REQUEST" \
  --count 1 \
  --output "$RUN_DIR" \
  --model "$EXEC_MODEL" \
  --review-model "$REVIEW_MODEL" \
  --headless --json
```

`--count 1` 表示最终交付一道通过审核的任务，不是只生成一个候选。已有非空工作区应使用 `resume`，不能再次用 `create` 覆盖。默认任务类型是 `full_manuscript`，默认选择模式是 `discovery`。[依据：请求与创建接口][cli]

### 2.4 指定论文、材料和其他选项

需要严格限定论文时，使用固定模式：

```bash
papersmith create '基于指定论文制作完整科研论文写作任务' \
  --selection fixed \
  --paper '<真实 DOI、arXiv 标识或规范论文 URL>' \
  --count 1 \
  --output "$HOME/papersmith-runs/fixed-paper" \
  --model "$EXEC_MODEL" \
  --review-model "$REVIEW_MODEL" \
  --headless --json
```

多篇论文可重复提供 `--paper`。目标数量不能超过指定名单；固定模式不会在拒绝后自动换用其他论文。[依据：固定选择约束][schema]

其他常用选项如下，可按需添加到创建命令：

| 选项 | 使用方式与注意事项 |
| --- | --- |
| `--source /绝对路径/研究材料目录` | 私有导入限定范围的研究材料；在请求中说明其来源与许可背景 |
| `--task-kind summary` | 明确改为摘要写作任务，不用于完整论文评测 |
| `--identifiers anonymized` | 在允许的范围内隐藏焦点论文标识，不豁免必要署名或允许虚构引文 |
| `--identifiers identified` | 保留真实来源标识，默认选择 |
| `--source-cache /绝对路径/旧工作区` | 为新运行复用经过哈希核验的获取输入，不继承旧审核批准 |

本地导入与缓存复用都不是绕过来源、许可或原始 PDF 核验的通道。使用缓存时保留原工作区的记录路径，不要把搬迁后的检查点当作可直接恢复的原运行。[依据：用户选项与缓存规则][readme]

### 2.5 查看进度、恢复运行和扩展数量

```bash
# 查看进度快照
papersmith status "$RUN_DIR" --json

# 中断或修复外部依赖后继续
papersmith resume "$RUN_DIR" --headless --json

# 检查当前产物与验收证据
papersmith validate "$RUN_DIR" --json

# 检查首个交付任务后，将同一次运行扩展到总共五道题
papersmith resume "$RUN_DIR" --count 5 --headless --json
papersmith validate "$RUN_DIR" --json
```

`status` 用于了解运行状态，**`validate` 才用于判断交付是否有效**。恢复会复用输入和实现未变的已通过阶段，重启中断或失败的阶段；实现或输入变化会使相关证据失效。扩展到五道指总目标变成五道，不是再增加五道。[依据：工作流程][workflow]、[检查点与验证逻辑][product]

使用 `--json` 时，标准输出用于最终 JSON 结果，结构化进度写入标准错误和 `events.jsonl`。适合由终端、脚本或其他系统读取；不要将原始模型服务诊断或凭据内容混入公开日志。[依据：事件输出][runtime]

### 2.6 取得并使用交付任务

从 `validate` 的结果读取任务路径，不根据候选编号或目录名字猜测交付位置。重点字段包括：

| 字段 | 含义 |
| --- | --- |
| `task_ready` | 请求的交付目标是否满足当前验证要求 |
| `target_count` / `task_ready_count` | 目标数量与有效交付数量 |
| `tasks` | 可用的实际 Harbor task 路径 |
| `failures` / `integrity_failures` | 阶段或证据完整性问题 |
| `blocked_reason` | 运行阻塞原因 |

未满足交付目标时，`validate` 返回非零退出状态。[依据：验证结果接口][product]、[CLI 退出逻辑][cli]

将任务交给 Harbor 后，写作 Agent 按 `instruction.md` 的要求读取 `/workspace/materials/`，并提交完整 LaTeX 源码树：

```text
/workspace/submission/
├── main.tex
├── references.bib
└── figures/              # 使用图时携带相应文件
```

`main.tex` 需要在该目录独立编译，引用必须能在 `references.bib` 中解析，图片依赖必须包含在提交树内。不要把 `solution/`、`tests/private/` 或原始答案另外交给被评测的写作 Agent。[依据：提交契约][submission]

PaperSmith 的交付结束于制题与必要验收；选择下游写作 Agent、开展模型比较和上传数据集，需要分别执行。[依据：产品说明][readme]

### 2.7 遇到失败时怎么办

| 现象 | 处理方式 |
| --- | --- |
| 缺少命令、模型不可用 | 根据 `doctor` 补齐依赖或修复指定模型服务 |
| 认证、额度或网络问题 | 在产品外修复服务，再对原工作区执行 `resume` |
| 材料或审核要求修复 | 由控制程序回到相关阶段，不手工编造批准文件 |
| 固定论文被拒绝 | 检查拒绝依据；需要换论文时创建新的固定请求 |
| 编译失败 | 保留源码、响应和日志，修复相关问题后恢复 |
| 证据过期或哈希不一致 | 重新运行受影响阶段，不修改哈希来强制通过 |

恢复必须保持工作区的证据历史。不要删除失败尝试来掩盖问题，也不要让两个控制程序同时写入同一个运行目录。[依据：失败与恢复规则][dev]、[证据完整性验证][integrity]

[readme]: https://github.com/a-green-hand-jack/paperbench-harbor/blob/main/README.md
[schema]: https://github.com/a-green-hand-jack/paperbench-harbor/blob/main/src/paperbench_harbor/papersmith/schema.py
[cli]: https://github.com/a-green-hand-jack/paperbench-harbor/blob/main/src/paperbench_harbor/papersmith/cli.py
[ground-truth]: https://github.com/a-green-hand-jack/paperbench-harbor/blob/main/src/paperbench_harbor/papersmith/ground_truth.py
[submission]: https://github.com/a-green-hand-jack/paperbench-harbor/blob/main/docs/submission-contract.md
[oracle]: https://github.com/a-green-hand-jack/paperbench-harbor/blob/main/src/paperbench_harbor/papersmith/oracle.py
[product]: https://github.com/a-green-hand-jack/paperbench-harbor/blob/main/src/paperbench_harbor/papersmith/product.py
[workflow]: https://github.com/a-green-hand-jack/paperbench-harbor/blob/main/docs/papersmith-workflow.md
[acceptance]: https://github.com/a-green-hand-jack/paperbench-harbor/blob/main/src/paperbench_harbor/papersmith/acceptance.py
[architecture]: https://github.com/a-green-hand-jack/paperbench-harbor/blob/main/docs/papersmith-architecture.md
[runtime]: https://github.com/a-green-hand-jack/paperbench-harbor/blob/main/src/paperbench_harbor/papersmith/runtime.py
[integrity]: https://github.com/a-green-hand-jack/paperbench-harbor/blob/main/src/paperbench_harbor/papersmith/integrity.py
[installer]: https://github.com/a-green-hand-jack/paperbench-harbor/blob/main/install.sh
[pyproject]: https://github.com/a-green-hand-jack/paperbench-harbor/blob/main/pyproject.toml
[dev]: https://github.com/a-green-hand-jack/paperbench-harbor/blob/main/DEV.md
[contributing]: https://github.com/a-green-hand-jack/paperbench-harbor/blob/main/CONTRIBUTING.md
[makefile]: https://github.com/a-green-hand-jack/paperbench-harbor/blob/main/Makefile
[e2e]: https://github.com/a-green-hand-jack/paperbench-harbor/blob/main/docker/e2e.sh
[dockerfile]: https://github.com/a-green-hand-jack/paperbench-harbor/blob/main/docker/papersmith/Dockerfile
[docker-workflow]: https://github.com/a-green-hand-jack/paperbench-harbor/blob/main/docs/papersmith-docker.md
[ci]: https://github.com/a-green-hand-jack/paperbench-harbor/blob/main/.github/workflows/ci.yml
[versioning]: https://github.com/a-green-hand-jack/paperbench-harbor/blob/main/docs/dataset-versioning.md
[source-archive]: https://github.com/a-green-hand-jack/paperbench-harbor/blob/main/docs/source-archive.md
[distribution]: https://github.com/a-green-hand-jack/paperbench-harbor/blob/main/src/paperbench_harbor/distribution/cli.py
[trials]: https://github.com/a-green-hand-jack/paperbench-harbor/blob/main/docs/trial-dataset.md
