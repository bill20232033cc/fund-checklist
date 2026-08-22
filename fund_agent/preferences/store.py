"""偏好存储（Slice P1：flomo-import SQLite 持久化；Slice P2：问卷结果）。

使用标准库 sqlite3；库文件位于 work_dir/preferences/preferences.db。
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Sequence

from fund_agent.preferences.flomo_parser import FlomoMemo
from fund_agent.preferences.note_parser import ThoughtNote
from fund_agent.preferences.questionnaire import QuestionnaireResult
from fund_agent.preferences.snapshot import PreferenceSnapshot

_SCHEMA = """
CREATE TABLE IF NOT EXISTS memos (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    content TEXT NOT NULL,
    images_json TEXT NOT NULL DEFAULT '[]',
    source TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS imports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_path TEXT NOT NULL,
    fingerprint TEXT NOT NULL UNIQUE,
    exported_at TEXT,
    memo_count INTEGER NOT NULL,
    imported_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS questionnaire_results (
    id TEXT PRIMARY KEY,
    answered_at TEXT NOT NULL,
    dimension_scores_json TEXT NOT NULL,
    total_score REAL NOT NULL,
    risk_level TEXT NOT NULL,
    answers_json TEXT NOT NULL,
    disclaimer TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS preference_snapshots (
    id TEXT PRIMARY KEY,
    quarter TEXT NOT NULL,
    created_at TEXT NOT NULL,
    questionnaire_result_id TEXT,
    behavior_summary_json TEXT NOT NULL,
    reflection_json TEXT NOT NULL,
    disclaimer TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS thought_records (
    id TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    title TEXT NOT NULL,
    created_at TEXT NOT NULL,
    status TEXT NOT NULL,
    content TEXT NOT NULL,
    source TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS note_imports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_path TEXT NOT NULL,
    fingerprint TEXT NOT NULL UNIQUE,
    exported_at TEXT NOT NULL,
    record_count INTEGER NOT NULL,
    imported_at TEXT NOT NULL
);
"""

_LOCAL_TZ = timezone(timedelta(hours=8))


class PreferencesStoreError(Exception):
    """偏好存储打开/写入失败（unavailable 语义）。

    参数:
        message: 面向调用方的中文错误说明。
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


@dataclass(frozen=True)
class ImportResult:
    """一次导入的结果。

    参数:
        imported: 是否新写入 memos/imports。
        cached: 是否命中已存在指纹（不覆盖）。
        memo_count: 本次导入的 memo 数（cached 时为已有条数）。
        image_count: 本次导入的图片引用总数；cached 时为 0。
        imported_at: imports 记录的导入时间（ISO8601 +08:00）。
    """

    imported: bool
    cached: bool
    memo_count: int
    image_count: int = 0
    record_count: int | None = None
    imported_at: str | None = None


@dataclass(frozen=True)
class ThoughtNoteRow:
    """智慧笔记记录表（thought_records）的一行。

    参数:
        id: 记录主键（note-<导出日期 YYYYMMDD>-<类别>-<序号>）。
        category: 类别 key（analysis / roundtable / incubator / structure）。
        title: 记录标题。
        created_at: 分析时间（ISO8601 +08:00）。
        status: 状态原文。
        content: 记录全文（Markdown 纯文本）。
        source: 导出文件相对名。
    """

    id: str
    category: str
    title: str
    created_at: str
    status: str
    content: str
    source: str


@dataclass(frozen=True)
class QuestionnaireResultRow:
    """问卷结果表的一行。

    参数:
        id: 结果记录主键（答题时间，冲突时追加序号）。
        answered_at: 答题时间（ISO8601 +08:00）。
        dimension_scores: 五维子分。
        total_score: 总分（0-100）。
        risk_level: 辅助 C1-C5 风险等级。
        answers: 逐题答案快照。
        disclaimer: 输出免责声明。
    """

    id: str
    answered_at: str
    dimension_scores: dict[str, float]
    total_score: float
    risk_level: str
    answers: dict[str, int]
    disclaimer: str


def _now_iso() -> str:
    """返回当前本地时间（+08:00）的 ISO8601 字符串。"""

    return datetime.now(_LOCAL_TZ).isoformat(timespec="seconds")


def _compute_fingerprint(exported_at: str | None, memos: Sequence[FlomoMemo]) -> str:
    """计算导入指纹：exported_at + 全部 memo 的 created_at + content 前 64 字符。"""

    material = (exported_at or "") + "".join(
        f"{memo.created_at}{memo.content[:64]}" for memo in memos
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _compute_note_fingerprint(exported_at: str, notes: Sequence[ThoughtNote]) -> str:
    """计算智慧笔记导入指纹：exported_at + 全部记录 title+created_at+content 前 64 字符。"""

    material = exported_at + "".join(
        f"{note.title}{note.created_at}{note.content[:64]}" for note in notes
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


class PreferencesStore:
    """偏好域 SQLite 存储。

    参数:
        connection: 已初始化的 sqlite3 连接。
        db_path: 数据库文件路径。
    """

    def __init__(self, connection: sqlite3.Connection, db_path: Path) -> None:
        self._conn = connection
        self.db_path = db_path

    def import_memos(
        self,
        memos: Sequence[FlomoMemo],
        *,
        source_path: str,
        exported_at: str | None,
    ) -> ImportResult:
        """幂等导入 memo 列表。

        参数:
            memos: 解析出的 memo 列表。
            source_path: 导出文件路径，记录于 imports.source_path。
            exported_at: 导出日期（YYYY-MM-DD），用于指纹与审计。

        返回:
            ImportResult；指纹已存在时 imported=False / cached=True，不覆盖。

        异常:
            PreferencesStoreError: SQLite 写入失败时抛出（unavailable 语义）。
        """

        fingerprint = _compute_fingerprint(exported_at, memos)
        try:
            with self._conn:
                existing = self._conn.execute(
                    "SELECT memo_count, imported_at FROM imports WHERE fingerprint = ?",
                    (fingerprint,),
                ).fetchone()
                if existing is not None:
                    return ImportResult(
                        imported=False,
                        cached=True,
                        memo_count=int(existing[0]),
                        imported_at=str(existing[1]),
                    )
                imported_at = _now_iso()
                self._conn.executemany(
                    "INSERT INTO memos (id, created_at, content, images_json, source) "
                    "VALUES (?, ?, ?, ?, ?)",
                    [
                        (
                            memo.id,
                            memo.created_at,
                            memo.content,
                            json.dumps(memo.images, ensure_ascii=False),
                            memo.source,
                        )
                        for memo in memos
                    ],
                )
                self._conn.execute(
                    "INSERT INTO imports (source_path, fingerprint, exported_at, memo_count, imported_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (source_path, fingerprint, exported_at, len(memos), imported_at),
                )
        except sqlite3.Error as exc:
            raise PreferencesStoreError(f"偏好数据库写入失败: {exc}") from exc
        return ImportResult(
            imported=True,
            cached=False,
            memo_count=len(memos),
            image_count=sum(len(memo.images) for memo in memos),
            imported_at=imported_at,
        )

    def import_notes(
        self,
        notes: Sequence[ThoughtNote],
        *,
        source_path: str,
        exported_at: str,
    ) -> ImportResult:
        """幂等导入智慧笔记记录列表。

        参数:
            notes: 解析出的 ThoughtNote 列表。
            source_path: 导出文件路径，记录于 note_imports.source_path。
            exported_at: 导出日期（YYYY-MM-DD），用于指纹与审计。

        返回:
            ImportResult；指纹已存在时 imported=False / cached=True，不覆盖。

        异常:
            PreferencesStoreError: SQLite 写入失败时抛出（unavailable 语义）。
        """

        fingerprint = _compute_note_fingerprint(exported_at, notes)
        try:
            with self._conn:
                existing = self._conn.execute(
                    "SELECT record_count, imported_at FROM note_imports WHERE fingerprint = ?",
                    (fingerprint,),
                ).fetchone()
                if existing is not None:
                    count = int(existing[0])
                    return ImportResult(
                        imported=False,
                        cached=True,
                        memo_count=count,
                        record_count=count,
                        imported_at=str(existing[1]),
                    )
                imported_at = _now_iso()
                self._conn.executemany(
                    "INSERT INTO thought_records "
                    "(id, category, title, created_at, status, content, source) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    [
                        (
                            note.id,
                            note.category,
                            note.title,
                            note.created_at,
                            note.status,
                            note.content,
                            note.source,
                        )
                        for note in notes
                    ],
                )
                self._conn.execute(
                    "INSERT INTO note_imports "
                    "(source_path, fingerprint, exported_at, record_count, imported_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (source_path, fingerprint, exported_at, len(notes), imported_at),
                )
        except sqlite3.Error as exc:
            raise PreferencesStoreError(f"偏好数据库写入失败: {exc}") from exc
        return ImportResult(
            imported=True,
            cached=False,
            memo_count=len(notes),
            record_count=len(notes),
            imported_at=imported_at,
        )

    def close(self) -> None:
        """关闭数据库连接。"""

        self._conn.close()


def save_questionnaire_result(store: PreferencesStore, result: QuestionnaireResult) -> str:
    """写入一次问卷评分结果，返回结果记录 id。

    参数:
        store: PreferencesStore 实例。
        result: 评分结果（QuestionnaireResult）。

    返回:
        结果记录 id（answered_at；同秒重复时追加 -N 序号）。

    异常:
        PreferencesStoreError: SQLite 写入失败时抛出（unavailable 语义）。
    """

    record_id = result.answered_at
    attempt = 0
    while True:
        candidate = record_id if attempt == 0 else f"{record_id}-{attempt + 1}"
        try:
            with store._conn:
                store._conn.execute(
                    "INSERT INTO questionnaire_results "
                    "(id, answered_at, dimension_scores_json, total_score, risk_level, answers_json, disclaimer) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        candidate,
                        result.answered_at,
                        json.dumps(result.dimension_scores, ensure_ascii=False),
                        result.total_score,
                        result.risk_level,
                        json.dumps(result.answers, ensure_ascii=False),
                        result.disclaimer,
                    ),
                )
            return candidate
        except sqlite3.IntegrityError:
            attempt += 1
            if attempt >= 100:
                raise PreferencesStoreError("问卷结果写入失败: 同秒记录过多") from None
        except sqlite3.Error as exc:
            raise PreferencesStoreError(f"问卷结果写入失败: {exc}") from exc


def list_questionnaire_results(store: PreferencesStore) -> list[QuestionnaireResultRow]:
    """按答题时间倒序返回全部问卷结果。

    参数:
        store: PreferencesStore 实例。

    返回:
        QuestionnaireResultRow 列表（按 answered_at 倒序）。

    异常:
        PreferencesStoreError: SQLite 读取失败时抛出（unavailable 语义）。
    """

    try:
        rows = store._conn.execute(
            "SELECT id, answered_at, dimension_scores_json, total_score, risk_level, answers_json, disclaimer "
            "FROM questionnaire_results ORDER BY answered_at DESC"
        ).fetchall()
    except sqlite3.Error as exc:
        raise PreferencesStoreError(f"问卷结果读取失败: {exc}") from exc
    return [
        QuestionnaireResultRow(
            id=str(row[0]),
            answered_at=str(row[1]),
            dimension_scores=json.loads(row[2]),
            total_score=float(row[3]),
            risk_level=str(row[4]),
            answers=json.loads(row[5]),
            disclaimer=str(row[6]),
        )
        for row in rows
    ]


def open_preferences_store(work_dir: Path) -> PreferencesStore:
    """打开（必要时创建）偏好数据库。

    参数:
        work_dir: 工作目录；库文件写入 work_dir/preferences/preferences.db。

    返回:
        已初始化表结构的 PreferencesStore。

    异常:
        PreferencesStoreError: 目录创建或 SQLite 打开失败时抛出（unavailable 语义）。
    """

    prefs_dir = Path(work_dir) / "preferences"
    connection: sqlite3.Connection | None = None
    try:
        prefs_dir.mkdir(parents=True, exist_ok=True)
        db_path = prefs_dir / "preferences.db"
        connection = sqlite3.connect(db_path)
        connection.executescript(_SCHEMA)
        connection.commit()
    except (OSError, sqlite3.Error) as exc:
        if connection is not None:
            connection.close()
        raise PreferencesStoreError(f"偏好数据库打开失败: {exc}") from exc
    return PreferencesStore(connection=connection, db_path=db_path)


def query_memos_by_date_range(
    store: PreferencesStore,
    start: date,
    end: date,
) -> list[dict[str, object]]:
    """按 created_at 日期范围查询 memos（含起点、不含终点）。

    参数:
        store: PreferencesStore 实例。
        start: 起始日期（含）。
        end: 结束日期（不含）。

    返回:
        memo 行字典列表（created_at/content/images/source，按 created_at 升序）。

    异常:
        PreferencesStoreError: SQLite 读取失败时抛出（unavailable 语义）。
    """

    try:
        rows = store._conn.execute(
            "SELECT created_at, content, images_json, source FROM memos "
            "WHERE created_at >= ? AND created_at < ? ORDER BY created_at",
            (start.isoformat(), end.isoformat()),
        ).fetchall()
    except sqlite3.Error as exc:
        raise PreferencesStoreError(f"偏好数据库读取失败: {exc}") from exc
    return [
        {
            "created_at": str(row[0]),
            "content": str(row[1]),
            "images": json.loads(row[2]),
            "source": str(row[3]),
        }
        for row in rows
    ]


def latest_questionnaire_result(
    store: PreferencesStore,
    quarter_end: date,
) -> QuestionnaireResultRow | None:
    """返回不晚于季度末的最新一次问卷结果。

    参数:
        store: PreferencesStore 实例。
        quarter_end: 季度末日期（含当天，按 answered_at 比较）。

    返回:
        最近一次 QuestionnaireResultRow；无结果时返回 None。

    异常:
        PreferencesStoreError: SQLite 读取失败时抛出（unavailable 语义）。
    """

    try:
        row = store._conn.execute(
            "SELECT id, answered_at, dimension_scores_json, total_score, risk_level, answers_json, disclaimer "
            "FROM questionnaire_results "
            "WHERE answered_at <= ? ORDER BY answered_at DESC LIMIT 1",
            (f"{quarter_end.isoformat()}T23:59:59",),
        ).fetchone()
    except sqlite3.Error as exc:
        raise PreferencesStoreError(f"问卷结果读取失败: {exc}") from exc
    if row is None:
        return None
    return QuestionnaireResultRow(
        id=str(row[0]),
        answered_at=str(row[1]),
        dimension_scores=json.loads(row[2]),
        total_score=float(row[3]),
        risk_level=str(row[4]),
        answers=json.loads(row[5]),
        disclaimer=str(row[6]),
    )


def save_snapshot(store: PreferencesStore, snapshot: PreferenceSnapshot) -> str:
    """写入一份季度偏好快照，返回记录 id。

    参数:
        store: PreferencesStore 实例。
        snapshot: 偏好快照（PreferenceSnapshot）。

    返回:
        快照记录 id（snapshot-<quarter>-<created_at>；同秒重复时追加序号）。

    异常:
        PreferencesStoreError: SQLite 写入失败时抛出（unavailable 语义）。
    """

    base_id = f"snapshot-{snapshot.quarter}-{snapshot.created_at}"
    record_id = base_id
    attempt = 0
    while True:
        if attempt > 0:
            record_id = f"{base_id}-{attempt + 1}"
        try:
            with store._conn:
                store._conn.execute(
                    "INSERT INTO preference_snapshots "
                    "(id, quarter, created_at, questionnaire_result_id, behavior_summary_json, reflection_json, disclaimer) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        record_id,
                        snapshot.quarter,
                        snapshot.created_at,
                        snapshot.baseline.answered_at if snapshot.baseline is not None else None,
                        json.dumps(
                            [
                                {
                                    "created_at": evidence.created_at,
                                    "content": evidence.content,
                                    "hit_keywords": evidence.hit_keywords,
                                }
                                for evidence in snapshot.behavior_summary
                            ],
                            ensure_ascii=False,
                        ),
                        json.dumps(snapshot.reflection, ensure_ascii=False),
                        snapshot.disclaimer,
                    ),
                )
            return record_id
        except sqlite3.IntegrityError:
            attempt += 1
            if attempt >= 100:
                raise PreferencesStoreError("偏好快照写入失败: 同秒记录过多") from None
        except sqlite3.Error as exc:
            raise PreferencesStoreError(f"偏好快照写入失败: {exc}") from exc
