# PaperSmith 开发、测试与发布指南

本文把启动指南中的维护者流程整理为开发约定。当前仓库是 backend-neutral scaffold；领域流水线尚未全部实现，因此必须区分“当前 scaffold 结构检查”和“未来 PaperSmith 任务流水线的真实验收”。

## 当前仓库的最小检查

在仓库根目录运行：

```bash
./scripts/validate-definition.sh papersmith
python3 .agents/skills/agent-consistency-audit/scripts/audit_agent.py --agent papersmith --strict
python3 .agents/skills/agent-infrastructure-health/scripts/check_infrastructure.py --agent papersmith
```

需要构建发布归档时运行 `./scripts/build-release.sh papersmith [version]`；需要运行当前 Agent 的容器 E2E 时使用 `./docker/run-papersmith-e2e.sh --help`，并按实际 backend 显式注入 provider 认证。检查脚本通过或镜像构建成功，都不等于领域任务功能验收通过。

## 当前 scaffold 与目标流水线的对应关系

| 启动指南中的目标职责 | 当前仓库位置 |
| --- | --- |
| Agent identity、权限和边界 | `src/papersmith/runtime/identity.md`、`memory-policy.md`、`knowledge/` |
| 工作流与技能 | `src/papersmith/runtime/workflows/`、`skills/` |
| Agent 声明与 OpenCode 配置 | `src/papersmith/agent.yaml`、`src/papersmith/runtime/opencode.json` |
| 安装、发布和容器入口 | `distribution/`、`docker/`、`scripts/` |

来源获取、材料整理、三道审核、任务转换、oracle/nop 和 `papersmith create` 等目标能力应在上述边界内逐步实现；不要把它们放进平行的自定义运行时或硬编码凭据。

## 第三阶段：开发人员怎么测试、开发和发布 PaperSmith

以下小节保留启动指南定义的目标职责与验收标准；其中引用的 `paperbench_harbor` 模块路径和 `make`/`docker/e2e.sh` 命令属于目标实现接口，当前 scaffold 尚未提供。实现时应将它们映射到本仓库的 `src/papersmith/`、`scripts/` 和 `docker/run-papersmith-e2e.sh`，并同步更新本文件。

### 3.1 先确定代码职责与修改边界

| 模块或路径 | 开发职责 |
| --- | --- |
| `src/paperbench_harbor/papersmith/cli.py` | 公共命令、参数、JSON 输出和依赖检查 |
| `schema.py` | 科学任务契约、材料结构、写作要求与审核结论 |
| `product.py` | 流程编排、修复、检查点、转换和交付 |
| `runtime.py` | OpenCode 会话、模型读取与联网权限、事件回执 |
| `ground_truth.py` | 原始 PDF、TeX 可用性与来源验证 |
| `oracle.py` | 公开模板、合成论文渲染及编译 |
| `integrity.py` / `acceptance.py` | 证据完整性与真实 Harbor 验收 |
| `src/paperbench_harbor/common/` | 共享模板与提交契约 |
| `src/paperbench_harbor/distribution/` | 独立的数据发布、审计和导出操作 |
| `install.sh` / `docker/e2e.sh` | 安装产品与已安装产品的 Docker 验证入口 |

开发时优先判断问题属于来源、模型输出、材料、转换、编译还是验收，避免把所有错误都退回重新选题。模型输出应交给结构与证据验证器检查，不应依靠提示词承诺替代程序验证。[依据：架构][architecture]、[流程实现][product]

修改共享模板和验证器时，必须维护既有 benchmark 的语义、提交路径和答案隔离。科研文件和生成的 LaTeX 均按不可信输入处理，不通过开放 shell 权限、放宽白名单或关闭检查来提高通过率。[依据：贡献规范][contributing]

### 3.2 准备开发环境并做静态检查

以下命令在仓库根目录执行，要求 `python3` 指向 Python 3.12 或更高版本。宿主机还需要可用的 Docker，Docker 工作流应以普通用户运行，不使用 root 或 `sudo` 启动运行封装。

```bash
python3 -m venv .venv
.venv/bin/python -m pip install '.[dev]' uv
export PATH="$PWD/.venv/bin:$PATH"
export PAPERSMITH_HOST_PYTHON="$PWD/.venv/bin/python"

make lint
```

