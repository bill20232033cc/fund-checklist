"""SessionStore — Session 的 filesystem JSON 持久化（原子写入）。

参考 FilesystemReportRepository._write_catalog 的临时文件 + os.replace 模式。
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

from fund_agent.service.session_models import (
    EpisodeSummary,
    PinnedState,
    Session,
    Turn,
)

_LABELS_FILENAME = "labels.json"
_SESSION_SCHEMA_VERSION = 1


class SessionStore:
    """Session 的 filesystem JSON 持久化存储。

    目录结构:
        {work_dir}/sessions/{session_id}.json  — 会话文件
        {work_dir}/sessions/labels.json       — label ↔ session_id 映射
    """

    def __init__(self, root: Path) -> None:
        """初始化 store。

        参数:
            root: sessions 目录路径。
        """
        self._root = Path(root)
        self._labels_path = self._root / _LABELS_FILENAME

    # ── public API ──────────────────────────────────────────────

    def create(self, fund_code: str, label: str | None = None) -> Session:
        """创建新会话并持久化。

        参数:
            fund_code: 基金代码。
            label: 可选用户标签，用于恢复。

        返回:
            已持久化的 Session。
        """
        session = Session.create(fund_code=fund_code, label=label)
        self.save(session)
        if label:
            self._add_label_mapping(session.session_id, label)
        return session

    def load(self, session_id_or_label: str) -> Session:
        """加载会话。

        先尝试按 session_id 加载，失败后尝试按 label 查找。
        """
        session_id = self._resolve_session_id(session_id_or_label)
        json_path = self._session_path(session_id)
        if not json_path.exists():
            raise FileNotFoundError(f"会话不存在: {session_id}")
        return self._load_from_path(json_path)

    def save(self, session: Session) -> None:
        """原子写入 session 到 JSON 文件。"""
        self._root.mkdir(parents=True, exist_ok=True)
        json_path = self._session_path(session.session_id)
        payload = self._session_to_json(session)
        text = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)
        temporary = self._root / f".{session.session_id}.{uuid4().hex}.tmp"
        try:
            with open(temporary, "w", encoding="utf-8") as f:
                f.write(text)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temporary, json_path)
        finally:
            if temporary.exists():
                temporary.unlink(missing_ok=True)

    def list_sessions(self, label: str | None = None) -> list[dict[str, object]]:
        """列出所有会话摘要（不加载完整 turns）。

        参数:
            label: 可选，按 label 过滤；None 时返回全部。
        """
        if not self._root.exists():
            return []
        result: list[dict[str, object]] = []
        for json_file in sorted(self._root.glob("*.json")):
            if json_file.name == _LABELS_FILENAME:
                continue
            try:
                data = json.loads(json_file.read_text(encoding="utf-8"))
                entry = {
                    "session_id": data.get("session_id", ""),
                    "label": data.get("label"),
                    "status": data.get("status", "UNKNOWN"),
                    "fund_code": data.get("pinned_state", {}).get("fund_code", ""),
                    "turn_count": len(data.get("turns", [])),
                    "created_at": data.get("created_at", ""),
                }
                if label is not None:
                    entry_label = data.get("label")
                    if entry_label != label:
                        continue
                result.append(entry)
            except (json.JSONDecodeError, OSError):
                continue
        return result

    def delete(self, session_id: str) -> None:
        """删除会话及关联 label 映射。"""
        json_path = self._session_path(session_id)
        if json_path.exists():
            json_path.unlink()
        self._remove_label_mapping(session_id)

    def set_label(self, session_id: str, label: str) -> None:
        """为已存在的会话设置或更新标签。

        参数:
            session_id: 会话 ID。
            label: 新标签名。
        """
        # 先移除旧 label 映射（如果存在且不同）
        labels = self._read_labels()
        old_label = labels.get("by_id", {}).get(session_id)
        if old_label and old_label != label:
            labels.get("by_label", {}).pop(old_label, None)
            labels.get("by_id", {}).pop(session_id, None)
            self._write_labels(labels)
        # 写入新映射
        self._add_label_mapping(session_id, label)

    # ── internal ────────────────────────────────────────────────

    def _session_path(self, session_id: str) -> Path:
        return self._root / f"{session_id}.json"

    def _resolve_session_id(self, session_id_or_label: str) -> str:
        """尝试将 label 解析为 session_id。"""
        json_path = self._session_path(session_id_or_label)
        if json_path.exists():
            return session_id_or_label
        # 尝试 label 查找
        mapping = self._read_labels()
        by_label = mapping.get("by_label", {})
        if session_id_or_label in by_label:
            return str(by_label[session_id_or_label])
        return session_id_or_label

    def _load_from_path(self, json_path: Path) -> Session:
        data = json.loads(json_path.read_text(encoding="utf-8"))
        return self._session_from_json(data)

    # ── JSON 序列化 ─────────────────────────────────────────────

    @staticmethod
    def _session_to_json(session: Session) -> dict:
        return {
            "schema_version": _SESSION_SCHEMA_VERSION,
            "session_id": session.session_id,
            "label": session.label,
            "status": session.status,
            "pinned_state": {
                "fund_code": session.pinned_state.fund_code,
                "available_document_ids": list(session.pinned_state.available_document_ids),
                "active_document_id": session.pinned_state.active_document_id,
                "active_year": session.pinned_state.active_year,
                "user_constraints": session.pinned_state.user_constraints,
            },
            "turns": [
                {
                    "role": t.role,
                    "content": t.content,
                    "citations": list(t.citations),
                    "tool_trace": list(t.tool_trace),
                    "timestamp": t.timestamp,
                }
                for t in session.turns
            ],
            "episode_summaries": [
                {
                    "episode_id": e.episode_id,
                    "start_turn_id": e.start_turn_id,
                    "end_turn_id": e.end_turn_id,
                    "title": e.title,
                    "goal": e.goal,
                    "confirmed_facts": list(e.confirmed_facts),
                    "open_questions": list(e.open_questions),
                }
                for e in session.episode_summaries
            ],
            "created_at": session.created_at,
            "updated_at": session.updated_at,
        }

    @staticmethod
    def _session_from_json(data: dict) -> Session:
        ps_raw = data.get("pinned_state", {})
        pinned_state = PinnedState(
            fund_code=ps_raw.get("fund_code", ""),
            available_document_ids=tuple(ps_raw.get("available_document_ids", [])),
            active_document_id=ps_raw.get("active_document_id"),
            active_year=ps_raw.get("active_year"),
            user_constraints=ps_raw.get("user_constraints", {}),
        )
        turns = tuple(
            Turn(
                role=t.get("role", "user"),
                content=t.get("content", ""),
                citations=tuple(t.get("citations", [])),
                tool_trace=tuple(t.get("tool_trace", [])),
                timestamp=t.get("timestamp", ""),
            )
            for t in data.get("turns", [])
        )
        episodes = tuple(
            EpisodeSummary(
                episode_id=e.get("episode_id", ""),
                start_turn_id=e.get("start_turn_id", 0),
                end_turn_id=e.get("end_turn_id", 0),
                title=e.get("title", ""),
                goal=e.get("goal", ""),
                confirmed_facts=tuple(e.get("confirmed_facts", [])),
                open_questions=tuple(e.get("open_questions", [])),
            )
            for e in data.get("episode_summaries", [])
        )
        return Session(
            session_id=data["session_id"],
            label=data.get("label"),
            status=data.get("status", "ACTIVE"),
            pinned_state=pinned_state,
            turns=turns,
            episode_summaries=episodes,
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
        )

    # ── label 双向映射 ──────────────────────────────────────────

    def _read_labels(self) -> dict:
        if not self._labels_path.exists():
            return {}
        try:
            return json.loads(self._labels_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def _write_labels(self, labels: dict) -> None:
        self._root.mkdir(parents=True, exist_ok=True)
        text = json.dumps(labels, ensure_ascii=False, sort_keys=True, indent=2)
        temporary = self._root / f".{_LABELS_FILENAME}.{uuid4().hex}.tmp"
        try:
            with open(temporary, "w", encoding="utf-8") as f:
                f.write(text)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temporary, self._labels_path)
        finally:
            if temporary.exists():
                temporary.unlink(missing_ok=True)

    def _add_label_mapping(self, session_id: str, label: str) -> None:
        labels = self._read_labels()
        labels.setdefault("by_label", {})[label] = session_id
        labels.setdefault("by_id", {})[session_id] = label
        self._write_labels(labels)

    def _remove_label_mapping(self, session_id: str) -> None:
        labels = self._read_labels()
        label = labels.get("by_id", {}).get(session_id)
        if label:
            labels.get("by_label", {}).pop(label, None)
        labels.get("by_id", {}).pop(session_id, None)
        if labels:
            self._write_labels(labels)
        elif self._labels_path.exists():
            self._labels_path.unlink()
