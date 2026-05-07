"""迁移系统：按版本号比较并顺序执行迁移脚本。

设计：
- 迁移文件放在此目录下，命名为 NNN_description.py
- 每个文件声明 UPGRADE_TO = "X.Y.Z"
- 运行时比较已安装版本，按序执行未完成的迁移
- 每次迁移成功后立即写入 .installed_version，中断可恢复
"""
import importlib
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_MIGRATIONS_DIR = Path(__file__).parent


def get_code_version() -> str:
    """从项目根目录的 VERSION 文件读取代码版本。"""
    version_file = _MIGRATIONS_DIR.parent.parent / "VERSION"
    if version_file.exists():
        return version_file.read_text().strip()
    return "0.0.0"


def get_installed_version(data_dir: str = "") -> str:
    """从数据目录的 .installed_version 文件读取已安装版本。"""
    if not data_dir:
        data_dir = str(Path.home() / ".local" / "share" / "local-rag")
    marker = Path(data_dir) / ".installed_version"
    if marker.exists():
        return marker.read_text().strip()
    return "0.0.0"


def _parse_version(v: str) -> tuple:
    """将 "X.Y.Z" 解析为可比较的元组。"""
    return tuple(int(x) for x in v.split("."))


def _write_installed_version(data_dir: str, version: str):
    marker = Path(data_dir) / ".installed_version"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(version)


def run_migrations(data_dir: str = ""):
    """执行所有待运行的迁移。"""
    if not data_dir:
        data_dir = str(Path.home() / ".local" / "share" / "local-rag")
    installed = get_installed_version(data_dir)
    code = get_code_version()

    if installed == code:
        logger.info("[migrations] 已是最新版本 (%s)，无需迁移", code)
        return

    installed_v = _parse_version(installed)
    logger.info("[migrations] 当前版本 %s → 目标版本 %s", installed, code)

    # 按文件名排序，依次执行
    migration_files = sorted(_MIGRATIONS_DIR.glob("[0-9]*.py"))
    for mf in migration_files:
        if mf.name == "__init__.py":
            continue

        mod = importlib.import_module(f"app.migrations.{mf.stem}")
        target = getattr(mod, "UPGRADE_TO", None)
        if target is None:
            logger.warning("[migrations] 跳过 %s：缺少 UPGRADE_TO", mf.name)
            continue

        target_v = _parse_version(target)
        if target_v <= installed_v:
            logger.info("[migrations] 已执行 %s (%s)，跳过", mf.name, target)
            continue

        logger.info("[migrations] 执行 %s → %s", mf.name, target)
        try:
            mod.upgrade(data_dir=data_dir)
        except Exception:
            logger.exception("[migrations] %s 执行失败", mf.name)
            raise

        _write_installed_version(data_dir, target)
        logger.info("[migrations] %s 完成", mf.name)

    logger.info("[migrations] 所有迁移完成，当前版本 %s", get_installed_version(data_dir))