这里安装了宿主机所需的 Harbor 依赖、开发检查工具和 Docker 封装所需的 `uv`。需要调整格式时使用 `make format`，之后重新运行 `make lint` 并检查差异。[依据：依赖声明][pyproject]、[Makefile][makefile]、[运行封装][e2e]

每次独立验收使用新的镜像标签和运行卷。下面的设置只在新建验收时生成一次，恢复时应沿用原值：

```bash
RUN_ID="dev-$(date +%Y%m%d-%H%M%S)"
export PAPERSMITH_IMAGE="paperbench-papersmith:$RUN_ID"
export PAPERSMITH_VOLUME_PREFIX="papersmith-$RUN_ID"
export PAPERSMITH_ACCEPTANCE_STATE="$HOME/.local/state/papersmith/acceptance/$RUN_ID"

sh docker/e2e.sh build
sh docker/e2e.sh exec papersmith --version
sh docker/e2e.sh exec papersmith identity --json
```

该镜像通过正式安装器安装 wheel，运行时不挂载源码 checkout，也不使用 `PYTHONPATH`。修改源码后必须重新构建镜像，不能用旧镜像的结果证明新代码有效。[依据：Docker 构建定义][dockerfile]、[已安装产品工作流][docker-workflow]

在不调用模型的情况下检查命令和请求形状：

```bash
PAPERSMITH_NETWORK=none sh docker/e2e.sh run \
  '寻找适合完整科研论文写作任务的论文' \
  --count 1 \
  --output /runs/request-check \
  --describe --headless --json
```

这个检查只证明安装后的命令可以解析请求，不证明论文获取、材料生成或三道审核能够完成。[依据：开发验证规则][dev]

### 3.3 配置模型访问，再运行真实端到端测试

Docker 默认不挂载凭据。先准备仅包含所需模型服务的配置文件，再明确指定最小访问范围：

```bash
# 替换为已准备好的实际文件；配置文件本身不包含秘密。
export PAPERSMITH_OPENCODE_CONFIG='/绝对路径/opencode.json'

# 仅在所选服务需要该认证文件时设置。
export PAPERSMITH_OPENCODE_AUTH='/绝对路径/opencode-auth.json'

EXEC_MODEL='provider/execution-model'
REVIEW_MODEL='provider/review-model'

sh docker/e2e.sh doctor \
  --model "$EXEC_MODEL" \
  --review-model "$REVIEW_MODEL" \
  --headless --json
```

外部服务适配器需要额外模块或凭据时，通过 `PAPERSMITH_READONLY_PATHS` 逐项指定。不要挂载宿主机整个 home、整个配置目录或 Docker socket，也不要输出认证文件内容。需要本地科研材料时，使用 `PAPERSMITH_INPUT` 挂载限定目录，并在创建参数中使用 `--source /input`。[依据：受限挂载实现][e2e]

获得真实模型调用授权后，先构建一道任务：

```bash
sh docker/e2e.sh run \
  '寻找来源可核验、材料充分、适合完整科研论文写作任务的论文' \
  --count 1 \
  --output /runs/acceptance \
  --model "$EXEC_MODEL" \
  --review-model "$REVIEW_MODEL" \
  --headless --json

sh docker/e2e.sh validate /runs/acceptance --json
```

人工检查首个交付任务的题面、公开材料、原始来源、参考稿与验收索引，确认任务目标没有被缩减，再显式扩展同一次运行：

```bash
sh docker/e2e.sh resume /runs/acceptance \
  --count 5 --headless --json

sh docker/e2e.sh validate /runs/acceptance --json
```

`run` 和 `resume` 会协调宿主机上安装后的验收工作进程。容器负责制题，受信任宿主机负责调用 Harbor 运行 oracle/nop，验收回执以只读方式提供给控制容器；不需要把 Docker 控制权限交给模型容器。[依据：验收工作进程][acceptance]

### 3.4 端到端验收要检查什么

| 验收维度 | 检查目标 |
| --- | --- |
| 真实来源 | 原始 PDF 可核验，身份、来源与许可依据绑定到实际材料 |
| 材料完整性 | 方法、结果、图表、引用和局限有明确覆盖及来源依据 |
| 独立审核 | 每道题有三道接受结论及真实的独立会话证据 |
| 参考解可用性 | 合成论文只使用公开输入，源码完整，可通过正常提交验证 |
| 正反执行测试 | 每道题实际 oracle=1、nop=0，且不是基础设施异常导致的结果 |
| 数量与去重 | 返回目标数量的不同论文任务，不靠重复身份凑数 |
| 证据完整性 | 当前文件、实现、回执和哈希一致 |
| 可恢复性 | 未改变的已通过阶段可复用，中断阶段可以继续 |

