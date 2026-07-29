# 第九阶段：GitHub Actions 持续集成

## 1. 这一步解决什么问题

本地测试通过，只能证明代码在当前电脑和当前环境中可以运行。

持续集成（Continuous Integration，简称 CI）会在代码推送到 GitHub 后，
自动创建一台临时运行环境，重新安装依赖并执行测试。这样可以尽早发现：

- 忘记提交必要文件；
- 项目只能在开发者自己的电脑运行；
- 新修改破坏了已有功能；
- Python 依赖或语法存在问题。

CI 不负责回答用户问题，也不参与 RAG 数据流。它负责检查生产 RAG 功能的代码质量。

## 2. 核心概念

### Workflow

Workflow 是完整的自动化流程。本项目的 Workflow 文件是：

```text
.github/workflows/ci.yml
```

### Event

Event 是触发 Workflow 的事件。本项目监听：

- 向 `main` 分支推送代码；
- 向 `main` 分支创建或更新 Pull Request；
- 在 GitHub 页面手动运行。

### Job

Job 是一组相对独立的任务。本项目有两个 Job：

- `backend-tests`：安装后端依赖并运行 pytest；
- `frontend-check`：安装前端依赖并检查 Python 语法。

没有依赖关系的 Job 可以并行执行，因此后端失败不会阻止前端开始检查。

### Step

Step 是 Job 中按顺序执行的单个步骤，例如拉取代码、安装 Python、安装依赖和运行测试。

### Runner

Runner 是执行 Job 的临时机器。本项目选择 `ubuntu-latest`。

每次运行都会获得一个相对干净的 Linux 环境，任务完成后环境会被销毁。
它不是项目使用的云服务器，也不会长期保存 KnowFlow AI 的数据库和上传文件。

## 3. 本项目的 CI 数据流

```text
本地修改代码
    ↓
git commit
    ↓
git push
    ↓
GitHub 检测到 push 事件
    ↓
启动两个 Ubuntu Runner
    ├── 安装后端依赖 → 运行 pytest
    └── 安装前端依赖 → 执行 compileall
    ↓
在 GitHub 页面显示成功或失败
```

## 4. 为什么 CI 不配置真实 API Key

当前自动化测试会对 Embedding、向量库和聊天模型调用进行 Mock，
验证的是业务流程、输入输出和异常处理，不会请求真实模型服务。

因此 CI 不需要读取本地 `.env`，也不会消耗模型额度。
未来增加必须访问外部服务的集成测试时，应使用 GitHub Secrets 注入密钥，
不能把密钥直接写入 YAML。

## 5. 工作流中的工程设计

- 显式使用 Python 3.12，避免 Runner 默认版本变化导致结果不一致。
- 使用 pip 缓存，减少重复下载依赖的时间。
- 测试数据库、上传目录和 Chroma 目录使用 CI 专用路径。
- 使用 `contents: read` 最小权限，测试任务只能读取仓库代码。
- 设置超时时间，避免异常任务无限等待。
- 同一分支出现新任务时取消旧任务，减少无意义的资源消耗。

## 6. 面试讲解

可以这样介绍：

> 项目使用 GitHub Actions 建立持续集成流程，在主分支推送和 Pull Request
> 场景下自动创建 Linux Runner，安装前后端依赖，执行 pytest 和 Python
> 语法检查。测试过程不依赖真实模型密钥，并通过最小权限、依赖缓存和并发取消
> 提升安全性与执行效率。

常见追问：

1. CI 和部署有什么区别？
2. 为什么本地测试通过还需要 CI？
3. Workflow、Job 和 Step 分别是什么？
4. 为什么不能把 API Key 写进 CI 文件？
5. 为什么选择固定 Python 版本？
