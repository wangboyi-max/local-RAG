"""初始迁移：确保外部数据目录存在，迁移旧数据（如存在）。"""
import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

UPGRADE_TO = "0.2.0"


def upgrade(data_dir: str = ""):
    """创建外部数据目录结构，迁移旧数据。"""
    if not data_dir:
        data_dir = str(Path.home() / ".local" / "share" / "local-rag")
    target = Path(data_dir)
    target.mkdir(parents=True, exist_ok=True)

    # 与 config.py 保持一致：rag/chroma_db、rag/uploads、notes
    subdirs = ["rag/chroma_db", "rag/uploads", "notes"]
    for sub in subdirs:
        (target / sub).mkdir(parents=True, exist_ok=True)

    # 如果旧 ./data 目录有数据，迁移到外部目录
    old_data = Path(__file__).parent.parent.parent / "data"
    if old_data != target and old_data.exists():
        for sub in subdirs:
            old_sub = old_data / sub
            new_sub = target / sub
            if old_sub.exists() and not any(new_sub.iterdir()):
                logger.info("[migration] 迁移旧数据 %s → %s", old_sub, new_sub)
                for item in old_sub.iterdir():
                    dest = new_sub / item.name
                    if item.is_dir():
                        if dest.exists():
                            shutil.copytree(str(item), str(dest), dirs_exist_ok=True)
                        else:
                            shutil.copytree(str(item), str(dest))
                    else:
                        shutil.copy2(str(item), str(dest))

    # 迁移旧 tasks.json
    old_tasks = old_data / "tasks.json"
    new_tasks = target / "tasks.json"
    if old_tasks.exists() and not new_tasks.exists():
        shutil.copy2(str(old_tasks), str(new_tasks))
        logger.info("[migration] 迁移 tasks.json")

    # 确保 .gitkeep 在 notes 目录
    (target / "notes" / ".gitkeep").touch(exist_ok=True)

    logger.info("[migration] 数据目录就绪: %s", target)
