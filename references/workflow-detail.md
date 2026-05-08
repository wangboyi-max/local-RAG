# 检索策略详解

## RAG 混合检索原理

knowledge-hub 使用三层检索策略：

### 1. BM25 关键词匹配
- 基于词频-逆文档频率的传统搜索引擎
- 擅长精确关键词匹配，对专业术语敏感
- 速度快，无需模型推理

### 2. 向量语义检索
- 使用 BGE-M3 嵌入模型将文本转为高维向量
- 通过余弦相似度计算语义相关性
- 擅长理解语义但字面不匹配的查询（如"如何培养孩子的英语兴趣"匹配"二语习得 启蒙阶段"）

### 3. 知识图谱扩展
- 文档索引时自动提取实体（人名、概念、机构等）并构建关系图
- 检索时将查询词中的实体在图谱中进行 BFS 扩展，找到关联文档
- 擅长发现间接关联（如查询"自然拼读"可扩展到相关教材出版社、分级读物系列）

**混合排序**：BM25 + 向量 + 图谱三路结果通过 Reciprocal Rank Fusion 合并排序，返回最相关的 top_k 个结果。

## 笔记与 RAG 的同步机制

Markdown 笔记管理采用**双写模式**：

1. **文件系统**：笔记以纯 `.md` 文件存储在 `.knowledge-hub/notes/` 目录，可用任意编辑器直接修改
2. **RAG 索引**：通过 `create_note` / `reindex_note` MCP 工具将笔记内容同步到向量数据库和知识图谱

**同步触发时机**：
- 创建笔记时：`create_note(title, content, tags)` 自动写入文件 + 异步索引
- 外部编辑后：手动调用 `reindex_note(title)` 重建索引
- 删除笔记时：`delete_note(title)` 同时删除文件和 RAG 索引

**异步处理**：索引是异步操作（大文件需要 OCR + 嵌入 + 图谱提取），可通过 `task_status(task_id)` 查询进度。

## 异步任务处理

以下操作返回 `task_id` 而非直接结果：
- `ingest_file`：索引 PDF/图片（最慢，涉及 OCR）
- `create_note`：创建并索引笔记
- `update_note`：更新并重新索引笔记
- `reindex_note`：手动重建索引

查询进度：
```
task_status(task_id="xxx")
# 返回: {"status": "running" | "completed" | "failed", "progress": "5/22 pages"}
```

## 实体提取模式选择

| 模式 | 速度 | 质量 | 依赖 | 适用场景 |
|------|------|------|------|---------|
| `jieba` | 快（毫秒级） | 中等 | 无额外依赖 | 中文文档、快速索引、无 LLM API |
| `llm` | 慢（网络请求） | 高 | 需配置 LLM_API_KEY | 需要精确实体识别、英文文档、专业领域 |

配置方式：编辑 `.env` 中的 `GRAPH_ENTITY_EXTRACTOR=jieba` 或 `llm`。

## 最佳实践

1. **先笔记后 RAG**：具体操作类问题先查笔记，理论类问题查 RAG
2. **大文件提前索引**：PDF 索引耗时较长（OCR 处理），建议在需要之前就预先索引
3. **定期维护**：用 `list_docs` 和 `list_notes` 定期检查知识源，用 `delete_docs` / `delete_note` 清理过期内容
4. **标签管理**：创建笔记时加 tags，方便后续 `list_notes(tag="xxx")` 快速筛选
