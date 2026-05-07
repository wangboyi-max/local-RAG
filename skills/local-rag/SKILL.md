---
name: local-rag
description: 本地 Graph RAG 知识库检索、文档索引和笔记管理
---

# Local RAG 知识库

通过 MCP 工具调用本地的 Graph RAG 服务，支持文档索引（PDF/图片 OCR）和 Markdown 笔记管理。

## 文档索引

当用户要求索引 PDF 或图片文件时，使用 `ingest_file` 工具。文件路径必须是本地绝对路径。

```
> 帮我索引 /path/to/document.pdf
> 把这张图片加入知识库: /home/user/notes/image.png
```

## 知识库检索

当用户询问知识库内容时，使用 `search_docs` 工具进行混合检索（向量 + 图谱）。

```
> 搜索关于 XX 的内容
> 知识库里有没有关于权限管理的文档？
```

## 笔记管理

笔记以 Markdown 文件形式存储在数据目录中。常用操作：

- **创建笔记**: `create_note(title, content, tags)`
- **读取笔记**: `get_note(title)` — 按标题查找
- **列出笔记**: `list_notes(tag?)` — 可选按标签过滤
- **更新笔记**: `update_note(title, content?, tags?, new_title?)` — 支持重命名
- **删除笔记**: `delete_note(title)`
- **搜索笔记**: `search_notes(query, top_k?)` — 向量语义搜索
- **重建索引**: `reindex_note(title)` — 外部编辑 .md 文件后手动触发

笔记文件是纯 Markdown，无 frontmatter，可直接用任意编辑器打开编辑。
编辑后需调用 `reindex_note(title)` 重建 RAG 索引。

## 查看统计

使用 `graph_stats` 查看知识图谱统计信息，`list_docs` 查看已索引文档列表。
