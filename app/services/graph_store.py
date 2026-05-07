import logging
import sys

from neo4j import GraphDatabase
from app.config import settings
from app.services.entity_extractor import EntityExtractor, create_extractor

logger = logging.getLogger(__name__)

# 常见中文停用词（LLM 提取时不再需要，保留给 retrieval 管线关键词匹配用）
STOP_WORDS = set(
    "的 了 是 在 我 有 和 就 不 人 都 一 一个 上 也 很 到 说 要 去 你 会 着 已经 如果 这 那 他 她 它 们 中 与 及 等 而 但 或 被 把 从 向 对 于 以 关于".split()
)


class GraphStoreService:
    def __init__(
        self,
        uri: str | None = None,
        user: str | None = None,
        password: str | None = None,
        entity_extractor: EntityExtractor | None = None,
    ):
        self.uri = uri or settings.neo4j_uri
        self.user = user or settings.neo4j_user
        self.password = password or settings.neo4j_password
        self.driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))
        self.entity_extractor = entity_extractor or create_extractor()
        self._ensure_constraints()

    def _ensure_constraints(self):
        """创建唯一约束，防止重复实体。"""
        with self.driver.session() as session:
            session.run(
                "CREATE CONSTRAINT entity_name IF NOT EXISTS "
                "FOR (e:Entity) REQUIRE e.name IS UNIQUE"
            )
            session.run(
                "CREATE CONSTRAINT chunk_id IF NOT EXISTS "
                "FOR (c:Chunk) REQUIRE c.chunkId IS UNIQUE"
            )

    def add_entities(self, texts: list[str], metadatas: list[dict]):
        """将文本块提取实体并写入图谱。"""
        total_chunks = len(texts)
        chunks_with_entities = 0
        total_entities = 0
        with self.driver.session() as session:
            for i, (text, meta) in enumerate(zip(texts, metadatas), 1):
                chunk_id = f"{meta.get('source', 'unknown')}-{meta.get('chunk_index', 0)}"
                source = meta.get("source", "unknown")
                page = meta.get("page", 0)

                # 实体提取
                entities = self.entity_extractor.extract(text)
                if not entities:
                    logger.debug("chunk %s: no entities extracted", chunk_id)
                    print(f"[Graph] 实体提取 {i}/{total_chunks}: {chunk_id} (0 实体)", file=sys.stderr, flush=True)
                    continue

                chunks_with_entities += 1
                total_entities += len(entities)
                entity_names = [e["name"] for e in entities]
                logger.info("chunk %s: extracted %d entities: %s", chunk_id, len(entities), entity_names)
                print(f"[Graph] 实体提取 {i}/{total_chunks}: {chunk_id} ({len(entities)} 实体: {', '.join(entity_names)})", file=sys.stderr, flush=True)

                # 创建 Chunk 节点
                note_id = meta.get("note_id")
                if note_id:
                    session.run(
                        """
                        MERGE (c:Chunk {chunkId: $chunkId})
                        SET c.source = $source, c.page = $page, c.text = $text, c.noteId = $noteId
                        """,
                        chunkId=chunk_id,
                        source=source,
                        page=page,
                        text=text,
                        noteId=note_id,
                    )
                else:
                    session.run(
                        """
                        MERGE (c:Chunk {chunkId: $chunkId})
                        SET c.source = $source, c.page = $page, c.text = $text
                        """,
                        chunkId=chunk_id,
                        source=source,
                        page=page,
                        text=text,
                    )

                # 创建 Entity 节点和 MENTIONS 关系
                for entity in entities:
                    session.run(
                        """
                        MATCH (c:Chunk {chunkId: $chunkId})
                        MERGE (e:Entity {name: $name})
                        SET e.type = $type
                        MERGE (c)-[:MENTIONS]->(e)
                        """,
                        chunkId=chunk_id,
                        name=entity["name"],
                        type=entity["type"],
                    )

                # 创建实体间的 RELATED_TO 共现关系
                if len(entity_names) > 1:
                    for i in range(len(entity_names)):
                        for j in range(i + 1, len(entity_names)):
                            session.run(
                                """
                                MATCH (e1:Entity {name: $name1}), (e2:Entity {name: $name2})
                                WHERE e1 <> e2
                                MERGE (e1)-[r:RELATED_TO]-(e2)
                                SET r.weight = coalesce(r.weight, 0) + 1
                                """,
                                name1=entity_names[i],
                                name2=entity_names[j],
                            )

        logger.info(
            "graph add_entities done: %d/%d chunks had entities, %d total entities written",
            chunks_with_entities,
            total_chunks,
            total_entities,
        )

    def expand_context(self, query_keywords: list[str], max_depth: int = 2) -> list[dict]:
        """从查询关键词匹配实体，BFS 扩展获取关联的 Chunk 文本。"""
        if not query_keywords:
            return []
        depth_pattern = "-[*1.." + str(max_depth) + "]-"
        cypher = f"""
            MATCH (e:Entity)
            WHERE e.name IN $keywords
            MATCH path = (e){depth_pattern}(connected)
            WHERE connected:Chunk
            RETURN DISTINCT connected.source AS source,
                   connected.page AS page,
                   connected.text AS text,
                   connected.chunkId AS chunkId
            LIMIT 20
            """
        with self.driver.session() as session:
            result = session.run(cypher, keywords=query_keywords)
            return [dict(record) for record in result]

    def delete_by_source(self, source: str) -> int:
        """删除指定来源的所有 Chunk 节点及孤立 Entity。"""
        with self.driver.session() as session:
            session.run(
                """
                MATCH (c:Chunk {source: $source})
                OPTIONAL MATCH (c)-[r:MENTIONS]-(e:Entity)
                WITH c, r, e
                DELETE c, r
                """,
                source=source,
            )
            # 清理孤立 Entity（无任何 Chunk 引用的实体）
            orphan_result = session.run(
                """
                MATCH (e:Entity)
                WHERE NOT (e)<-[:MENTIONS]-()
                WITH e
                OPTIONAL MATCH (e)-[r:RELATED_TO]-()
                DELETE e, r
                RETURN count(e) AS deleted
                """,
            )
            record = orphan_result.single()
            return record["deleted"] if record else 0

    def delete_by_note_id(self, note_id: str) -> int:
        """删除指定笔记的所有 Chunk 节点及 MENTIONS 关系，清理孤立 Entity。"""
        with self.driver.session() as session:
            session.run(
                """
                MATCH (c:Chunk {noteId: $noteId})
                OPTIONAL MATCH (c)-[r:MENTIONS]-(e:Entity)
                WITH c, r, e
                DELETE c, r
                """,
                noteId=note_id,
            )
            # 清理孤立 Entity（无任何 Chunk 引用的实体）
            session.run(
                """
                MATCH (e:Entity)
                WHERE NOT (e)<-[:MENTIONS]-()
                DELETE e
                """
            )

    def get_stats(self) -> dict:
        """返回图谱统计信息。"""
        with self.driver.session() as session:
            chunk_count = session.run("MATCH (c:Chunk) RETURN count(c) AS n").single()["n"]
            entity_count = session.run("MATCH (e:Entity) RETURN count(e) AS n").single()["n"]
            rel_count = session.run("MATCH ()-[r]->() RETURN count(r) AS n").single()["n"]
            return {
                "chunk_nodes": chunk_count,
                "entity_nodes": entity_count,
                "relationships": rel_count,
            }

    def close(self):
        self.entity_extractor.close()
        self.driver.close()
