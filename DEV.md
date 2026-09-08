# PaperSmith 开发、验证与发布指南

本文描述已实现的领域能力与开发约定。产品行为位于 `src/papersmith/runtime/`；确定性控制程序在 `src/papersmith/runtime/tools/papersmith/`；开发 Agent 的知识、memory 与 skills 位于 `.agents/`，两者不互相复制。三层独立：`src/papersmith/` 是 Agent scaffold，backend（当前 OpenCode）是可替换执行层，provider/model 在运行时注入。

## 1. 架构

PaperSmith 用确定性 Python 控制程序实现论文重建管线，模型只以只读会话承担两个角色：

| 角色 | 触发阶段 | 产出 | 校验 |
| --- | --- | --- | --- |
| 材料概述会话 | materials | `research_overview.md` + 图/表描述 | `validate_materials_output`，失败重试 3 次 |
| 独立审核会话 | gate1/2/3 | `ReviewDecision` | 记录为证据，不硬阻塞 |

其余环节（下载、解析、LaTeX 手术、编译、哈希、任务树组装、状态转换、验收请求）全部由控制程序完成，模型无 shell 或 Docker 控制权。

## 2. 模块映射（`tools/papersmith/`）

| 模块 | 职责 |
| --- | --- |
| `cli.py` | `doctor/create/status/resume/validate` 子命令 |
| `config.py` | `RequestSpec`、参数校验、`ConfigError` |
| `state.py` | `run.json`、`events.jsonl`、锁、阶段目录与 manifest |
| `sources.py` | arXiv 解析/下载、安全解包、`BlockedError`、Bohrium PDF 文本 |
| `latex.py` | `find_main_tex`、`probe_reducibility`、`derive_template`、`extract_references`、`extract_figures`、`extract_tables`、`extract_style_files`、`compile_template`、`compile_ground_truth_pdf` |
| `materials.py` | `build_materials_prompt`、`validate_materials_output`、`assemble_materials` |
| `review.py` | `run_gate`、`GATE_CRITERIA` |
| `conversion.py` | `build_task_tree`、`build_source_manifest` |
| `contract.py` | `CANARY_GUID`、`REQUIRED_PATHS`、`PUBLIC_ROOTS`、`PRIVATE_MARKERS`、`render_template`、`validate_task_tree` |
| `acceptance.py` | `build_acceptance_request`、`write_acceptance_request`、`verify_acceptance_receipt` |
| `integrity.py` | `hash_json`、`sha256_file` |
| `backends.py` | backend 发现、`doctor_report`、`run_phase`、`extract_json` |
| `pipeline.py` | `run_fixed`、`_build_one` 编排 |

## 3. 管线阶段（`pipeline._build_one`）

```text
1. resolve_identifier + fetch_arxiv_source         # 元数据 + 源包 + sha256
2. find_main_tex + probe_reducibility              # 不可还原 → BlockedError
3. derive_template + extract_references
   + extract_style_files + compile_template        # 模板必须编译通过
4. extract_figures + extract_tables                # 图复制 + table/table* 环境提取
5. 只读模型会话：overview + 图/表描述              # 校验失败重试 3 次
6. assemble_materials → environment/materials/     # 含 table_inventory.json（确定性）
7. compile_ground_truth_pdf                        # 在源目录副本里编译
8. build_task_tree + validate_task_tree            # 30 必填路径 + 公开泄漏扫描
9. run_gate ×3（gate1/2/3）                        # 记录证据，不硬阻塞
10. write_acceptance_request                       # 恒写；真实 Harbor 是权威门槛
```

每次运行写 `events.jsonl`（只追加）与各阶段 manifest；`source_fetched`、`template_derived`、`materials_retry`、`task_converted`、`<gate>_review`、`acceptance_requested` 等事件记录了证据链。

## 4. 任务契约

