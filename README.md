# AI Industry Intelligence Research Agent

一个面向求职作品集、可持续演进的 AI 行业情报研究工作流。它持续追踪 AI Agent、AI Coding、LLM、AIGC 与 AI 产品动态，把分散文章转化为结构化事件、证据约束的 ResearchBrief 和 Markdown 情报报告。

当前仓库完成 **Phase 2：Research Workflow**。它没有 Dashboard，也没有为了“Agent”标签引入 LangChain、LangGraph、Vector DB、Redis、Celery 或微服务。

## Pipeline

```text
Source
  → Collector
  → Normalize
  → Deduplicate
  → Full Text Extraction
  → Classify / Score
  → Event Grouping
  → Top-K Event Selection
  → Research Agent
  → ResearchBrief
  → Markdown Intelligence Report
```

Phase 1 的 article-level pipeline 与报告仍然保留，可以独立使用。

## Architecture

```text
CLI
 ├── CollectionPipeline
 │    ├── Collector protocol → RSSCollector
 │    ├── Normalizer / URL + title deduplication
 │    └── ArticleRepository → SQLite
 ├── ContentExtractionService
 │    └── ContentExtractor protocol → TrafilaturaContentExtractor
 ├── ArticleProcessor
 │    ├── Classifier protocol
 │    ├── ImportanceScorer protocol
 │    └── Summarizer protocol
 ├── EventGroupingService
 │    └── EventGrouper protocol → conservative deterministic grouping
 ├── EventRankingService
 │    └── EventScorer protocol → source diversity + recency + article score
 ├── ResearchService
 │    └── ResearchAgent protocol
 │         ├── structured LLM implementation
 │         └── deterministic no-key fallback
 ├── ResearchReportGenerator
 └── EvaluationService / EvaluationReportGenerator
```

主要目录：

```text
app/
  collectors/      # RSS/Atom 和未来外部数据源接口
  content/         # HTTP fetch、正文提取接口与 Trafilatura 实现
  analysis/        # article 分类、评分、摘要和 LLM provider
  events/          # Event grouping 与 Top-K ranking
  research/        # Research Agent、校验、fallback、报告
  evaluation/      # 人工评测导入与 Markdown summary
  storage/         # SQLite、迁移和 repositories
  services/        # Phase 1 collection/processing/report services
prompts/           # 与 Python 业务逻辑分离的研究 prompts
evaluation/        # 人工评分 JSON 模板
config/            # 来源和 pipeline 参数
tests/             # 单元与集成测试
```

## Data Model and Migration

`Database.initialize()` 使用幂等、向后兼容的增量迁移。现有 Phase 1 SQLite 会原地增加字段和表，不删除文章数据。

### Articles

Phase 1 字段全部保留，并新增：

- `content`：提取的网页正文
- `content_status`：`pending` / `fetched` / `failed`
- `content_length`
- `content_fetched_at`
- `content_error`

RSS 的 `raw_text` 永不被正文提取覆盖。成功提取的文章默认不会重复下载。

### Events

`events` 保存：

- `id`、`title`、`normalized_title`、`category`
- `created_at`、`updated_at`
- `importance_score`
- `article_count`、`source_count`

`event_articles.article_id` 有唯一约束，因此一篇文章最多归属一个 Event。

### ResearchBrief

`research_briefs` 结构化保存：

- `headline`
- `executive_summary`
- `what_happened`
- `key_facts`，每条区分 `reported_fact` 与 `inference`
- `background`
- `why_it_matters`
- `industry_impact`
- `ugc_relevance`
- `evidence`
- `sources`
- `uncertainties`
- `confidence`（0–1）
- `tags`、`provider_name`

模型返回的每个 source URL、evidence URL 和 article ID 都必须来自输入文章，否则整个 LLM brief 被拒绝并回退到本地实现。

### Evaluations

`evaluations` 保存五个 1–5 人工评分：

- `factuality`
- `source_coverage`
- `relevance`
- `insightfulness`
- `clarity`

## Installation

- Python 3.11+
- 网络仅用于 RSS、正文下载和可选 LLM 调用

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

不创建 `.env` 也可以运行。数据库、日志、真实 `.env` 和生成报告均被 `.gitignore` 排除。

## CLI Usage

### Phase 1 commands

```bash
python -m app collect
python -m app process
python -m app report
python -m app run
```

### Full-text extraction

```bash
python -m app fetch-content
python -m app fetch-content --limit 20
python -m app fetch-content --limit 20 --retry-failed
```

单篇 403、404、超时、非 HTML、页面过大或正文解析失败只影响该文章。失败原因保存在 `content_error`。

### Event grouping and Top-K

```bash
python -m app events
python -m app events --limit 500 --top 10
```

第一版 grouping 有意保守：

- 只在配置的时间窗口内比较；
- 非兼容 category 不合并；
- 需要足够的标题词元重叠与相似度；
- 同一来源的不同文章默认不聚类，避免把模板系列误当成同一事件；
- 没有足够证据时创建独立 Event。

