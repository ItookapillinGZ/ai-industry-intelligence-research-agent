# Interview guide

这些答案基于当前 Phase 1–2.7 实现，目标是帮助作者在 30–60 秒内讲清一个问题。回答时优先说“问题—设计—边界”，不要把小规模实验描述成通用 benchmark。

## 1. 为什么做这个项目？

AI 行业信息量大、重复高，而且公司公告、媒体、论文的证据角色不同。普通资讯流能告诉我“有一篇新文章”，却不容易回答“发生了什么事件、重要吗、由什么证据支持”。因此我做了一个本地研究工作流，把 RSS 文章转成事件、Evidence Pack 和结构化 ResearchBrief，并保留人工评测环节。

## 2. 为什么不是普通新闻摘要器？

摘要器通常是 `Article → Summary`，这个项目是 `Article → Event → Evidence → Research`。它先把多篇文章抽象为事件，再做重要性排序，只对 Top-K 收集和校验证据。最终输出还区分事实、推断、验证等级与不确定性，而不是只生成一段流畅文本。

## 3. Article 和 Event 有什么区别？

Article 是一个来源发布的一条内容，Event 是这些内容共同描述的现实变化。多个 URL 可能属于同一个 Event，一篇 Article 也不能只靠数据库自增 ID 判断身份。项目先做 URL/标题去重，再用时间窗口、类别兼容性和标题相似度做保守事件聚类。

## 4. 什么是 Evidence Pack？

Evidence Pack 是某个事件进入研究阶段时允许使用的证据集合。每条证据保留真实 URL、标题、来源、source type、snippet/正文和稳定 source ID，同时记录 official 与 independent coverage 是否充分。LLM 只能引用这个集合中的来源，不能自行补 URL。

## 5. 为什么多个 URL 不一定是独立来源？

独立性取决于来源控制关系和研究角色，不取决于域名或 URL 数量。例如 NVIDIA Blog、NVIDIA 模型卡和 NVIDIA 文档是三条材料，但都属于第一方。它们增加 evidence depth，却不能证明有独立媒体或第三方完成了验证。

## 6. 为什么需要 deterministic baseline？

第一，它保证没有 API key 时系统仍可运行，便于本地开发、测试和故障降级。第二，它给 LLM 评测提供最低可复现基线，帮助判断增益来自语言模型还是数据流程。它不是高质量研究员替代品，而是安全、便宜、稳定的对照组。

## 7. 为什么要比较 single-source 和 multi-source？

只比较 deterministic 与 LLM，会把“模型能力”和“新增证据”混在一起。single-source 与 multi-source 使用相同研究结构，区别在 Evidence Pack 覆盖，因此能观察第二来源是否真正增加新信息。结果也表明 multi-source 不会自动更好，新增来源必须提供有意义的证据。

## 8. ResearchBrief 如何降低 hallucination？

模型输入只包含当前 Event 和 Evidence Pack。输出必须是结构化 JSON，source ID、URL、evidence reference 和 key-fact reference 都要通过白名单校验；未知来源会导致整份结果被拒绝并回退。逐字引用还必须在输入文本中找到，否则自动降级为 paraphrase。

## 9. claim_confidence 和 verification_level 有什么区别？

`claim_confidence` 是 0–1 数值，回答“当前证据对核心 claim 的支持有多强”。`verification_level` 是语义分类，回答“支持来自单一第一方、多第一方、论文、独立佐证还是独立复现”。来源更多可能提高前者，但只有证据角色符合时才能改变后者。

## 10. 为什么不使用 LangChain 或 LangGraph？

当前流程是线性的、边界清晰的本地 pipeline，标准 Python、Protocol、factory 和 service 已足够表达替换、降级与测试。引入 Agent framework 会增加抽象层和调试成本，却没有解决当前阶段的具体问题。这个选择让架构更容易解释、测试和维护。

## 11. 最大的工程问题是什么？

一个典型问题是首次拉取包含大量历史记录的 RSS 时，逐条查询 SQLite 做 URL/标题去重，整体开销接近 O(n²)。另一个难点是让 LLM 输出真正受证据约束，而不是只在 prompt 里写“请勿幻觉”。前者通过 repository cache 解决，后者通过严格结构和运行时校验解决。

## 12. RSS O(n²) 去重问题怎么解决？

Repository 第一次查询时加载 normalized URL 与近期标题 snapshot 到内存，后续判断走 set/list cache；新插入记录同步更新缓存。SQLite 的 normalized URL unique constraint 仍保留，作为并发或遗漏情况下的最终防线。配置中的 per-source `max_items` 也限制单次历史 feed 规模。

## 13. 为什么只有 Top-K 才调用 LLM？

采集、标准化、去重和初步排序属于高吞吐、规则明确的工作，使用本地 deterministic 方法更可控。LLM 深度研究成本更高，只应投入行业重要性更高的事件。这样形成“300 articles → events → Top-K → LLM research”的分层成本结构。

## 14. 成本如何控制？

控制点包括本地预处理、Top-K 截断、按事件构造最小 Evidence Pack、single-event smoke gate，以及分别记录 token usage。Phase 2.6 的 10 份有效 live ResearchBrief 共使用 52,556 tokens，按实验记录估算约 $0.27。这个数字只是该次实验估算，核心是 cost-aware design。

## 15. Human evaluation 怎么设计？

对同样的 5 个真实事件分别生成 deterministic、single-source LLM 和 multi-source LLM，共 15 份 ResearchBrief。人工从 factuality、source coverage、relevance、insightfulness、clarity 五个维度按 1–5 分评价。三组均分为 2.32、4.04、4.36。

## 16. 5-event evaluation 有什么局限？

样本小、事件来自同一批数据，而且只有一名人工评审，因此没有统计效力，也不能外推到所有领域或模型。它适合验证评测流程、发现明显质量差异和暴露失败模式。下一步应该扩大事件集、增加评审者并做跨模型比较。

## 17. Multi-source 一定比 single-source 好吗？

不一定。第二来源可能只是转载、同一公司的另一页面，或者没有提供新事实；这种情况下只增加 token，不增加验证质量。NVIDIA 案例有三个 official URL 但没有 independent source，而 Knowledge Distillation 的论文增加了方法边界，Gemini 的媒体报道增加了发布背景。

## 18. 一个失败案例是什么？

早期 Virgin Atlantic 客户案例曾排到 #1，因为 recency、泛化 category bonus 和 article base score 权重过高。复核后把 importance 重心调整到 novelty、industry magnitude、ecosystem、developer 和 creator impact，并让 source coverage 主要影响 verification。另一个失败是首次 live 请求因不兼容的 `temperature` 参数返回 HTTP 400，之后加入 smoke gate。

## 19. 如果再给两周，会怎么继续？

我会先扩充评测集和人工评审覆盖，而不是加 Dashboard。然后评估 semantic-assisted event clustering、source health monitoring 与 cross-model comparison，同时继续保持 evidence validation 和 deterministic baseline。只有数据质量稳定后，才考虑定时投递等产品化方向。

## 20. 这个项目和 AI 内容 / UGC 岗位有什么关系？

项目覆盖 AIGC、创作者工具、内容生产、短视频、分发、社区与审核等影响维度。ResearchBrief 用结构化 `ugc_relevance` 记录 level、directness、reason 和 affected areas，避免把所有 AI 事件都硬说成 UGC 相关。它展示的是内容行业研究、信息判断与 AI 工程结合，而不是一个内容生成 Demo。
