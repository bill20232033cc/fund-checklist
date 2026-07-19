"""Prompt 模板渲染与装配模块。

参照 dayu prompting/ 模块设计，负责：
- 从文件系统加载 .md 模板文件
- {{ variable }} 变量替换
- <when_missing field> / </when_missing> 条件块渲染
- 输出最终 prompt 文本

不依赖 Engine、LLM 运行时或业务逻辑。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class PromptRenderError(Exception):
    """Prompt 模板渲染错误。"""


# 条件块正则（模块级编译）
_WHEN_MISSING_OPEN = re.compile(r"<when_missing\s+([a-zA-Z_][a-zA-Z0-9_]*)>")
_WHEN_MISSING_CLOSE = re.compile(r"</when_missing>")
_VERSION_COMMENT = re.compile(r"<!--\s*version:\s*(.+?)\s*-->")
_VARIABLE_PATTERN = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")


@dataclass(frozen=True)
class ComposedPrompt:
    """PromptComposer 输出。

    参数:
        template_name: 模板文件名。
        template_version: 模板版本号（从文件头注释提取）。
        system_message: 渲染后的 system prompt 文本。
        missing_variables: 未提供的变量列表（用于调试）。
    """
    template_name: str
    template_version: str
    system_message: str
    missing_variables: tuple[str, ...] = ()


@dataclass
class PromptComposer:
    """Prompt 模板渲染器。

    参数:
        template_dir: 模板文件目录（fund_agent/service/prompts/）。
    """
    template_dir: Path

    def compose(
        self,
        template_name: str,
        context: dict[str, Any],
        *,
        strict: bool = False,
    ) -> ComposedPrompt:
        """加载模板并渲染。

        参数:
            template_name: 模板文件名（如 "ch3.md"）。
            context: 变量上下文（如 {"data_table": "...", "fund_name": "..."}）。
            strict: True 时变量缺失抛异常，False 时保留原始 {{ var }} 标记。

        返回:
            ComposedPrompt。

        异常:
            PromptRenderError: 模板文件不存在或 strict 模式下变量缺失。
        """
        template_path = self.template_dir / template_name
        if not template_path.exists():
            raise PromptRenderError(f"模板文件不存在: {template_path}")

        raw_template = template_path.read_text(encoding="utf-8")

        # 提取版本号
        version_match = _VERSION_COMMENT.search(raw_template)
        version = version_match.group(1).strip() if version_match else "unknown"

        # 移除版本注释行（不参与渲染）
        template_text = _VERSION_COMMENT.sub("", raw_template, count=1).strip()

        # 处理 <when_missing> 条件块
        template_text = _render_when_missing_blocks(template_text, context)

        # 变量替换
        result, missing = _replace_variables(template_text, context, strict=strict)

        return ComposedPrompt(
            template_name=template_name,
            template_version=version,
            system_message=result,
            missing_variables=tuple(missing),
        )


def _render_when_missing_blocks(template: str, context: dict[str, Any]) -> str:
    """渲染 <when_missing field> / </when_missing> 条件块。

    当 field 在 context 中缺失或为空字符串/None 时，保留块内容；
    否则丢弃块内容。
    """
    result_parts: list[str] = []
    position = 0

    while position < len(template):
        open_match = _WHEN_MISSING_OPEN.search(template, position)
        if open_match is None:
            result_parts.append(template[position:])
            break

        # 添加 open tag 之前的内容
        result_parts.append(template[position:open_match.start()])

        field_name = open_match.group(1)

        # 找对应的 close tag
        close_match = _WHEN_MISSING_CLOSE.search(template, open_match.end())
        if close_match is None:
            raise PromptRenderError(
                f"<when_missing {field_name}> 缺少对应的 </when_missing>"
            )

        block_content = template[open_match.end():close_match.start()]

        # 判断 field 是否缺失
        value = context.get(field_name)
        is_missing = value is None or (isinstance(value, str) and not value.strip())

        if is_missing:
            # 递归处理嵌套条件块
            result_parts.append(_render_when_missing_blocks(block_content, context))

        position = close_match.end()

    return "".join(result_parts)


def _replace_variables(
    template: str,
    context: dict[str, Any],
    *,
    strict: bool = False,
) -> tuple[str, list[str]]:
    """替换 {{ variable }} 变量。

    参数:
        template: 模板文本。
        context: 变量上下文。
        strict: True 时变量缺失抛异常。

    返回:
        (替换后的文本, 缺失变量列表)。
    """
    missing: list[str] = []

    def replacer(match: re.Match) -> str:
        var_name = match.group(1)
        if var_name in context:
            value = context[var_name]
            return str(value) if value is not None else ""
        else:
            missing.append(var_name)
            if strict:
                raise PromptRenderError(f"模板变量缺失: {{{{{var_name}}}}}")
            return match.group(0)  # 保留原始标记

    result = _VARIABLE_PATTERN.sub(replacer, template)
    return result, missing


# 合同解析：从模板 HTML 注释中提取 CHAPTER_CONTRACT
_CHAPTER_CONTRACT_PATTERN = re.compile(
    r"<!--\s*\n?CHAPTER_CONTRACT\s*\n(.*?)\nEND_CHAPTER_CONTRACT\s*\n?\s*-->",
    re.DOTALL,
)


def extract_contract_from_template(template_text: str) -> dict[str, Any] | None:
    """从模板文本中提取 CHAPTER_CONTRACT HTML 注释块。

    参数:
        template_text: 模板原始文本（含 HTML 注释）。

    返回:
        合同字段字典；未找到时返回 None。

    异常:
        无（解析失败时返回 None）。
    """
    match = _CHAPTER_CONTRACT_PATTERN.search(template_text)
    if not match:
        return None

    raw_yaml = match.group(1).strip()
    return _parse_contract_yaml(raw_yaml)


def _strip_yaml_quotes(s: str) -> str:
    """去除 YAML 值的外层引号。"""
    s = s.strip()
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        return s[1:-1]
    if len(s) >= 2 and s[0] == "'" and s[-1] == "'":
        return s[1:-1]
    return s


def _parse_contract_yaml(raw: str) -> dict[str, Any]:
    """解析合同 YAML-like 文本。

    支持的格式：
    - scalar: key: value
    - list: key:\\n  - item1\\n  - item2
    - nested list of dicts: key:\\n  - name: x\\n    formula: y

    参数:
        raw: YAML-like 文本。

    返回:
        解析后的字典。
    """
    result: dict[str, Any] = {}
    lines = raw.split("\n")
    i = 0

    while i < len(lines):
        line = lines[i]
        # 跳过空行
        if not line.strip():
            i += 1
            continue

        # 判断缩进级别
        indent = len(line) - len(line.lstrip())

        # 顶层 key: value
        if indent == 0 and ":" in line:
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip()

            if value:
                # scalar value
                result[key] = _strip_yaml_quotes(value)
                i += 1
            else:
                # list value (后续行以 - 开头)
                items: list[Any] = []
                i += 1
                while i < len(lines):
                    next_line = lines[i]
                    next_stripped = next_line.strip()
                    if not next_stripped:
                        i += 1
                        continue
                    next_indent = len(next_line) - len(next_line.lstrip())
                    if next_indent == 0 and ":" in next_line:
                        break  # 下一个顶层 key
                    if next_stripped.startswith("- "):
                        # list item
                        item_content = next_stripped[2:].strip()
                        # 检查是否是 dict item（后续行有更深缩进的 key: value）
                        sub_items: dict[str, str] = {}
                        if ":" in item_content:
                            sub_key, _, sub_val = item_content.partition(":")
                            sub_items[sub_key.strip()] = _strip_yaml_quotes(sub_val)
                            # 读取更深缩进的行
                            j = i + 1
                            while j < len(lines):
                                sub_line = lines[j]
                                sub_stripped = sub_line.strip()
                                if not sub_stripped:
                                    j += 1
                                    continue
                                sub_indent = len(sub_line) - len(sub_line.lstrip())
                                if sub_indent <= next_indent:
                                    break
                                if ":" in sub_stripped:
                                    sk, _, sv = sub_stripped.partition(":")
                                    sub_items[sk.strip()] = _strip_yaml_quotes(sv)
                                j += 1
                            if len(sub_items) > 1:
                                items.append(sub_items)
                            else:
                                items.append(_strip_yaml_quotes(item_content))
                            i = j
                        else:
                            items.append(_strip_yaml_quotes(item_content))
                            i += 1
                    else:
                        break
                result[key] = items
        else:
            i += 1

    return result


def load_contract_from_file(template_path: Path) -> dict[str, Any] | None:
    """从模板文件中提取 CHAPTER_CONTRACT。

    参数:
        template_path: 模板文件路径。

    返回:
        合同字段字典；未找到或文件不存在时返回 None。

    异常:
        无。
    """
    if not template_path.exists():
        return None
    text = template_path.read_text(encoding="utf-8")
    return extract_contract_from_template(text)
