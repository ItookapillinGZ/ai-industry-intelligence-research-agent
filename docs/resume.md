# Resume-ready project descriptions

All figures below come from the completed Phase 2.6/2.7 repository artifacts. The evaluation is a small human-reviewed pilot, not a statistically powered benchmark.

## 中文简历版本

- 搭建面向 AI Agent、基础模型、AI Coding 与 AIGC 等领域的行业情报工作流，实现配置化 RSS 采集、URL/标题去重、事件聚类、重要性排序、Evidence Gathering 与结构化 ResearchBrief 生成。
- 设计 evidence-grounded LLM Research Pipeline，通过 source typing、事实/推断分离、`claim_confidence`、`verification_level`、uncertainty 与真实 URL 校验降低幻觉和错误归因。
- 构建 deterministic、single-source LLM、multi-source LLM 三组对照，对 5 个真实事件、15 份 ResearchBrief 开展人工评测，五维综合均分为 2.32 / 4.04 / 4.36；结果定位为小规模方向性 pilot。
- 采用高吞吐 deterministic preprocessing + Top-K LLM research 的分层架构；10 份有效 live ResearchBrief 共使用约 52.6k tokens，按实验记录估算成本约 $0.27。

## English resume version

- Built a local AI industry-intelligence pipeline covering configurable RSS ingestion, URL/title deduplication, event grouping, auditable importance ranking, multi-source evidence gathering, and structured ResearchBrief generation.
- Designed an evidence-grounded LLM research workflow with source typing, fact/inference separation, `claim_confidence`, `verification_level`, uncertainty tracking, and strict source-ID/URL validation to reduce hallucination and attribution errors.
- Compared deterministic, single-source LLM, and multi-source LLM modes across 5 real events and 15 ResearchBriefs; a small human-reviewed pilot scored the modes 2.32, 4.04, and 4.36 out of 5.
- Implemented cost-aware deterministic preprocessing with Top-K LLM research; 10 valid live ResearchBriefs used approximately 52.6k tokens at an estimated experiment cost of $0.27.
