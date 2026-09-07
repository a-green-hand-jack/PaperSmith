# PaperSmith：产品介绍、用户使用与开发发布指南

本文面向使用 PaperSmith 制作科研写作评测任务的用户，以及负责开发、测试和发布 PaperSmith 的维护者。命令示例以 Linux shell 为例；模型标识、论文标识和路径中的占位符需要替换为实际值。


> 这是 PaperSmith 的启动文档。产品定义、用户流程和开发发布规则分别见 [USER.md](USER.md) 与 [DEV.md](DEV.md)。

## 当前仓库状态

当前仓库提供 backend-neutral 的 PaperSmith Agent scaffold，产品运行时位于 `src/papersmith/runtime/`。下文第一阶段定义的是目标领域产品契约；`papersmith create`、`doctor`、`status`、`resume` 和 `validate` 等领域命令需要在后续实现后才可使用，不能把本仓库当前的 launcher 启动成功当成领域功能已完成。

## 当前开发入口

```bash
./scripts/validate-definition.sh papersmith
python3 .agents/skills/agent-consistency-audit/scripts/audit_agent.py --agent papersmith --strict
python3 .agents/skills/agent-infrastructure-health/scripts/check_infrastructure.py --agent papersmith
```

最后一条只检查基础设施。真实产品行为必须在注入实际 provider runtime 后通过 Docker E2E 证明；凭据不得写入仓库或文档。

## 文档导航

- [用户指南](USER.md)：运行环境、模型选择、任务创建、恢复、交付和失败处理。
- [开发指南](DEV.md)：代码边界、静态检查、Docker E2E、验收、版本与发布。

## 第一阶段：介绍 PaperSmith

### 1.1 PaperSmith 是什么

**PaperSmith 是科研论文写作评测任务的自动制作工具，而不是直接替用户完成论文写作的产品。**

用户提供选题要求或指定论文后，PaperSmith 获取真实来源，整理适合写作的研究材料，组织独立审核，生成参考解，并交付可由 Harbor 运行的任务包。用户不需要预先准备领域知识包、标准答案或手工传递审核批准文件。[依据：产品说明][readme]

三者的分工是：

| 组件 | 主要职责 |
| --- | --- |
| PaperSmith | 出题：完成来源获取、材料整理、审核、任务转换和交付 |
| Harbor | 运行任务：提供执行环境，运行 Agent 和提交验证器 |
| 写作 Agent | 答题：读取公开材料，提交符合要求的论文源码 |

默认任务要求写作 Agent 完成一篇完整的科研论文，包括研究问题、背景、方法、结果、解释与局限性，而不是生成摘要或堆砌笔记。摘要任务必须由用户显式选择。任务目标一旦确定，后续生成和审核不得自行缩减范围。[依据：科学任务契约][schema]

### 1.2 输入是什么

| 输入类型 | 用户提供的内容 | 对应作用 |
| --- | --- | --- |
| 自然语言请求 | 研究主题、论文筛选条件、材料要求 | 让系统发现适合制题的论文 |
| 指定论文 | DOI、arXiv 标识或规范论文 URL | 将制题范围限制在明确的论文名单内 |
| 来源与本地材料 | 请求中的来源 URL，或 `--source` 指定的研究文件、目录 | 补充原文、数据、图表、补充材料和来源信息 |
| 任务配置 | 交付数量、输出目录、任务类型、标识策略 | 确定这次运行的任务契约 |
| 模型配置 | 执行模型与审核模型的 `provider/model` 标识 | 指定生成和审核所使用的模型 |

论文选择分为两种模式：`discovery` 自动发现候选，被拒绝的论文可以由新候选补足；`fixed` 仅允许使用 `--paper` 明确指定的论文，被拒绝时阻塞，不擅自换题。仅在自然语言请求中写入 DOI，并不等于锁定论文身份。[依据：命令接口][cli]

用户可以不上传 PDF，但系统必须取得与权威论文元数据相绑定的真实原始 PDF，并检查解析、可读性、标题与标识。原始 TeX 及其依赖只有在实际取得时才能作为原始来源保存；获取不到时，应记录检索和尝试范围，不能用模型生成的 TeX 冒充原始文件。[依据：原始材料获取与验证][ground-truth]

### 1.3 输出是什么

核心输出是一个实际可运行的 **Harbor task 目录**，而不是候选论文列表或一句“任务已完成”。主要结构如下，辅助证据文件省略：

