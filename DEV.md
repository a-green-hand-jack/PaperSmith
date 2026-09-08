# PaperSmith 开发、验证与发布指南

本文描述已实现的领域能力与开发约定。产品行为位于 `src/papersmith/runtime/`；确定性控制程序在 `src/papersmith/runtime/tools/papersmith/`；开发 Agent 的知识、memory 与 skills 位于 `.agents/`，两者不互相复制。三层独立：`src/papersmith/` 是 Agent scaffold，pi 是可替换的执行层，provider/model 在运行时注入。

## 0. 交付物

唯一的产出是**已通过真实 Harbor 验收的 Harbor task**，发布到 HF `Jack-Jieke-Wu/Paper-Writing-Exam`。判定只有 `oracle=1.0` 且 `nop=0.0` 一条。已发布 `lspr-0023`；批量并行产线在建，尚未产出过整批。

## 1. 架构

PaperSmith 用确定性 Python 控制程序实现论文重建管线，模型只以只读会话承担两个角色：

| 角色 | 触发阶段 | 产出 | 校验 |
| --- | --- | --- | --- |
| 材料概述会话 | materials | `research_overview.md` + 图/表描述 | `validate_materials_output`，失败重试 3 次 |
| 独立审核会话 | gate1/2/3 | `ReviewDecision` | 记录为证据，不硬阻塞 |

其余环节（下载、解析、LaTeX 手术、编译、哈希、任务树组装、状态转换、验收请求）全部由控制程序完成，模型无 shell 或 Docker 控制权。

## 2. 后端契约：pi only

后端是 pi，且只有 pi（`@earendil-works/pi-coding-agent`；`@mariozechner/pi-coding-agent` 是已废弃包名）。

- 运行时清单是 `src/papersmith/runtime/package.json`：`keywords` 含 `pi-package`，无 `scripts`，`pi` 段声明资源路径，`agent` 段声明 `manifest_version:1`、`backend:"pi"`、`system_prompt`、`context`、`default_tools`、`capabilities`、`network`、`leaf_tools`、`tool_checks`。runtime 内出现 `opencode.json`/`codex.toml`/`.claude` 会被校验器拒绝。
- `distribution/launcher` 有两个前门：`doctor|create|status|resume|validate` 在任何模型接线之前分发给 `papersmith-cli`（所以 `doctor`/`status` 无需凭据即可用）；其余进入 pi 会话，资源经 pi 自己的加载器进入，ambient discovery 全部关闭。
- 每个模型会话以 `--no-tools --print --no-session` 运行。「只读」和「不留会话」因此是结构性保证，不再依赖提示词里的请求。

`python3 scripts/check-pi-only-backend.py` 守住这条线。开发侧合法提及非 pi 名称的文件需在 `DEVELOPMENT_ALLOWLIST` 里写明理由；该检查同时会报出**不再需要的豁免**，避免清单腐化。

## 3. LLM 无关

kimi 是当前选择，不是实现前提。

- provider/model 只从 `--provider`/`--model` 或 `LLM_PROVIDER`/`LLM_MODEL`/`LLM_REVIEW_MODEL` 进入；`backends.run_phase` 在缺少任一项时**报错而不是回退默认值**。代码里不出现具体 provider 或 model 名。
- 默认值只允许出现在配置层（`.env.example`）且可被覆盖。
- 模型能力按声明门控，不按假设使用。当前 provider 下没有任何 kimi 支持图像输入，所以「表格 VLM 逐单元格解读」只能是可选能力，不能成为管线前提；提示词长度也不得假定某个上下文窗口。
- 输出契约与模型无关：文本输出 + `extract_json` + `validate_materials_output` + 重试，不依赖任何一家的 JSON mode 或 function calling。
- 验收标准：换 provider/model 只改运行时参数并重跑冒烟，不需要改管线代码。

凭据统一经 `accountctl docker-run --providers <account> --env-file-only --out <path>` 产出 mode-600 env 文件。`accountctl docker-run` 传不了 docker flag、挂不了目录，因此不能作为容器入口；容器由本仓库 runner 拉起。pi 的自定义 provider 还需要一个容器化模型目录（拷贝 provider 条目并把 `apiKey` 设成 `$<PROVIDER>_API_KEY`，只含变量引用不含密钥）。

## 4. 模块映射（`tools/papersmith/`）

| 模块 | 职责 |
| --- | --- |
| `cli.py` | `doctor/create/status/resume/validate` 子命令；provider/model 的运行时注入 |
| `config.py` | `RequestSpec`、`DOMAIN_PROFILES`、参数校验、`ConfigError` |
| `state.py` | `run.json`、`events.jsonl`、锁、阶段目录与 manifest |
| `sources.py` | arXiv 解析/下载、安全解包、`BlockedError`、Bohrium PDF 文本 |
| `latex.py` | `find_main_tex`、`probe_reducibility`、`derive_template`、`extract_references`、`extract_figures`、`extract_tables`、`extract_style_files`、`compile_template`、`compile_ground_truth_pdf` |
| `materials.py` | `build_materials_prompt`、`validate_materials_output`、`assemble_materials` |
| `review.py` | `run_gate`、`GATE_CRITERIA` |
| `conversion.py` | `build_task_tree`、`build_source_manifest` |
| `contract.py` | `CANARY_GUID`、`REQUIRED_PATHS`、`PUBLIC_ROOTS`、`PRIVATE_MARKERS`、`render_template`、`validate_task_tree` |
| `acceptance.py` | `build_acceptance_request`、`write_acceptance_request`、`verify_acceptance_receipt` |
| `integrity.py` | `hash_json`、`sha256_file` |
| `backends.py` | pi 发现、`doctor_report`、`run_phase`（隔离 flag 与只读强制）、`extract_json` |
| `pipeline.py` | `run_fixed`、`run_discovery`、`_build_one` 编排 |