五道题意味着需要检查十五道审核结论和十次 oracle/nop 运行，但“计数齐全”本身仍不够，还必须检查其结果、身份和证据绑定。[依据：审核与会话验证][integrity]、[执行验收][acceptance]

中断恢复测试应在至少一道审核通过后进行：记录检查点，在前台按 `Ctrl-C` 中断，再使用相同镜像、工作卷、宿主机验收目录和原输出路径执行 `resume`。检查事件中的 `checkpoint_reused`，确认系统复用未变的已通过阶段，而不是从头重做。[依据：恢复验收方法][dev]

源码或输入发生变化后，不应要求系统沿用不再有效的批准。此时应重新运行受影响阶段；验证“原样恢复”时则必须保持镜像和输入不变。不要手工修改 `run.json`、审核文件或哈希来制造成功。[依据：依赖与完整性绑定][integrity]

建议把以下场景加入真实工作流回归：自动发现与固定论文的差异、目标数量扩展、来源获取失败、认证中断、材料修复、编译失败后的恢复，以及越权读取和答案泄漏的拒绝行为。这些是回归检查方向，不意味着需要新建仓库级伪任务测试套件。

### 3.5 日常开发与持续集成

推荐开发循环如下：

```text
定位问题与受影响契约
        ↓
修改实现、结构定义或模板
        ↓
make lint 与 wheel 构建
        ↓
重建 Docker 镜像并检查安装后的命令
        ↓
对相关真实场景执行创建、恢复、验证
        ↓
整理证据并提交评审
```

仓库的持续集成负责静态检查和 wheel 构建，并检查根目录 `tests/`、`scripts/`、`.opencode/agent` 不被重新引入。CI 中的开发依赖安装不替代 Docker 中的已安装产品验收；生成任务中的 `tests/` 是 benchmark 验证器，必须保留，两者不是同一套测试。[依据：持续集成配置][ci]、[贡献规范][contributing]

提交评审时，说明改动影响了哪些阶段、契约与证据；区分实际完成的静态检查、模型运行和 Harbor 验收。保留失败记录及修复依据，不把 `doctor`、请求预览、镜像构建或单纯进程退出成功描述成完整任务验收。

源码仓库不保存生成的论文数据集、原始论文、密钥、模型凭据、评测轨迹或完整运行工作区。敏感诊断在私有证据位置排查；对外分享前审查并脱敏。[依据：贡献规范][contributing]

### 3.6 发布 PaperSmith 工具版本

**工具发布与任务发布分开进行。** 本节是维护者发布软件包的操作流程，发布位置及权限由维护者确定。

#### 确定版本与候选提交

修改版本时，同步检查 `pyproject.toml` 中的包版本，以及 `cli.py` 中 `--version` 和 `identity` 输出使用的版本值，避免安装包元数据与命令显示不一致。验收身份还包括安装内容指纹，不能只依靠一个版本号判断实现是否相同。[依据：包元数据][pyproject]、[版本命令][cli]、[验收身份][acceptance]

建议在候选提交中一并更新用户参数说明、开发验证步骤与兼容性注意事项。使用明确的完整 Git 提交标识记录发布源，不用浮动分支名替代不可变版本。

#### 构建独立 wheel 并检查安装

在确定的源码提交上构建 wheel，将构建产物放到仓库之外：

```bash
RELEASE_DIR="$(mktemp -d "${TMPDIR:-/tmp}/papersmith-release.XXXXXX")"

make lint
.venv/bin/python -m pip wheel --no-deps . --wheel-dir "$RELEASE_DIR"
sha256sum "$RELEASE_DIR"/*.whl

# 新目录中应只有一个产品 wheel。
set -- "$RELEASE_DIR"/*.whl
[ "$#" -eq 1 ] && [ -f "$1" ] || exit 1
WHEEL="$1"

PAPERSMITH_SOURCE="$WHEEL" \
PAPERSMITH_PREFIX="$RELEASE_DIR/install" \
PAPERSMITH_BIN_DIR="$RELEASE_DIR/bin" \
  sh install.sh

# 从源码仓库之外验证安装后的命令。
(
  cd "$RELEASE_DIR"
  "$RELEASE_DIR/bin/papersmith" --version
  "$RELEASE_DIR/bin/papersmith" identity --json
)
```

