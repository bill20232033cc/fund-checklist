"""日志级别扩展：VERBOSE 诊断级 + 环境变量驱动的日志配置。"""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping

VERBOSE_LOG_LEVEL: int = 15
VERBOSE_LOG_NAME: str = "VERBOSE"
LOG_LEVEL_ENV: str = "FUND_CHECKLIST_LOG_LEVEL"
_ALLOWED_LOG_LEVELS: tuple[str, ...] = ("DEBUG", "VERBOSE", "INFO", "WARNING", "ERROR")
_BASIC_FORMAT: str = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def register_verbose_log_level() -> None:
    """把 VERBOSE=15 注册进标准 logging 级别表（幂等）。

    参数:
        无。

    返回:
        None。

    异常:
        不抛出业务异常。
    """

    logging.addLevelName(VERBOSE_LOG_LEVEL, VERBOSE_LOG_NAME)


def verbose(logger: logging.Logger, message: str, *args: object, **kwargs: object) -> None:
    """以 VERBOSE 级别写一条日志记录。

    参数:
        logger: 目标 logger。
        message: 日志消息模板（% 风格占位符）。
        args/kwargs: 模板格式化参数，透传 logging.Logger.log。

    返回:
        None。

    异常:
        logger 有效级别高于 VERBOSE 时按标准 logging 语义静默，不抛出。
    """

    register_verbose_log_level()
    logger.log(VERBOSE_LOG_LEVEL, message, *args, **kwargs)


def configure_logging(*, env: Mapping[str, str] | None = None) -> None:
    """按 FUND_CHECKLIST_LOG_LEVEL 环境变量配置根 logger（默认 absent 时零行为变更）。

    参数:
        env: 环境变量映射；缺省取 os.environ。

    返回:
        None。

    异常:
        环境变量取值为合法集合外时抛 ValueError，提示合法取值。
    """

    source = os.environ if env is None else env
    raw = source.get(LOG_LEVEL_ENV)
    value = (raw or "").strip().upper()
    if not value:
        return
    if value not in _ALLOWED_LOG_LEVELS:
        raise ValueError(f"{LOG_LEVEL_ENV} 取值必须为 {'/'.join(_ALLOWED_LOG_LEVELS)}")
    register_verbose_log_level()
    level = logging.getLevelName(value)
    logging.basicConfig(level=level, format=_BASIC_FORMAT)