Event score 综合最高 article importance、独立来源数量、recency 和 category。没有 API key 也能稳定运行。

### Research Agent

```bash
python -m app research --top 10
python -m app research --top 10 --force
python -m app research-report --top 10
```

默认无 key 时使用 deterministic fallback。它会：

- 只引用 linked articles 的真实 URL；
- 把抽取内容、文章摘要或 RSS 文本转为可追踪 evidence；
- 明确记录单来源、正文缺失等 uncertainty；
- 对无明显 UGC 关系的事件输出 `low relevance / limited direct impact`；
- 对单来源且无完整正文的 brief 使用保守 confidence。

研究 prompts 位于：

```text
prompts/research_system.txt
prompts/research_event.txt
```

大型 prompt 不在 Python service 中硬编码。

### Human evaluation

复制并编辑 `evaluation/evaluation_template.json`，将 `research_brief_id` 改为真实 ID，然后执行：

```bash
python -m app evaluate --input evaluation/evaluation_template.json
```

评分会写入 SQLite，并在 `reports/` 生成逐维度 Markdown summary。该轻量框架适合后续人工评测 10–20 个真实事件。

## LLM Provider and Graceful Degradation

默认配置：

```dotenv
AI_INTEL_LLM_PROVIDER=disabled
AI_INTEL_LLM_API_KEY=
```

此时采集、正文、处理、grouping、ranking、research 和报告都能运行。

要使用 OpenAI-compatible Chat Completions API，在本地 `.env` 中设置：

```dotenv
AI_INTEL_LLM_PROVIDER=openai_compatible
AI_INTEL_LLM_API_KEY=your-key-here
AI_INTEL_LLM_MODEL=your-model
AI_INTEL_LLM_BASE_URL=https://api.example.com/v1
```

不要提交真实密钥。LLM 调用失败、JSON 无效、schema 不完整或出现输入之外的来源时，会记录 warning 并使用 deterministic fallback。

## Configuration

`config/sources.yaml` 管理 sources 和 pipeline 参数：

```yaml
app:
  content_timeout_seconds: 20
  content_min_length: 200
  content_max_bytes: 5000000
  content_batch_size: 20
  event_time_window_days: 7
  event_similarity_threshold: 0.62
  event_batch_size: 500
  research_top_k: 10
  prompts_dir: prompts

sources:
  - name: Example AI Lab
    url: https://example.com/feed.xml

## Phase 2.5: Research Quality Validation

Phase 2.7 is the current project boundary. Phase 3 has not started.

The research path is now explicit:

    Event
      -> Evidence Gathering
      -> Evidence Pack
      -> Evidence-bound Analysis
      -> ResearchBrief

Evidence Gathering uses deterministic queries derived from the event title, tags, and named
entities. The first implementation uses Bing News RSS and the existing standard-library HTTP
path. Search failures are logged in the Evidence Pack and do not terminate the pipeline.
Every candidate keeps its real URL, source name, and source type: official, independent_media,
research, community, or other. URLs are normalized and deduplicated before analysis. The
selection target is one official source plus one or two independent media sources; an Evidence Pack
records insufficient coverage when this is not achieved.

Research runs are stored separately by research_mode (deterministic, single_source_llm, or
multi_source_llm) and generation_type (deterministic, mock, live, fallback, or
legacy_unverified). This prevents deterministic, mock, or fallback output from overwriting a
live LLM result. Mock output is test-only validation and must never be reported as a successful
live call.

### Phase 2.5 commands

    python -m app reclassify --limit 1000
    python -m app ranking-audit --top 10
    python -m app gather-evidence --top 10

    python -m app research --mode deterministic --top 10 --force
    python -m app research --mode single-source-llm --top 10 --force
    python -m app research --mode multi-source-llm --top 10 --force

    python -m app research-report --mode deterministic --top 10
    python -m app research-report --mode multi-source-llm --top 10
    python -m app evaluation-template --top 10
    python -m app comparison-report --top 10

When no API key exists, the two LLM commands are explicitly logged and stored as fallback;
the comparison report states that live validation is blocked.

### Category, ranking, and UGC schemas

The Phase 2.5 taxonomy is: Foundation Model, AI Agent, AI Coding, Multimodal / AIGC,
AI Product, Enterprise Adoption, Research, Open Source, AI Safety, Cybersecurity,
Policy / Regulation, Funding / Business, and Other.

Importance ranking stores an audit breakdown for novelty, industry magnitude, source
authority, source diversity, ecosystem impact, developer impact, creator/UGC impact, and
recency. No title or article receives an article-specific hard-coded bonus.

UGC relevance is a structured object with level, directness, reason, and affected_areas.
Directness is none, indirect, or direct and does not automatically determine the level. Allowed
areas are creator_tools, content_creation, short_video, distribution, community, and moderation.
Unrelated events must remain low/none with no invented impact.

### Live LLM validation

Real credentials remain local-only. Copy .env.example to .env, then set:

    AI_INTEL_LLM_PROVIDER=openai_compatible
    AI_INTEL_LLM_API_KEY=your-real-key
    AI_INTEL_LLM_MODEL=your-model
    AI_INTEL_LLM_BASE_URL=https://api.openai.com/v1

For the required five-event comparison, run:

    python -m app research --mode single-source-llm --top 5 --force
    python -m app research --mode multi-source-llm --top 5 --force

This makes ten model calls: one single-source and one multi-source call for each event.
Each call sends the event metadata plus the selected Evidence Pack fields: source IDs,
titles, source names/types, real URLs, publication dates, snippets, and locally stored
article content where available. API keys, environment variables, database files, logs,
and unrelated articles are not included in prompts.

Every live or mock research call uses prompts/research_system.txt and
prompts/research_event.txt. Output must pass strict JSON, source-ID, URL, evidence-type, claim-confidence,
verification-level, key-fact, and structured-UGC validation before it is saved.
    enabled: true
    max_items: 100
    tags: [Research]
```