```text
<task-id>/
├── instruction.md                    # 写作题目与提交要求
├── task.toml                         # Harbor 任务配置
├── manifest.json                     # 任务契约和材料指纹
├── environment/
│   ├── Dockerfile                    # 写作环境
│   └── materials/                    # 写作 Agent 可读材料
│       ├── ...                       # 方法、结果、图表、数据、引用等
│       └── template/
│           ├── main.tex              # 可编译的 LaTeX 起始模板
│           └── references.bib
├── tests/
│   ├── test.sh
│   ├── test_state.py                 # 提交验证器
│   └── private/
│       └── ground_truth/
│           ├── paper.pdf             # 真实原始论文
│           └── ...                   # 原文、获取记录与来源证据
└── solution/
    ├── solve.sh                      # 安装并编译参考解
    ├── manuscript/                   # 合成参考论文源码
    └── preview.pdf                   # 合成参考论文预览
```

这三个层次不能混淆：

| 内容 | 用途 | 是否提供给普通写作 Agent |
| --- | --- | --- |
| 公开研究材料 | 支持完成题目要求的写作 | 是，受明确的文件白名单约束 |
| 原始 ground truth | 核对来源真实性及材料、参考解的忠实程度 | 否 |
| 合成 oracle，即参考解 | 验证题目能否按正常提交契约完成 | 否，仅供专门的 oracle 验收使用 |

原始论文是证据依据，合成参考解是基于公开材料重新完成的一份答案，两者不能互相替代。[依据：提交与隔离契约][submission]、[参考解生成][oracle]

运行工作区还会保留 `run.json` 检查点、`events.jsonl` 事件、各阶段的独立尝试目录、会话回执、审核记录和哈希。交付阶段的 `delivery.json` 提供材料、参考解、三道审核及 oracle/nop 验收证据的索引；它属于交付记录，不应假设它就在任务目录根部。[依据：控制与交付逻辑][product]

### 1.4 中间怎么工作

一次 `papersmith create` 串联“四个工作步骤、三个审核关口”：

```text
用户请求
   │
   ▼
proposal ──► gate1 ──► materials ──► gate2 ──► convert ──► gate3 ──► deliver
候选与来源    来源审核    写作材料      材料审核    任务转换     综合审核     交付
```

| 工作步骤 | 核心工作 | 审核重点 |
| --- | --- | --- |
| 第一步：候选与来源 | 发现或解析指定论文，获取原文、元数据及许可依据 | Gate 1：来源是否真实、授权与材料是否适用、是否适合出写作题 |
| 第二步：写作材料 | 整理方法、结果、图表、引用、研究背景和局限性 | Gate 2：与原始论文是否一致，是否足以支撑完整写作 |
| 第三步：任务转换 | 生成题面、环境、验证器和合成参考解 | Gate 3：任务结构、参考解、来源隔离和科学充分性是否合格 |
| 第四步：交付 | 输出通过审核和执行检查的任务，绑定全部证据 | 只有满足交付条件的任务才计入目标数量 |

材料充分性指“足以写论文”，不是要求答题者重新完成整项研究。相关图表、方法、结论与局限需要逐项说明纳入、替代、排除或不可用的处理方式。结构化表格需要保留数值、单位、表注、缺失值及精度信息，而不是只给出概括性描述。[依据：工作流程][workflow]、[材料结构][schema]

转换时，系统先检查公开模板可以编译，再由新的模型会话仅依据公开题面和材料撰写合成参考论文，由控制程序渲染并编译。模板编译成功不等于完成了论文提交；合成参考解也不能复制原始答案。[依据：模板与参考解实现][oracle]

Gate 3 在独立科学审核前，还要求真实运行两类 Harbor 验收：**oracle 得分为 1，nop 得分为 0**。前者检查参考解能够通过正常验证器，后者检查空提交不能误通过。两类任务必须实际执行，不能用模型自报分数代替。[依据：执行验收][acceptance]

### 1.5 模型、控制程序与权限边界

模型承担阅读理解、材料组织、参考稿撰写和科学判断；Python 控制程序承担文件获取、结构验证、任务渲染、编译、检查点和证据绑定。[依据：系统架构][architecture]

模型工具没有任意 shell 执行或文件写入权限。联网发现会话不能读取工作区文件；本地材料处理和审核会话只能读取显式授权的路径，并在工具层禁用联网。公开发现请求可能被发送给联网工具，因此其中不应包含机密研究内容。[依据：模型运行时][runtime]

审核使用新的会话和独立角色；可以复用同一个审核模型，但不能复用构建会话或由构建者批准自己。这里的“独立”是流程与权限上的独立，不代表获得了多个独立科研机构的背书。审核证据需要绑定实际文件、哈希和可检查的位置。[依据：审核完整性验证][integrity]

**结构验证、科学审核、下游写作评测、公开发布是四件不同的事。** 编译和得分检查不能独自证明科学正确；本地任务就绪也不会触发自动上传。[依据：系统架构][architecture]



## 仓库边界

产品运行时只放在 `src/papersmith/runtime/`；开发资源位于 `.agents/`，发布脚本位于 `distribution/`、`docker/` 和 `scripts/`。发布内容排除 `AGENTS.md`、开发资源、凭据、认证存储和原始 provider 会话。
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