## 5. 管线阶段（`pipeline._build_one`）

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

## 6. 任务契约

`contract.REQUIRED_PATHS` 定义 30 个必填路径；`PUBLIC_ROOTS`（`environment/`、`instruction.md`、`task.toml`）划定写作 Agent 可见范围；`PRIVATE_MARKERS` 保证公开文件不泄漏 `ground_truth`、`solution/` 等私有标记。`validate_task_tree` 做结构检查（路径 + 键存在），不比较模板字节。

表格提取（`latex.extract_tables`）从 `main.tex` 确定性解析 `table`/`table*` 环境，产出 `tables/table-NNN.tex` + `table_inventory.json`；`table_summary.txt` 是模型写的描述，`table_inventory.json` 是确定性清单，两者分开。

只保 **LaTeX 重建一种任务契约**。取不到可编译源码的论文一律 reject，不开第二种任务形态。

## 7. 审核 gate 与验收

- `review.py` 的三个 gate 各有一个独立只读模型会话，返回 pass/blocked。它们**记录证据、不硬阻塞**；`acceptance_requested` 恒为 true。
- 真实 Harbor 试跑是权威验收门槛：宿主机 `docker/run-acceptance-worker.sh` 跑 oracle（期望 1.0）与 nop（期望 0.0），只读回执写回 `acceptance/receipt.json`。
- `papersmith validate` 用 `verify_acceptance_receipt` 校验回执与请求一致后，组装 `delivery.json`。
- `tests/Dockerfile` 在 Harbor `separate` verifier 模式下必须 `COPY . /tests/` 自持测试文件；`TEXINPUTS`/`BSTINPUTS` 指向 `/tests/texmf//:`。

## 8. 模板

`templates/` 是任务树的确定性模板源。`render_template` 只替换 `{{key}}`，未知占位符保留可见而非静默丢弃。模板随包安装（`pyproject.toml` 的 `package-data`）。

## 9. 开发与验证

文档或 runtime 定义变更后：

```bash
./scripts/validate-definition.sh papersmith
python3 scripts/check-pi-only-backend.py
python3 .agents/skills/agent-consistency-audit/scripts/audit_agent.py --agent papersmith --strict
python3 .agents/skills/agent-infrastructure-health/scripts/check_infrastructure.py --agent papersmith
git diff --check
```

**镜像构建成功或 CLI 启动不是 Agent E2E 证据**：必须注入真实 provider runtime 并观察真实模型响应。`docker/run-papersmith-e2e.sh` 现在 **fail-closed**——未注入凭据直接拒绝运行，并列出注入选项；`--allow-unauthenticated` 只用于 infra-only 冒烟，且该次运行会被标记为 `infrastructure-only`，不是行为证据。runner 与 `scripts/run-benchmark.sh` 都会在证据行/JSON 记录里写明 `provider` 与 `credential_source`。

任务级验收证据只有一个：真实 Harbor `oracle=1`/`nop=0`。

## 10. 发布

```bash
./scripts/build-release.sh papersmith [version]
```

产品 payload 包含 `src/papersmith/runtime/` 中已审核的 identity、memory policy、knowledge、skills、workflows、tools 与 `package.json`（pi 资源清单，必须随包发布），排除所有 `AGENTS.md`、`.agents/`、凭据、认证存储、原始 session、运行工作区与构建残留（`__pycache__`、`*.egg-info`、`build`）。

任务发布到 HF `Jack-Jieke-Wu/Paper-Writing-Exam` 的 `<config>/<prefix>-NNNN`，并在 `dataset-manifest.jsonl` 追加条目。`create` 完成不会自动发布。

## 11. 已知缺口

| 项 | 状态 |
| --- | --- |
| 增量 `resume` | stub：只校验请求哈希，不复用已有证据。批量场景的首要阻塞项 |
| 运行锁 | `O_CREAT\|O_EXCL` 且只在优雅退出时删除；进程被 kill 后 `.lock` 残留，该 run 再也进不去 |
| `domain_profile()` | 未知 domain 静默退回 `biology`，会默默产出错领域的 task；`DOMAIN_PROFILES` 目前只有 biology/physics |
| 验收 worker 并发 | `HARBOR_JOBS_DIR` 默认固定共享路径且每次 `rm -rf`，并发验收互相清作业目录 |
| 验收 receipt | `exit_status` 硬编码 0，从未真实观测——与「绝不伪造回执」的规则冲突 |
| 发现层 | 仅 arXiv，收录有领域偏好（生化优质期刊基本不在其上）；多平台发现层待接入 |
| 组件层 pi-native | 后端已 pi-only，但编排仍在 Python 侧（agent 循环、会话、provider 调用、人格文本），尚未按 pi 组件契约上移到 skill/extension |
| 表格 VLM 描述 | 需要具备视觉的 provider；当前 provider 下的 kimi 均不支持图像输入 |