全局 `--config` 和 `--log-level` 选项放在子命令前：

```bash
python -m app --config config/sources.yaml --log-level DEBUG events --top 10
```

## Phase 2.7: Research Methodology and Human Evaluation

The research methodology is explicit and evidence-bound:

```text
Event
  -> Evidence Gathering
  -> Source Typing
  -> Evidence Validation
  -> Evidence-bound LLM Analysis
  -> Human Evaluation
```

Evidence sources use a finite taxonomy:

- `official`: first-party announcements, documentation, or model cards;
- `independent_media`: editorial reporting independent of the subject organization;
- `research`: papers and technical reports, which do not imply independent replication;
- `community`: forums, social posts, and community discussion;
- `other`: sources that do not fit the four research roles above.

Multiple URLs do not equal independent corroboration. Several official pages from one company
may improve first-party support while still providing no independent verification.

Evidence references distinguish `verbatim_quote` from `paraphrase`. A verbatim quote must be
found in the supplied snippet or content; an unverified quote is downgraded to a paraphrase.
Paraphrases are not rendered as quotations. Historical `excerpt` records remain readable through
the migration layer.

Research confidence is split into:

- `claim_confidence`: confidence that the Evidence Pack supports the brief's core factual claims;
- `verification_level`: `single_first_party`, `multi_first_party`, `research_supported`,
  `independently_corrob`, or `independently_replicated`.

`independently_replicated` is reserved for explicit independent technical or benchmark
replication. Source diversity primarily informs verification, while importance answers a separate
question: how consequential is the event to the AI industry?

### Human-reviewed pilot over 5 events

| Mode | Briefs | Mean score across five dimensions |
|---|---:|---:|
| deterministic | 5 | 2.32/5 |
| single-source LLM | 5 | 4.04/5 |
| multi-source LLM | 5 | 4.36/5 |

This is a small human-reviewed pilot evaluation over 5 events, not a statistically powered
benchmark. The results are directional and should not be interpreted as a general performance
claim. Scores cover factuality, source coverage, relevance, insightfulness, and clarity; the
persisted reviewer type is `human/manual`.

## Testing

```bash
python -m pytest
python -m pytest --cov=app --cov-report=term-missing
```

测试重点覆盖：

- Phase 1 数据库原地迁移与数据保留
- content extraction 错误隔离与成功后跳过
- 完整正文优先进入分类和摘要
- 同事件 grouping 与不同事件分离
- 同来源模板文章误合并防护
- deterministic no-key Research Agent
- ResearchBrief schema 和 confidence 范围
- 非法 LLM JSON 回退
- 虚构 source/evidence 拒绝
- Research Report 的真实 URL
- evaluation persistence、评分边界和 summary

## Current Boundaries

- 许多站点会对通用 HTTP 客户端返回 403；系统会回退到 RSS 内容，但正文覆盖率会下降。
- 当前 grouping 是保守词法方法，不使用 embeddings；漏合并优先于误合并。
- 默认官方博客源之间同事件交叉报道较少，source diversity 分值通常偏低。
- deterministic Research Agent 是安全、可运行的基线，不等同于高质量人工行业分析。
- Event 无自动重建/拆分 UI；grouping 参数变化后的批量重建目前属于运维操作。
- SQLite 面向单机工作流，没有并发 worker、任务队列或调度器。
- 没有 Dashboard、搜索 UI 或人工审核界面。

## Suggested Phase 3

Phase 3 应优先提升证据覆盖和研究质量，而不是增加 UI：

1. 增加更多独立媒体、公司公告、论文与监管来源，建立来源健康度指标。
2. 加入合法、可配置的站点级正文抓取策略和缓存，改善 403/正文覆盖率。
3. 建立 10–20 个真实事件人工评测集，比较 prompt/model/fallback 版本。
4. 在保持可解释性的前提下评估 entity extraction 或轻量 embedding-assisted grouping。
5. 增加 prompt/version、模型成本、延迟和输出质量观测。

Dashboard 应在数据质量和研究评测稳定之后再考虑。

