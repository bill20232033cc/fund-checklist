"""日志 VERBOSE 级 + FUND_CHECKLIST_LOG_LEVEL 配置的测试。"""

from __future__ import annotations

import logging

import pytest

from fund_agent.agent.log_levels import (
    LOG_LEVEL_ENV,
    VERBOSE_LOG_LEVEL,
    VERBOSE_LOG_NAME,
    configure_logging,
    register_verbose_log_level,
    verbose,
)


def test_verbose_level_constants() -> None:
    """VERBOSE=15 且位于 DEBUG/INFO 之间。"""

    assert VERBOSE_LOG_LEVEL == 15
    assert VERBOSE_LOG_NAME == "VERBOSE"
    assert 10 < VERBOSE_LOG_LEVEL < 20


def test_register_verbose_log_level_idempotent() -> None:
    """重复注册 VERBOSE 级别幂等，getLevelName 始终返回 15。"""

    register_verbose_log_level()
    register_verbose_log_level()
    assert logging.getLevelName("VERBOSE") == 15


def test_verbose_records_below_or_equal_threshold(caplog: pytest.LogCaptureFixture) -> None:
    """logger 级别 ≤15 时 verbose() 产出 levelno=15 / levelname=VERBOSE 记录。"""

    logger = logging.getLogger("test.verbose.emit")

    with caplog.at_level(VERBOSE_LOG_LEVEL, logger="test.verbose.emit"):
        verbose(logger, "诊断消息 %s", "payload")

    matches = [
        record
        for record in caplog.records
        if record.name == "test.verbose.emit"
        and record.levelno == VERBOSE_LOG_LEVEL
        and record.levelname == "VERBOSE"
    ]
    assert len(matches) == 1
    assert matches[0].getMessage() == "诊断消息 payload"


def test_verbose_silent_above_threshold(caplog: pytest.LogCaptureFixture) -> None:
    """logger 有效级别 >15 时 verbose() 按标准 logging 语义静默。"""

    logger = logging.getLogger("test.verbose.silent")

    with caplog.at_level(logging.INFO, logger="test.verbose.silent"):
        verbose(logger, "不应出现")

    assert not [
        record
        for record in caplog.records
        if record.name == "test.verbose.silent" and record.levelno == VERBOSE_LOG_LEVEL
    ]


def test_configure_logging_absent_and_empty_are_noop() -> None:
    """env 缺失/空值/纯空白时 configure_logging 不改变根 logger level 与 handlers。"""

    root = logging.getLogger()
    saved_handlers = list(root.handlers)
    saved_level = root.level
    try:
        configure_logging(env={})
        assert root.handlers == saved_handlers
        assert root.level == saved_level

        configure_logging(env={LOG_LEVEL_ENV: ""})
        assert root.handlers == saved_handlers
        assert root.level == saved_level

        configure_logging(env={LOG_LEVEL_ENV: "   "})
        assert root.handlers == saved_handlers
        assert root.level == saved_level
    finally:
        root.handlers[:] = saved_handlers
        root.setLevel(saved_level)


def test_configure_logging_verbose_sets_root_level() -> None:
    """FUND_CHECKLIST_LOG_LEVEL=VERBOSE（小写 + 空白容忍）时根 logger level 置为 15。"""

    root = logging.getLogger()
    saved_handlers = list(root.handlers)
    saved_level = root.level
    try:
        root.handlers[:] = []
        configure_logging(env={LOG_LEVEL_ENV: "  verbose  "})
        assert root.level == VERBOSE_LOG_LEVEL
    finally:
        root.handlers[:] = saved_handlers
        root.setLevel(saved_level)


def test_configure_logging_unknown_value_raises_value_error() -> None:
    """未知取值 fail-fast 抛 ValueError，消息含合法取值。"""

    with pytest.raises(ValueError) as excinfo:
        configure_logging(env={LOG_LEVEL_ENV: "TRACE"})

    message = str(excinfo.value)
    assert LOG_LEVEL_ENV in message
    for name in ("DEBUG", "VERBOSE", "INFO", "WARNING", "ERROR"):
        assert name in message
