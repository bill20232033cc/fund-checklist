"""interruptible_process 进程隔离执行原语的回归测试（真实子进程，无 fake）。"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from fund_agent.fund.document_tools.interruptible_process import (
    DEFAULT_TERMINATE_GRACE_SECONDS,
    InterruptibleProcess,
    SubprocessExecutionError,
    SubprocessTimeoutError,
    run_in_subprocess,
)


def test_run_in_subprocess_returns_child_result() -> None:
    """run_in_subprocess 必须返回子进程内的结果，而不是父进程。"""

    child_pid = run_in_subprocess(os.getpid, timeout=10)
    assert isinstance(child_pid, int)
    assert child_pid != os.getpid()


def test_run_in_subprocess_timeout_raises() -> None:
    """一站式超时路径必须抛 SubprocessTimeoutError 并回收子进程。"""

    with pytest.raises(SubprocessTimeoutError):
        run_in_subprocess(time.sleep, args=(60,), timeout=0.3)


def test_interruptible_process_manual_terminate_kill_reaps() -> None:
    """纯手动 API 必须完成 start→join→terminate→grace→kill→join 的真实回收。"""

    proc = InterruptibleProcess(target=time.sleep, args=(60,), timeout=0.3)
    proc.start()
    proc.join(0.3)
    assert proc.is_alive()
    proc.terminate()
    time.sleep(DEFAULT_TERMINATE_GRACE_SECONDS)
    proc.kill()
    proc.join(5)
    assert not proc.is_alive()
    assert proc._process.exitcode is not None
    proc.close()


def test_run_in_subprocess_child_error_propagates() -> None:
    """子进程执行异常必须经 envelope 传播为 SubprocessExecutionError。"""

    with pytest.raises(SubprocessExecutionError) as exc_info:
        run_in_subprocess(int, args=("not-a-number",), timeout=10)
    assert exc_info.value.child_type == "ValueError"


def test_interruptible_process_rejects_invalid_params() -> None:
    """timeout<=0 或 grace_period<0 必须抛 ValueError。"""

    with pytest.raises(ValueError):
        InterruptibleProcess(target=time.sleep, args=(0,), timeout=0)
    with pytest.raises(ValueError):
        InterruptibleProcess(target=time.sleep, args=(0,), timeout=1, grace_period=-1)


def test_interruptible_process_bounded_close_idempotent() -> None:
    """close 幂等、run 后 close 不抛、重复 run / start 后 run 抛 RuntimeError。"""

    proc = InterruptibleProcess(target=time.sleep, args=(0.05,), timeout=10)
    result = proc.run()
    assert result is None
    proc.close()
    proc.close()
    with pytest.raises(RuntimeError):
        proc.run()

    started = InterruptibleProcess(target=time.sleep, args=(0.05,), timeout=10)
    started.start()
    with pytest.raises(RuntimeError):
        started.run()
    started.join(5)
    started.close()