该步骤检查 wheel 可以独立安装和启动。完整发布候选还需通过前述 Docker 真实任务与恢复验收，并核对最终 wheel 的安装内容身份与验收对象一致；不要在验收之后修改代码，再把原有结果用于新包。[依据：安装器][installer]、[构建配置][dockerfile]

#### 记录并分发发布产物

建议为发布保存一份记录，包含完整 Git 提交、包版本、wheel SHA-256、安装内容身份、验收协议、Docker 镜像 ID、静态检查结果和真实验收证据的位置。再为该提交建立版本标签，将 wheel 和校验值发布到项目选定的制品位置。

通过远程安装器分发时，安装器与源码必须固定到同一个完整提交：

```bash
COMMIT='<替换为可信的完整 40 位小写提交 SHA>'

curl -fsSL \
  "https://raw.githubusercontent.com/a-green-hand-jack/paperbench-harbor/$COMMIT/install.sh" \
  | PAPERSMITH_REF="$COMMIT" sh
```

只有经过审核的可信提交才应使用这种安装方式。升级前结束占用同一安装环境的运行；恢复或重现旧任务时保留原始实现与证据，不将旧记录改写成新版本已通过。[依据：安装来源与环境锁][installer]

### 3.7 发布任务、来源档案和评测记录

PaperSmith 本地交付的工作区不是可以整体公开的发布包。正式发布时，需要再次检查资产授权、署名、私有文件边界、版本绑定和目标数据集的发布规则。[依据：任务版本规则][versioning]、[来源档案边界][source-archive]

| 发布对象 | 包含什么 | 与其他对象的关系 |
| --- | --- | --- |
| 工具版本 | PaperSmith 源码、wheel 和安装信息 | 记录构建与验收所用实现 |
| 可运行任务数据集 | 审核后的 Harbor task | 绑定不可变任务版本与生成来源 |
| 来源档案 | 可合法保留或分发的构建来源、任务与论文映射、文件清单 | 独立版本，不因档案更新改变任务字节 |
| 评测记录数据集 | 脱敏后的下游运行记录与结果 | 绑定实际使用的任务、Agent 和模型版本 |

任务、来源档案和评测记录应分别版本化。发布记录保存不可变 revision 和对应关系；无法合法再分发的来源只保留允许公开的定位与说明，不因归档而获得额外分发权。[依据：数据版本管理][versioning]、[来源档案][source-archive]

仓库把相关操作放在独立的 `paperbench-distribute` 接口下。先查看适用命令的参数，不把 benchmark 专用发布流程当作任意 PaperSmith 任务都能直接使用的通用上传器：

```bash
paperbench-distribute --help
paperbench-distribute audit-fidelity --help
paperbench-distribute verify-release-provenance --help
paperbench-distribute build-source-archive --help
paperbench-distribute export-trial --help
```

按目标流程启用 `pyproject.toml` 声明的相应可选依赖，再针对明确的发布树、来源和版本执行操作。既有 benchmark 的额外发布门槛只适用于相应数据集，不应被隐式加入普通本地制题请求。[依据：分发命令][distribution]、[依赖定义][pyproject]

评测记录导出时，排除密钥、任务参考解、私有验证材料和原始 ground truth。检查脱敏结果后再单独上传，并记录返回的不可变评测版本；不能直接上传 `run.json` 所在的整个工作区。[依据：评测记录导出边界][trials]

### 3.8 发布前的最终检查

| 检查范围 | 发布条件 |
| --- | --- |
| 安装与接口 | 最终 wheel 可独立安装，参数和版本信息一致 |
| 真实功能 | 任务构建、三道审核、oracle/nop 与恢复测试有对应证据 |
| 实现一致性 | Git 提交、安装内容身份、镜像与验收对象相匹配 |
| 科学与来源 | 原始依据、材料覆盖、参考解和资产署名可追溯 |
| 安全与隔离 | 公开包不包含凭据；普通写作环境不包含私有答案 |
| 分发与版本 | 明确区分软件、任务、来源档案及评测记录，并固定对应版本 |

维护工作的闭环是：**修改实现 → 安装产品 → 验证真实任务 → 保留证据 → 明确发布边界 → 分发不可变版本。**

<!-- 参考链接按文中首次使用的主题组织，保留为普通 Markdown 链接，便于脱离聊天窗口阅读。 -->
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
