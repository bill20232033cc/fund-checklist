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
