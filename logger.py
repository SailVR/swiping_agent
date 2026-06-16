"""
日志系统

为整个项目提供统一的日志配置，支持：
- 文件日志（自动轮转，保留 7 天，单文件 5MB）
- 控制台日志（仅 WARNING+，避免干扰终端）
- 每个模块独立 logger，按需获取

用法：
    from logger import get_logger
    logger = get_logger(__name__)
    logger.info("...")
"""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from typing import Optional

# ── 全局配置 ────────────────────────────────────────────

LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
LOG_LEVEL_FILE = logging.DEBUG       # 文件记录所有级别
LOG_LEVEL_CONSOLE = logging.WARNING  # 控制台只显示 WARNING 以上
MAX_BYTES = 5 * 1024 * 1024          # 单文件 5MB
BACKUP_COUNT = 3                     # 保留 3 个轮转文件

_FILE_HANDLER: Optional[logging.Handler] = None
_CONSOLE_HANDLER: Optional[logging.Handler] = None


def _ensure_handlers():
    """确保全局文件和控制台 handler 已创建（单例）。"""
    global _FILE_HANDLER, _CONSOLE_HANDLER

    if _FILE_HANDLER is not None:
        return

    os.makedirs(LOG_DIR, exist_ok=True)

    # ── 文件 Handler（轮转，UTF-8） ──
    file_path = os.path.join(LOG_DIR, "app.log")
    _FILE_HANDLER = RotatingFileHandler(
        file_path,
        maxBytes=MAX_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    _FILE_HANDLER.setLevel(LOG_LEVEL_FILE)
    _FILE_HANDLER.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)-7s] %(name)s | %(filename)s:%(lineno)d | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))

    # ── 控制台 Handler（只输出 WARNING+） ──
    _CONSOLE_HANDLER = logging.StreamHandler(sys.stderr)
    _CONSOLE_HANDLER.setLevel(LOG_LEVEL_CONSOLE)
    _CONSOLE_HANDLER.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    ))

    # 禁用第三方库的 DEBUG 日志避免刷屏
    for noisy in ("httpx", "urllib3", "httpcore", "openai", "langchain", "langgraph"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str = __name__) -> logging.Logger:
    """获取一个配置好的 logger 实例。

    Args:
        name: 通常传 __name__，形如 "agents.master_agent"。

    Returns:
        已挂载文件 + 控制台 handler 的 Logger 对象。
    """
    _ensure_handlers()

    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)  # 由 handler 级别控制过滤

    # 避免重复添加 handler
    if not logger.handlers:
        if _FILE_HANDLER:
            logger.addHandler(_FILE_HANDLER)
        if _CONSOLE_HANDLER:
            logger.addHandler(_CONSOLE_HANDLER)

    return logger


def set_console_level(level: int) -> None:
    """动态调整控制台输出级别（调试时可临时切到 DEBUG）。"""
    _ensure_handlers()
    if _CONSOLE_HANDLER:
        _CONSOLE_HANDLER.setLevel(level)


def get_log_file_path() -> str:
    """获取当前日志文件路径。"""
    return os.path.join(LOG_DIR, "app.log")