`contract.REQUIRED_PATHS` 定义 30 个必填路径；`PUBLIC_ROOTS`（`environment/`、`instruction.md`、`task.toml`）划定写作 Agent 可见范围；`PRIVATE_MARKERS` 保证公开文件不泄漏 `ground_truth`、`solution/` 等私有标记。`validate_task_tree` 做结构检查（路径 + 键存在），不比较模板字节。

表格提取（`latex.extract_tables`）从 `main.tex` 确定性解析 `table`/`table*` 环境，产出 `tables/table-NNN.tex` + `table_inventory.json`（id/行号/environment/caption/label/content_sha256/public_path）；`table_summary.txt` 是模型写的描述，`table_inventory.json` 是确定性清单，两者分开。

## 5. 审核 gate 与验收

- `review.py` 的三个 gate 各有一个独立只读模型会话，返回 pass/blocked。它们**记录证据、不硬阻塞**；`acceptance_requested` 恒为 true。
- 真实 Harbor 试跑是权威验收门槛：宿主机 `docker/run-acceptance-worker.sh` 跑 oracle（期望 1.0）与 nop（期望 0.0），只读回执写回 `acceptance/receipt.json`。
- `papersmith validate` 用 `verify_acceptance_receipt` 校验回执与请求一致后，组装 `delivery.json`（`oracle_reward`/`nop_reward`/`receipt_fingerprint`/`delivery_hash`）。
- `tests/Dockerfile` 在 Harbor `separate` verifier 模式下必须 `COPY . /tests/` 自持测试文件；`TEXINPUTS`/`BSTINPUTS` 指向 `/tests/texmf//:`。

## 6. 模板

`templates/` 是任务树的确定性模板源：`task.toml.j2`、`instruction.md.j2`、`environment.Dockerfile`、`solve.sh.j2`、`normalize.py`、`test.sh`、`test_state.py`、`grader_pwb.py`、`tests.Dockerfile`、`AGENTS.md.j2`。`render_template` 只替换 `{{key}}`，未知占位符保留可见而非静默丢弃。模板随包安装（`pyproject.toml` 的 `package-data`）。

## 7. 开发与验证

文档或 runtime 定义变更后，在仓库根目录运行：

```bash
./scripts/validate-definition.sh papersmith
python3 .agents/skills/agent-consistency-audit/scripts/audit_agent.py \
  --agent papersmith --strict
python3 .agents/skills/agent-infrastructure-health/scripts/check_infrastructure.py \
  --agent papersmith
git diff --check
```

definition 和 consistency 检查验证结构、frontmatter、配置与发布边界；infrastructure 检查验证 installer、launcher、Docker。**镜像构建成功或 CLI 启动不是 Agent E2E 证据**：必须注入真实 provider runtime，观察真实模型响应，并以真实 Harbor `oracle=1`/`nop=0` 作为任务验收证据。未注入凭据的运行只能报告为 infrastructure-only。

## 8. 发布

```bash
./scripts/build-release.sh papersmith [version]
```

产品 payload 包含 `src/papersmith/runtime/` 中已审核的 identity、memory policy、knowledge、skills、workflows 与 tools，排除所有 `AGENTS.md`、`.agents/`、凭据、认证存储、原始 session 与运行工作区。

任务发布到 HF `Jack-Jieke-Wu/Paper-Writing-Exam` 的 `lifesci-paperrecon-short/lspr-NNNN`，并在 `dataset-manifest.jsonl` 追加条目。`create` 完成不会自动发布；发布需显式授权并在 `validate` 返回 valid 后进行。

## 9. 已知缺口

| 项 | 状态 |
| --- | --- |
| `--selection discovery` | 未接入新管线（`cli.cmd_create` 返回错误提示） |
| 增量 `resume` | stub：只校验请求哈希后重跑 `run_fixed` |
| backend | 仅 OpenCode 通过 `run_phase` 接线；codex/claude/pi 仅被 `discover_backends` 发现 |
| 表格 VLM 描述 | `table_summary.txt` 由模型描述生成，可增强为逐单元格解读 |
| 论文内嵌 `tabular` 之外的表格源（CSV/补充材料） | 当前不抽取 |
