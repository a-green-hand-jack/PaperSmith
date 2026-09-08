# PaperSmith 用户指南

PaperSmith 把用户请求和真实论文来源转换为可交付的 Harbor 科研写作任务（论文重建格式）。本指南描述当前可用的命令与运行契约。

## 1. PaperSmith 做什么

`papersmith create --selection fixed --paper <arXiv>` 走完整确定性管线：解析请求 → 获取 arXiv 源包 → LaTeX 手术（模板/引用/图/表/样式）→ 只读模型会话写研究概述与图表描述 → 组装材料 → 编译 ground-truth PDF → 组装任务树 → 三道审核 → 写验收请求。真实 Harbor 验收由宿主机受信 worker 执行，`validate` 校验回执后组装 `delivery.json`。

模型只承担两个只读角色：材料概述（含图/表描述，校验失败自动重试 3 次）和三道独立审核。其余下载、解析、编译、哈希、状态转换全部由确定性控制程序完成。

## 2. 检查环境

```bash
papersmith doctor
```

输出 Python 版本、可发现的 backend 二进制（opencode/codex/claude/pi）、文档工具（pdflatex/pdftotext/docker）以及能力标志。模型可发现性需要 provider 凭据，doctor 不发起付费调用。

## 3. 只解析请求

用 `--describe` 只做确定性请求解析，不创建运行目录、不调用模型：

```bash
papersmith create '基于指定论文制作完整科研论文写作任务' \
  --selection fixed --paper arXiv:2601.02265 \
  --count 1 --output /tmp/run \
  --backend opencode --provider opencode-go \
  --model deepseek-v4-flash --review-model deepseek-v4-flash \
  --describe
```

## 4. 正式创建任务

```bash
papersmith create '基于指定论文制作完整科研论文写作任务' \
  --selection fixed --paper arXiv:2601.02265 \
  --count 1 --output /tmp/run \
  --backend opencode --provider opencode-go \
  --model deepseek-v4-flash --review-model deepseek-v4-flash
```

关键点：

- `--selection fixed` + `--paper <arXiv/DOI/URL>`：当前唯一完整实现的选择模式；论文被判定不可还原（`paper_rejected`）时阻塞，不擅自换题。
- `--selection discovery`：尚未接入新管线，会返回错误提示改用 fixed。
- `--count 1`：目标最终交付任务数。
- `--output`：必须是空目录或不存在；已有非空目录需用 `resume`。
- `--source <目录>`：额外授权读取的本地目录（不授权父目录）。

## 5. 查看、恢复与验证

```bash
papersmith status   /tmp/run     # 只读 run.json 与各阶段 manifest 状态
papersmith resume   /tmp/run     # 校验请求快照后重跑 run_fixed（增量复用尚未实现）
papersmith validate /tmp/run     # 校验回执并组装 delivery.json
```

`validate` 在 `acceptance/receipt.json` 存在且与验收请求哈希一致时返回 valid 并写回 `delivery.json`（绑定任务、gate 证据、`oracle`/`nop` 回执与指纹）。

## 6. 运行目录

```text
run.json                 # 当前阶段、状态与请求哈希
events.jsonl             # 只追加事件流
inputs/request.json      # 请求快照
stages/                  # proposal/gate1/materials/gate2/conversion/gate3 各阶段证据
acceptance/              # <slug>-request.json + receipt.json（只读回执）
tasks/<slug>/            # 可交付 Harbor task
delivery.json            # 交付与验收证据索引
```

## 7. 验收

真实 Harbor 试跑在**宿主机**执行，不在控制容器内：

```bash
docker/run-acceptance-worker.sh <acceptance-request.json>
```

该 worker 依次跑 oracle（期望 `reward=1.0`）与 nop（期望 `reward=0.0`）试跑，把只读 `receipt.json` 写回运行目录。之后运行 `papersmith validate` 组装 delivery。镜像启动或编译成功不等于验收通过。

## 8. 发布

验收通过且 `validate` 返回 valid 后，将任务树按 `lifesci-paperrecon-short/lspr-NNNN` 布局上传到 HF `Jack-Jieke-Wu/Paper-Writing-Exam`，并在 `dataset-manifest.jsonl` 追加条目。发布是显式步骤，`create` 不会自动发布。

## 9. 失败处理

| 现象 | 处理方式 |
| --- | --- |
| `doctor` 报依赖或 backend 不可用 | 修复依赖或模型配置后重查 |
| 认证、额度或网络中断 | 修复外部服务后重跑 create |
| `paper_rejected`（fixed） | 阅读拒绝原因；换论文需新的明确请求 |
| 材料概述校验失败 | 管线自动重试 3 次；仍失败则阻塞并报告问题 |
| 模板/ground-truth 编译失败 | 修复论文源或样式提取后重跑 |
| oracle/nop 未满足 | 保留回执，修复转换或验收问题后重跑；不得当成功交付 |
| `resume` 报请求快照不一致 | 输入已变，下游证据失效，重新 create |

开发者实现与验证规则见 [DEV.md](DEV.md)，整体架构见 [README.md](README.md)。
