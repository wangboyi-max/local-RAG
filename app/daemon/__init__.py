"""Daemon 入口：运行迁移 → 初始化服务单例 → 启动 HTTPServer。"""
import logging
import signal
import sys

logger = logging.getLogger(__name__)


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    # 确定数据目录
    from app.config import settings
    data_dir = settings.work_dir

    # 运行迁移
    try:
        from app.migrations import run_migrations
        run_migrations(data_dir)
    except Exception:
        logger.exception("[daemon] 迁移执行失败")
        sys.exit(1)

    # 启动 HTTP server
    from app.daemon.server import DaemonServer
    daemon = DaemonServer(data_dir)

    def _shutdown(signum, frame):
        logger.info("[daemon] 收到退出信号，关闭服务...")
        daemon.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    daemon.start()


if __name__ == "__main__":
    main()
