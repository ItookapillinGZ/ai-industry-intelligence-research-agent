# AI Industry Intelligence Research Agent

一个面向求职作品集、可持续演进的 AI 行业情报研究工作流。它追踪 AI Agent、AI Coding、LLM、AIGC 与 AI 产品动态，将分散的信息源转化为可查询的结构化数据和 Markdown 研究报告。

当前仓库只实现 **Phase 1：MVP 基础架构**。它不是 Dashboard，也不是一个仅拼接新闻标题的摘要器；重点是建立清晰、可运行、可测试、方便后续接入更多 Collector 和 LLM/Agent 能力的工程基础。

## MVP Pipeline

```text
Source → Collector → Normalize → Deduplicate → Classify → Score → Summarize → Markdown Report
```

各阶段职责彼此分离：

- **Source**：在 `config/sources.yaml` 中声明 RSS 信息源，不在业务代码中硬编码。
- **Collector**：读取通用 RSS/Atom feed，并映射为统一文章模型。
- **Normalize**：规范 URL、标题、时间、正文和标签。
- **Deduplicate**：先检查规范化 URL 唯一性，再对近期文章做标题相似度匹配。
- **Classify / Score / Summarize**：通过独立协议执行，LLM provider 可替换。
- **Report**：读取已处理文章，按重要度和类别生成 Markdown 报告。

## Architecture

```text
CLI (app/cli.py)
  ├── CollectionPipeline
  │     ├── Collector protocol → RSSCollector
  │     ├── Normalizer
  │     ├── Deduplicator
  │     └── ArticleRepository → SQLite
  ├── ArticleProcessor
  │     ├── Classifier protocol
  │     ├── ImportanceScorer protocol
  │     ├── Summarizer protocol
  │     └── LLMProvider protocol / local fallback
  └── MarkdownReporter
```

主要目录：

```text
app/
  collectors/        # 可扩展外部数据采集接口与 RSS 实现
  storage/           # SQLite 初始化和 Article Repository
  services/          # normalize、deduplicate、pipeline、process、report
  analysis/          # 分类/评分/摘要协议、LLM provider、本地 fallback
  cli.py             # 命令行入口
config/sources.yaml  # RSS 信息源与运行参数
data/                # SQLite 数据库（运行时生成）
reports/             # Markdown 报告（运行时生成）
logs/                # 滚动日志（运行时生成）
tests/               # 单元和集成级基础测试
```

这种划分允许后续新增 API、网页或数据库 Collector，或将任意分析组件换成不同的模型服务，而无需重写采集与存储流程。

## Data Model

SQLite `articles` 表包含：

- `title`
- `url` / `normalized_url`
- `source`
- `author`
- `published_at`
- `collected_at`
- `raw_text`
- `summary`
- `category`
- `importance_score`（0–10）
- `tags`（JSON array）
- `normalized_title`
- `processing_status`
- `llm_provider`
- 创建与更新时间

`normalized_url` 有数据库唯一约束，即使并发或上层检查遗漏，也不会写入重复 URL。

## Requirements and Installation

- Python 3.11+（已在 Python 3.13 上验证）
- 网络连接（仅采集在线 RSS 或调用 LLM 时需要）

PowerShell：

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

macOS/Linux：

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
cp .env.example .env
```

不创建 `.env` 也可以运行。`.gitignore` 已排除 `.env`、数据库、日志和生成的报告。

## Usage

分阶段执行：

```bash
python -m app collect
python -m app process
python -m app report
```

也可以执行完整 MVP：

```bash
python -m app run
```

常用选项：

```bash
python -m app --log-level DEBUG collect
python -m app process --limit 20
python -m app process --retry-failed
python -m app report --limit 50
python -m app --config path/to/sources.yaml collect
```

注意：全局选项 `--config` 和 `--log-level` 放在子命令前。

## Source Configuration

编辑 `config/sources.yaml` 即可新增、停用或标记 RSS 信息源：

```yaml
sources:
  - name: Example AI Lab
    url: https://example.com/feed.xml
    enabled: true
    tags: [Research, Example]
```

单个源失败只会记入日志，不会中止其他源。默认配置是示例起点，生产使用前应根据覆盖范围、稳定性、授权和内容质量进行维护。

## LLM Provider and Graceful Degradation

默认 `AI_INTEL_LLM_PROVIDER=disabled`。此时：

- RSS 采集、存储、URL 去重和标题去重完整运行；
- `process` 使用本地关键词分类、规则评分和抽取式摘要；
- 不需要 API key，也不会因缺少密钥退出。

要使用 OpenAI-compatible Chat Completions API，在本地 `.env` 中设置：

```dotenv
AI_INTEL_LLM_PROVIDER=openai_compatible
AI_INTEL_LLM_API_KEY=your-key-here
AI_INTEL_LLM_MODEL=your-model
AI_INTEL_LLM_BASE_URL=https://api.example.com/v1
```

不要把真实密钥写入 `.env.example` 或提交到 Git。LLM 调用失败时，每个分类、评分或摘要步骤都会分别记录 warning 并回退到本地实现。要接入新的 SDK/provider，只需实现 `app.analysis.interfaces.LLMProvider`；要完全自定义某个研究步骤，则实现 `Classifier`、`ImportanceScorer` 或 `Summarizer`。

## Deduplication

1. URL 规范化会统一 scheme/host、移除 fragment、默认端口、尾部斜杠和常见追踪参数，并排序 query。
2. 若 URL 未命中，会在配置的近期窗口内使用规范化标题做相似度比较。
3. 阈值和回看天数由 YAML 配置：

```yaml
app:
  title_similarity_threshold: 0.92
  dedup_lookback_days: 30
```

阈值越低越容易合并改写标题，也越可能误判；应结合真实数据调优。

## Testing

```bash
python -m pytest
python -m pytest --cov=app --cov-report=term-missing
```

测试覆盖配置解析、URL/标题规范化、两种去重、采集流水线、本地分析和 Markdown 报告。

## Current MVP Boundaries

- RSS 正文质量取决于 feed；当前不抓取文章落地页补全正文。
- 标题相似度使用轻量字符串算法，没有语义向量去重。
- 本地 fallback 是保证工作流可运行的基线，不代表高质量研究判断。
- SQLite 适合单机 MVP；当前没有任务队列、并发采集、调度器或增量迁移框架。
- 报告是 Markdown artifact，没有 Dashboard、搜索 UI 或人工审核界面。
- 信息源列表需要持续维护；站点可能改 URL、反爬或临时不可用。

## Suggested Next Phases

在 Phase 1 数据和指标稳定后，建议按顺序推进：

1. 增加网页正文提取、更多 Collector 和来源健康度监控。
2. 建立 prompt/version、模型输出校验、费用/延迟与人工质量评估。
3. 增加 entity/event extraction、跨来源事件聚类与引用追踪。
4. 引入可调度的增量任务、数据库迁移和观测指标。
5. 最后再基于已验证的数据契约设计检索、审核或 Dashboard。

