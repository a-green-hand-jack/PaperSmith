# PaperSmith

## 产出什么

**一批可直接用于评测的 Harbor 科研论文写作任务，发布在 HF 数据集 [`Jack-Jieke-Wu/Paper-Writing-Exam`](https://huggingface.co/datasets/Jack-Jieke-Wu/Paper-Writing-Exam)。**

每个交付任务是一棵完整的任务树：写作 Agent 只看到题面与公开材料（研究概述、固定引用、可编译 LaTeX 模板、图表描述与清单、图片），要从中还原出一篇完整论文；ground truth 与私有校验器不进入它的上下文。任务只有在真实 Harbor 试跑拿到 `oracle=1.0` 且 `nop=0.0` 后才算交付——镜像能起、模板能编译、模型自报通过，都不是验收证据。

当前状态要说清楚：**已发布 1 个任务** `lspr-0023`（论文 `arXiv:2601.02265`，真实 `oracle=1/nop=0`），布局 `lifesci-paperrecon-short/`。批量并行产线正在建设中，尚未产出过一整批。

```text
真实论文 → 确定性管线 → 可验收任务树 → 真实 Harbor 试跑 → HF 数据集
                                          oracle=1 / nop=0
```

## 一次任务如何流转

`create --selection fixed --paper <arXiv>` 走完整确定性管线；discovery 选择已实现但候选池仍限 arXiv，增量 `resume` 尚未实现。

```mermaid
flowchart TD
    CMD["papersmith create<br/>--selection fixed --paper ARXIV"] --> S0["parse request → RequestSpec"]
    S0 --> S1["resolve_identifier + fetch_arxiv_source"]
    S1 --> S2["find_main_tex + probe_reducibility"]
    S2 -->|reducible| S3["derive_template + extract_references<br/>+ extract_style_files"]
    S2 -->|not reducible| REJ["paper_rejected<br/>(BlockedError)"]
    S3 --> S4["compile_template (proof)"]
    S4 --> S5["extract_figures + extract_tables"]
    S5 --> S6["model session (read-only)<br/>research overview + figure/table descriptions<br/>retry ×3 on validation failure"]
    S6 --> S7["assemble_materials → environment/materials/"]
    S7 --> S8["compile_ground_truth_pdf"]
    S8 --> S9["build_task_tree + validate_task_tree"]
    S9 --> S10["gate1: source integrity"]
    S10 --> S11["gate2: material sufficiency"]
    S11 --> S12["gate3: task-tree conformance"]
    S12 --> S13["write acceptance request"]
    S13 --> S14["host worker: real Harbor oracle + nop trials"]
    S14 --> S15["oracle = 1.0, nop = 0.0"]
    S15 --> S16["papersmith validate → delivery.json"]
    S16 --> S17["publish (HF upload)"]
```

流程图源文件：`papersmith-workflow.mmd`（含任务树与运行工作区两张图）。

## 架构：确定性控制程序 + 只读模型角色

PaperSmith 不把产品逻辑集中在模型提示词里，而是分层：

| 层 | 负责什么 | 不负责什么 |
| --- | --- | --- |
| `tools/papersmith/` 控制程序 | 下载、解析、LaTeX 手术、编译、哈希、任务树组装、状态转换、验收请求 | 产品人格、自然语言流程提示 |
| 只读模型会话 | 研究概述与图表/表格描述（`materials`）、三道独立审核（`gate1/2/3`） | 写文件、下载、编译、伪造状态 |
| `runtime/` scaffold | 身份、memory policy、knowledge/skills/workflows 的领域描述 | 替代确定性校验器或隐藏失败 |

模型可以理解请求、组织材料、做科学判断；控制程序必须负责下载、解析、复制、哈希、编译和状态转换。工具接口返回结构化结果与证据路径，模型的一句「完成」不算状态。

## 后端与 LLM

后端是 **pi，且只有 pi**（`@earendil-works/pi-coding-agent`）。运行时清单是 `src/papersmith/runtime/package.json`，资源经 pi 自己的加载器（`--skill` 等）进入；ambient discovery 全部关闭。每个模型会话都以 `--no-tools --print --no-session` 运行——「只读」和「不留会话」是结构性保证，不是提示词里的请求。

**实现与 LLM 无关。** provider 与 model 只从运行时进入（`--provider`/`--model` 或 `LLM_PROVIDER`/`LLM_MODEL`），代码里不出现任何具体 provider 或 model 名。换 LLM 只需改运行时参数并重跑一次冒烟，不需要改管线代码。当前选用 `gravarc-router` / `kimi-k3`。

凭据统一由 `accountctl` 注入：

```bash
accountctl docker-run --providers gravarc-router --env-file-only --out <path>
```

注意 `accountctl docker-run` 本身挂不了目录也传不了 docker flag，所以它只用来产出 mode-600 env 文件，容器由本仓库的 runner 拉起。

## 交付任务树

每个交付任务满足 30 个必填路径（`contract.REQUIRED_PATHS`），结构如下（详见 `papersmith-workflow.mmd`）：

```text
tasks/<slug>/
├── task.toml
├── instruction.md
├── environment/
│   ├── Dockerfile
│   ├── materials/
│   │   ├── research_overview.md      # 公开：研究概述
│   │   ├── references.bib            # 公开：固定引用
│   │   ├── template.tex              # 公开：可编译模板
│   │   ├── figure_summary.txt        # 公开：图描述
│   │   ├── table_summary.txt         # 公开：表描述
│   │   ├── table_inventory.json      # 公开：表清单（id/行号/环境/caption/label/sha256）
│   │   ├── AGENTS.md
│   │   ├── figures/  tables/  code/
│   └── texmf/                        # 提取的 .sty/.bst 等
├── solution/
│   ├── solve.sh  normalize.py
│   └── private/  main.tex  main.pdf  config.yaml
└── tests/
    ├── Dockerfile  test.sh  test_state.py  grader_pwb.py
    ├── texmf/
    └── private/  ground_truth.tex  research_overview_long.md
                  source_manifest.json  figure_summary.txt  table_summary.txt
                  ground_truth_sources/
```

公开范围只含 `environment/`、`instruction.md`、`task.toml`；`solution/` 与 `tests/private/` 是私有依据，不进入写作 Agent 上下文（`contract.PUBLIC_ROOTS` / `PRIVATE_MARKERS` 保证公开文件不泄漏私有标记）。

## 验收与交付

三道审核 gate 只作为**记录在案的证据**，不硬阻塞；真实 Harbor 试跑由宿主机受信 worker 执行：

```text
控制容器 → docker/run-acceptance-worker.sh → Harbor oracle/nop 试跑 → 只读 receipt.json
```

- 每道任务必须真实得到 `oracle=1.0`、`nop=0.0`。
- `papersmith validate` 校验 receipt 与请求哈希一致后，组装并写回 `delivery.json`（绑定任务、gate 证据、oracle/nop 回执及指纹）。
- 镜像启动成功、模板编译成功、模型自报通过都不是验收证据。

## 发布

发布目标：HF 数据集 `Jack-Jieke-Wu/Paper-Writing-Exam`，布局 `<config>/<prefix>-NNNN`。上传前 `papersmith validate` 必须返回 valid；`dataset-manifest.jsonl` 追加新条目。发布是显式步骤，`create` 不会自动发布。

用户操作见 [USER.md](USER.md)，实现、测试与发布规则见 [DEV.md](DEV.md)。
