"""进程隔离执行原语：子进程启动 / 结果回收 / terminate+kill / bounded close。

概念对齐 dayu runtime/interruptible_process.py 的「取消/超时 = 杀子进程」模式语义，
本模块为自实现，不复制 dayu 代码；仅使用标准库 multiprocessing（spawn 上下文）。
"""

from __future__ import annotations

import multiprocessing as mp
import time
from typing import Any, Callable

DEFAULT_TERMINATE_GRACE_SECONDS: float = 2.0
DEFAULT_JOIN_AFTER_KILL_SECONDS: float = 5.0


class SubprocessTimeoutError(TimeoutError):
    """子进程在 deadline 内未完成，已执行 terminate→grace→kill→reap→close。

    异常:
        调用方无需再手动清理；被超时回收的子进程已不再存活。
    """


class SubprocessExecutionError(RuntimeError):
    """子进程执行异常（envelope 回传）或无结果崩溃（envelope 缺失）。

    参数:
        message: 面向调用方的安全错误信息。
        child_type: 子进程内原始异常的类型名；无结果崩溃时为 None。
        child_message: 子进程内原始异常的消息；无结果崩溃时为 None。
    """

    def __init__(
        self,
        message: str,
        *,
        child_type: str | None = None,
        child_message: str | None = None,
    ) -> None:
        """初始化带子进程异常信息的执行错误。"""

        super().__init__(message)
        self.child_type = child_type
        self.child_message = child_message


def _child_entry(parent_conn, target: Callable[..., Any], args: tuple) -> None:
    """子进程入口：执行 target 并把单次结果 envelope 回传父进程。

    参数:
        parent_conn: 子进程持有的管道端点（发送端），仅用于回传一次 envelope。
        target: 必须可由 spawn 按引用序列化的模块级函数或 builtin。
        args: 传给 target 的位置参数。

    返回:
        无返回值；通过管道回传 ("ok", result) 或 ("error", (type, message))。

    异常:
        本函数捕获 target 抛出的 BaseException 并以 envelope 回传，不向进程外抛出。
    """

    try:
        result = target(*args)
        parent_conn.send(("ok", result))
    except BaseException as exc:
        parent_conn.send(("error", (type(exc).__name__, str(exc))))
    finally:
        parent_conn.close()


class InterruptibleProcess:
    """可抢占的子进程执行原语，支持一站式 run() 与手动 start/join/terminate/kill。

    参数:
        target: 必须可由 spawn 按引用序列化的顶层可调用（模块级函数 / builtin）。
        args: 传给 target 的位置参数。
        timeout: 硬 deadline 秒数，必须为正数。
        grace_period: terminate 后等待 kill 的宽限秒数，不能为负数。

    返回:
        InterruptibleProcess 实例。

    异常:
        ValueError: timeout<=0 或 grace_period<0 时抛出。
    """

    def __init__(
        self,
        *,
        target: Callable[..., Any],
        args: tuple = (),
        timeout: float,
        grace_period: float = DEFAULT_TERMINATE_GRACE_SECONDS,
    ) -> None:
        """初始化管道端点、目标与生命周期状态。"""

        if timeout <= 0:
            raise ValueError("timeout 必须为正数")
        if grace_period < 0:
            raise ValueError("grace_period 不能为负数")
        self._target = target
        self._args = tuple(args)
        self._timeout = timeout
        self._grace_period = grace_period
        ctx = mp.get_context("spawn")
        self._parent_conn, self._child_conn = ctx.Pipe(duplex=False)
        self._process: mp.Process | None = None
        self._started = False
        self._closed = False

    def _spawn(self) -> None:
        """创建未启动的 spawn 子进程（daemon=False，父进程显式 join 回收）。"""

        ctx = mp.get_context("spawn")
        self._process = ctx.Process(
            target=_child_entry,
            args=(self._child_conn, self._target, self._args),
            daemon=False,
        )

    def run(self) -> Any:
        """一站式执行：start→join(deadline)→超时则 terminate→grace→kill→reap→close。

        返回:
            target 在子进程内返回的结果。

        异常:
            SubprocessTimeoutError: deadline 内未完成，子进程已被杀并回收。
            SubprocessExecutionError: 子进程执行异常或无结果崩溃。
            RuntimeError: 实例已 start() 或已 run() 时重复调用。
        """

        if self._started:
            raise RuntimeError("InterruptibleProcess 已 start/run，禁止重复 run")
        self._started = True
        self._spawn()
        self._process.start()
        self._process.join(self._timeout)
        if self._process.is_alive():
            self._process.terminate()
            time.sleep(self._grace_period)
            self._process.kill()
            self._process.join(DEFAULT_JOIN_AFTER_KILL_SECONDS)
            self.close()
            raise SubprocessTimeoutError(
                f"子进程在 {self._timeout} 秒内未完成，已 terminate→kill 回收"
            )
        try:
            return self._receive_result(timeout=DEFAULT_JOIN_AFTER_KILL_SECONDS)
        finally:
            self.close()

    def _receive_result(self, *, timeout: float) -> Any:
        """从管道回收单次 envelope；异常/崩溃映射为 SubprocessExecutionError。"""

        if not self._parent_conn.poll(timeout):
            raise SubprocessExecutionError("子进程未返回结果")
        try:
            envelope = self._parent_conn.recv()
        except (EOFError, OSError) as exc:
            raise SubprocessExecutionError("子进程未返回结果") from exc
        kind, payload = envelope
        if kind == "error":
            child_type, child_message = payload
            raise SubprocessExecutionError(
                f"子进程执行异常: {child_type}",
                child_type=child_type,
                child_message=child_message,
            )
        if kind != "ok":
            raise SubprocessExecutionError("子进程返回未知 envelope")
        return payload

    def start(self) -> None:
        """启动子进程；run() 与该调用互斥（先 start 再 run 抛 RuntimeError）。"""

        self._started = True
        self._spawn()
        self._process.start()

    def join(self, timeout: float | None = None) -> None:
        """等待子进程退出，最多等待 timeout 秒。"""

        self._process.join(timeout)

    def terminate(self) -> None:
        """向子进程发送 SIGTERM。"""

        self._process.terminate()

    def kill(self) -> None:
        """向子进程发送 SIGKILL。"""

        self._process.kill()

    def close(self) -> None:
        """关闭内部进程对象与管道端点；幂等，重复调用不抛。"""

        if self._closed:
            return
        self._closed = True
        process = self._process
        if process is not None and not process.is_alive():
            process.close()
        self._parent_conn.close()
        self._child_conn.close()

    def is_alive(self) -> bool:
        """返回子进程是否仍在运行。"""

        return self._process.is_alive()


def run_in_subprocess(
    target: Callable[..., Any],
    args: tuple = (),
    *,
    timeout: float,
    grace_period: float = DEFAULT_TERMINATE_GRACE_SECONDS,
) -> Any:
    """薄封装：创建 InterruptibleProcess 并一站式 run()。

    参数:
        target: 必须可由 spawn 按引用序列化的顶层可调用。
        args: 传给 target 的位置参数。
        timeout: 硬 deadline 秒数，必须为正数。
        grace_period: terminate 后等待 kill 的宽限秒数，不能为负数。

    返回:
        target 在子进程内返回的结果。

    异常:
        SubprocessTimeoutError: deadline 内未完成。
        SubprocessExecutionError: 子进程执行异常或无结果崩溃。
        ValueError: timeout<=0 或 grace_period<0。
    """

    return InterruptibleProcess(
        target=target,
        args=args,
        timeout=timeout,
        grace_period=grace_period,
    ).run()
