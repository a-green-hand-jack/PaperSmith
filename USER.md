# papersmith 用户指南

`papersmith` 是一个面向最终用户的 Agent CLI/TUI 入口。它把一个 Agent
scaffold 的行为定义交给成熟的 coding-agent backend 执行，再由 backend
连接具体的 LLM provider 和 model。

```text
Agent scaffold  ->  coding-agent backend  ->  LLM provider/model
papersmith runtime        OpenCode/Codex/Claude    opencode-go/openai/...
```

用户通常只需要使用 `papersmith`，不需要直接调用 OpenCode、Codex 或 Claude Code。

## 1. 安装

### 方案 A：从已发布 release 安装（推荐，不需要 clone GitHub）

release archive 自带 papersmith 的 runtime definition、launcher 和 installer。
用户只需要下载 release 中的 `install.sh`，再让它下载对应 archive；不需要
clone template 仓库。

当前仓库已经实现了 release 构建和安装逻辑，但截至目前还没有公开发布的
GitHub Release/tag。下面的地址是发布后的固定格式，只有在对应版本真正发布
后才能使用：

```bash
VERSION=0.1.0
INSTALLER_URL="https://raw.githubusercontent.com/a-green-hand-jack/coding-agent-template/v${VERSION}/distribution/install.sh"
RELEASE_URL="https://github.com/a-green-hand-jack/coding-agent-template/releases/download/v${VERSION}/papersmith-${VERSION}.tar.gz"

curl --fail --silent --show-error --location "$INSTALLER_URL" -o /tmp/papersmith-install.sh
RELEASE_URL="$RELEASE_URL" \
AGENT_NAME=papersmith \
AGENT_BACKENDS=opencode,codex,claude \
bash /tmp/papersmith-install.sh
rm -f /tmp/papersmith-install.sh
```

安装完成后：

```bash
export PATH="$HOME/.local/bin:$PATH"
papersmith --version
papersmith --help
```

如果只需要 OpenCode，请在上面的安装命令中把
`AGENT_BACKENDS=opencode,codex,claude` 改成 `AGENT_BACKENDS=opencode`，
这样可以避免下载不使用的 backend。

不要把 API key、auth store 或 `.env` 放入命令、release archive 或 Git。

### 方案 B：从源码安装（仅适合开发者或未发布 release 时）

这个方案需要先取得 template 源码。在仓库根目录执行：

```bash
AGENT_NAME=papersmith \
PREFIX="$HOME/.local" \
AGENT_BACKENDS=opencode,codex,claude \
./distribution/install.sh
```

源码安装需要本机已有 Node.js/npm、Python 3 和 `uv`。它会把 papersmith 的工具
安装到独立的 `~/.local/lib/papersmith/environment/`，不会使用开发仓库的 `.venv`。

### 使用 Docker

```bash
docker build --build-arg AGENT_NAME=papersmith \
  -t papersmith:dev -f docker/Dockerfile .

docker run --rm -it \
  --env-file .env \
  papersmith:dev \
  "完成这个任务"
```

Docker 镜像内置 OpenCode、Codex 和 Claude Code。镜像不包含开发目录、
`AGENTS.md`、`.agents/` 或 provider credentials。

## 2. Agent scaffold、backend 和 LLM

这三层是独立的：

- **Agent scaffold**：一个 Agent 的 Identity、Knowledge、Skills、Memory
  policy 和 Workflows。
- **Backend**：执行 Agent 的成熟 coding-agent，例如 OpenCode、Codex、
  Claude Code。
- **Provider/model**：运行时选择的模型服务和模型名称。

当前一个安装好的命令对应一个 scaffold：`papersmith` 对应 `papersmith` scaffold。要
使用另一个 scaffold，安装时指定它的名称，之后使用对应命令：

```bash
AGENT_NAME=my-agent ./distribution/install.sh
my-agent "运行我的 Agent"
```

当前版本可以在运行时切换 backend 和 provider/model，但还不能用
`papersmith --scaffold another-agent` 在多个 scaffold 之间切换。

## 3. 选择 backend

### OpenCode

```bash
papersmith --backend opencode \
  --provider opencode-go \
  --model glm-5.3 \
  "分析这个项目"
```

OpenCode 使用 `[provider/]model` 命名空间；`--provider` 主要用于 OpenCode。

### Codex

```bash
papersmith --backend codex \
  --model gpt-5.5 \
  "分析这个项目"
```

### Claude Code

```bash
papersmith --backend claude \
  --model sonnet \
  "分析这个项目"
```

Claude Code 使用 `sonnet`、`opus` 等自己的 model alias。

## 4. 配置 provider 和 credentials

credentials 只在运行时提供，不要写入 Git、scaffold、Dockerfile 或镜像。

### OpenCode

```bash
export AGENT_BACKEND=opencode
export LLM_PROVIDER=opencode-go
export LLM_MODEL=glm-5.3
```

使用 API key 时，变量名是 `<PROVIDER>_API_KEY`。例如：

```bash
export OPENAI_API_KEY="..."
export LLM_PROVIDER=openai
export LLM_MODEL=gpt-5.5
papersmith "你好"
```

如果 OpenCode 已通过自己的标准 auth store 登录，运行 papersmith 前设置：

```bash
export AGENT_AUTH_STORE=1
```

### Codex

```bash
export OPENAI_API_KEY="..."
export CODEX_MODEL=gpt-5.5
papersmith --backend codex "你好"
```

也可以使用 Codex 的标准 `CODEX_HOME/auth.json`。使用外部 auth store 时，
设置 `CODEX_AUTH_STORE=1`。

### Claude Code

```bash
export ANTHROPIC_API_KEY="..."
export ANTHROPIC_BASE_URL="https://api.example.com"
papersmith --backend claude --model sonnet "你好"
```

也可以使用 `ANTHROPIC_AUTH_TOKEN`、`ANTHROPIC_API_KEY_FILE` 或 Claude
credentials store。使用 credentials store 时，设置 `CLAUDE_AUTH_STORE=1`。

## 5. CLI 和 TUI

### CLI：一次性任务

带任务参数时，papersmith 使用 backend 的非交互模式：

```bash
papersmith "总结当前目录的代码"
papersmith --backend codex "检查这个错误"
papersmith --backend claude --model sonnet "设计一个修复方案"
```

### TUI：交互式工作

不带任务时，papersmith 默认进入选定 backend 的交互界面：

```bash
papersmith
papersmith --backend codex
papersmith --backend claude
```

也可以显式指定：

```bash
papersmith --tui
papersmith --backend opencode --tui
```

CLI 和 TUI 都使用同一个 scaffold runtime；变化的只是 backend 和
provider/model。

常用环境变量：

```text
AGENT_BACKEND   opencode、codex 或 claude
LLM_PROVIDER    OpenCode provider ID
LLM_MODEL       默认模型
LLM_VARIANT     OpenCode model variant
```

## 6. 安全边界和故障排查

- 不要提交 API key、auth store、session、`.env` 或个人数据。
- 不要把宿主机整个 `HOME` 目录挂入容器。
- Docker 场景只挂载明确指定的 credentials，并使用只读挂载。
- `--provider` 对 Codex/Claude Code 不起作用；它们使用自己的认证和模型命名空间。
- 缺少 provider key 或 auth store 时，papersmith 会拒绝启动。
- `papersmith --version` 和 `papersmith --help` 可用于确认安装是否成功。

开发者验证 Agent 行为请参考 [DEV.md](DEV.md)；最终用户不需要运行开发仓库
中的 benchmark 或发布脚本。
