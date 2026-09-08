# PaperSmith 用户指南

## 你最终拿到什么

一批**已通过真实 Harbor 验收**的科研论文写作任务，发布到 HF 数据集 `Jack-Jieke-Wu/Paper-Writing-Exam`。判定标准只有一条：每个任务真实跑出 `oracle=1.0` 且 `nop=0.0`，回执与验收请求哈希一致。除此之外的任何信号——镜像起来了、模板编译过了、模型说完成了——都不算数。

本指南描述当前可用的命令与运行契约。

## 1. PaperSmith 做什么

`papersmith create --selection fixed --paper <arXiv>` 走完整确定性管线：解析请求 → 获取 arXiv 源包 → LaTeX 手术（模板/引用/图/表/样式）→ 只读模型会话写研究概述与图表描述 → 组装材料 → 编译 ground-truth PDF → 组装任务树 → 三道审核 → 写验收请求。真实 Harbor 验收由宿主机受信 worker 执行，`validate` 校验回执后组装 `delivery.json`。

模型只承担两个只读角色：材料概述（含图/表描述，校验失败自动重试 3 次）和三道独立审核。其余下载、解析、编译、哈希、状态转换全部由确定性控制程序完成。

## 2. 后端、LLM 与凭据

后端是 pi，且只有 pi。provider 与 model **只从运行时进入**，实现与 LLM 无关：换模型只改参数，不改代码。

```bash
# 1) 产出 mode-600 env 文件（accountctl 是唯一的凭据注入入口）
accountctl docker-run --providers gravarc-router --env-file-only --out /run/user/$(id -u)/ps.env

# 2) 容器化 pi 模型目录：拷贝 provider 条目并把 apiKey 指向环境变量，绝不写入密钥
python3 - ~/.pi/agent/models.json gravarc-router /tmp/pi-models.json <<'PY'
import json, re, sys
src, provider, dest = sys.argv[1:4]
entry = dict(json.load(open(src))["providers"][provider])
entry["apiKey"] = "$" + re.sub(r"[^A-Za-z0-9]", "_", provider).upper() + "_API_KEY"
json.dump({"providers": {provider: entry}}, open(dest, "w"), indent=2)
PY
```

`accountctl docker-run` 传不了 docker flag、也挂不了目录，所以它只负责产出 env 文件；容器由本仓库的 runner 拉起。

## 3. 检查环境

```bash
papersmith doctor
```

输出 Python 版本、pi 是否可发现、文档工具（pdflatex/pdftotext/docker）以及能力标志。模型可发现性需要 provider 凭据，doctor 不发起付费调用。

## 4. 只解析请求

用 `--describe` 只做确定性请求解析，不创建运行目录、不调用模型：

```bash
papersmith create '基于指定论文制作完整科研论文写作任务' \
  --selection fixed --paper arXiv:2601.02265 \
  --count 1 --output /tmp/run \
  --provider gravarc-router --model kimi-k3 \
  --describe
```

`--provider`/`--model` 省略时从 `LLM_PROVIDER`/`LLM_MODEL` 读取；两者都没有时，需要模型的阶段会明确报错而不是猜一个默认值。

## 5. 正式创建任务

```bash
papersmith create '基于指定论文制作完整科研论文写作任务' \
  --selection fixed --paper arXiv:2601.02265 \
  --count 1 --output /tmp/run \
  --provider gravarc-router --model kimi-k3
```

关键点：

- `--selection fixed` + `--paper <arXiv/DOI/URL>`：论文被判定不可还原（`paper_rejected`）时阻塞，不擅自换题。
- `--selection discovery` + `--domain`：按领域从 arXiv 发现候选并逐个尝试，直到达到 `--count`。当前候选池仍限 arXiv。
- `--count N`：目标最终交付任务数。
- `--output`：必须是空目录或不存在。
- `--source <目录>`：额外授权读取的本地目录（不授权父目录）。

## 6. 查看、恢复与验证

```bash
papersmith status   /tmp/run     # 只读 run.json 与各阶段 manifest 状态
papersmith resume   /tmp/run     # 校验请求快照后重跑（增量复用尚未实现）
papersmith validate /tmp/run     # 校验回执并组装 delivery.json
```

`validate` 在 `acceptance/receipt.json` 存在且与验收请求哈希一致时返回 valid 并写回 `delivery.json`（绑定任务、gate 证据、`oracle`/`nop` 回执与指纹）。

## 7. 运行目录

```text
run.json                 # 当前阶段、状态与请求哈希
events.jsonl             # 只追加事件流
inputs/request.json      # 请求快照
stages/                  # proposal/gate1/materials/gate2/conversion/gate3 各阶段证据
acceptance/              # <slug>-request.json + receipt.json（只读回执）
tasks/<slug>/            # 可交付 Harbor task
delivery.json            # 交付与验收证据索引
```

## 8. 验收

真实 Harbor 试跑在**宿主机**执行，不在控制容器内：

```bash
docker/run-acceptance-worker.sh <acceptance-request.json>
```

该 worker 依次跑 oracle（期望 `reward=1.0`）与 nop（期望 `reward=0.0`），把只读 `receipt.json` 写回运行目录。之后运行 `papersmith validate` 组装 delivery。

批量场景用 `scripts/accept-run.sh <run-dir>` 遍历一个运行目录下所有待验收请求。

## 9. 发布

验收通过且 `validate` 返回 valid 后，将任务树按 `<config>/<prefix>-NNNN` 布局上传到 HF `Jack-Jieke-Wu/Paper-Writing-Exam`，并在 `dataset-manifest.jsonl` 追加条目：

```bash
scripts/publish-run.sh <run-dir> Jack-Jieke-Wu/Paper-Writing-Exam <config-dir> <prefix>
```

发布是显式步骤，`create` 不会自动发布。

## 10. 失败处理

| 现象 | 处理方式 |
| --- | --- |
| `doctor` 报依赖或 pi 不可用 | 修复依赖或安装后重查 |
| 缺 provider/model | 传 `--provider`/`--model` 或设 `LLM_PROVIDER`/`LLM_MODEL`；不会有默认值 |
| 认证、额度或网络中断 | 修复外部服务后重跑 create |
| `paper_rejected`（fixed） | 阅读拒绝原因；换论文需新的明确请求 |
| 材料概述校验失败 | 管线自动重试 3 次；仍失败则阻塞并报告问题 |
| 模板/ground-truth 编译失败 | 修复论文源或样式提取后重跑 |
| oracle/nop 未满足 | 保留回执，修复转换或验收问题后重跑；不得当成功交付 |
| `resume` 报请求快照不一致 | 输入已变，下游证据失效，重新 create |

开发者实现与验证规则见 [DEV.md](DEV.md)，整体架构见 [README.md](README.md)。
