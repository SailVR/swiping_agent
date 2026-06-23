"""
SQL 安全校验器

白名单机制：只允许 SELECT / WITH ... SELECT / EXPLAIN 等只读查询通过。
在 MCP 服务端（执行层）和 SQLAgent（调用层）双重拦截，防止 LLM 幻觉生成的
DML/DDL 语句破坏数据库。

支持以下检查：
- 语句类型白名单（只读）
- 多语句检测（; 分隔符劫持）
- 危险关键字 / PRAGMA / ATTACH DATABASE 检测
- 注释剥离后校验，防止关键字隐藏在注释中
"""

import re
from typing import Tuple

# ─── 配置 ────────────────────────────────────────────────

# 允许的语句前缀（严格白名单）
ALLOWED_STATEMENT_PREFIXES = (
    "select",
    "explain",
    "explain query plan",
    "with",
)

# 明确禁止的关键字 —— 出现在 SELECT 以外的独立语句中时直接拒绝
DML_DDL_KEYWORDS = (
    "insert", "update", "delete", "drop", "alter", "create",
    "truncate", "replace", "reindex", "vacuum",
)

# 始终禁止的操作（即使出现在 SELECT 内部也会被拦截）
BLOCKED_PATTERNS: list[re.Pattern] = [
    re.compile(r'\battach\s+database\b', re.IGNORECASE),
    re.compile(r'\bdetach\s+database\b', re.IGNORECASE),
    re.compile(r'\bpragma\b', re.IGNORECASE),
]

# ─── 核心校验 ───────────────────────────────────────────


def normalize_sql(sql: str) -> str:
    """规范化 SQL：去除字符串字面量、注释，使关键字检测不被内容干扰。"""
    s = sql

    # 去除单引号字符串
    s = re.sub(r"'(?:[^'\\]|\\.)*'", '', s)
    # 去除双引号字符串（SQLite 标识符）
    s = re.sub(r'"(?:[^"\\]|\\.)*"', '', s)
    # 去除 SQL 行注释
    s = re.sub(r'--.*$', '', s, flags=re.MULTILINE)
    # 去除 SQL 块注释
    s = re.sub(r'/\*[\s\S]*?\*/', '', s)
    # 合并空白
    s = re.sub(r'\s+', ' ', s).strip()

    return s


def _get_first_statement(sql: str) -> str:
    """提取第一个有效语句（用于检测多语句执行）。"""
    # 移除字符串内容 & 注释后再按 ; 分割
    normalized = normalize_sql(sql)
    # 按分号分割，滤掉空串
    parts = [p.strip() for p in normalized.split(';') if p.strip()]

    return parts[0] if parts else ""


def _detect_multi_statement(sql: str) -> bool:
    """检测是否包含多条语句（; 分割攻击）。"""
    # 把字符串和注释去掉后再按分号数
    cleaned = normalize_sql(sql)
    parts = [p.strip() for p in cleaned.split(';') if p.strip()]
    return len(parts) > 1


def _is_read_only(first_stmt: str) -> bool:
    """判断第一个语句是否为只读查询。"""
    if not first_stmt:
        return False
    return first_stmt.lower().startswith(ALLOWED_STATEMENT_PREFIXES)


def _has_blocked_patterns(sql: str) -> Tuple[bool, str]:
    """检测是否包含始终禁止的操作模式。"""
    for pattern in BLOCKED_PATTERNS:
        match = pattern.search(sql)
        if match:
            return True, f"禁止的操作: '{match.group()}'"
    return False, ""


def _has_dml_ddl_after_select(first_stmt: str) -> bool:
    """检测 SELECT 后面是否跟着 DML/DDL（多语句劫持）。"""
    # normalize_sql 已经处理了字符串内容，直接用 lower 匹配
    lower = first_stmt.lower()
    for kw in DML_DDL_KEYWORDS:
        # 确保这个关键字是以单词边界出现的（而不是列名的一部分）
        if re.search(r'\b' + re.escape(kw) + r'\b', lower):
            return True
    return False


def validate_sql(sql: str) -> Tuple[bool, str]:
    """SQL 安全校验主入口。

    Args:
        sql: 用户或 LLM 提交的原始 SQL 语句。

    Returns:
        (is_valid, reason) —— True 表示通过，False 表示拒绝。
        reason 在拒绝时包含人类可读的原因。
    """
    if not sql or not sql.strip():
        return False, "SQL 语句为空"

    # 1. 始终禁止的模式（即使是 SELECT 内部的 PRAGMA / ATTACH）
    blocked, reason = _has_blocked_patterns(sql)
    if blocked:
        return False, reason

    # 2. 多语句检测（; 分隔符劫持）
    if _detect_multi_statement(sql):
        return False, "禁止执行多条 SQL 语句"

    # 3. 提取规范化后的第一个语句
    first_stmt = _get_first_statement(sql)

    if not first_stmt:
        return False, "无法解析 SQL 语句"

    # 4. 白名单：只允许只读查询
    if not _is_read_only(first_stmt):
        # 尝试提取语句开头的关键字作为提示
        first_word = first_stmt.split()[0] if first_stmt.split() else ""
        return False, (
            f"禁止执行 {first_word.upper()} 操作。"
            "系统仅允许 SELECT / WITH / EXPLAIN 等只读查询。"
        )

    # 5. SELECT / WITH 语句内部混入 DDL/DML 关键字
    if not first_stmt.lower().startswith("explain"):
        # WITH / SELECT 里混入 DROP / DELETE 等
        if _has_dml_ddl_after_select(first_stmt):
            # 要排除列名或别名中带的单词（如 DELETE 作为别名）
            # 这里通过 normalize_sql 已经去掉了字符串和注释，误报概率低
            return False, (
                "SELECT 语句中包含了 DDL/DML 关键字，已拒绝执行。"
                "如确需修改数据请联系管理员。"
            )

    return True, ""


# ─── 快捷检查──────────────────────────────────────────────


def assert_read_only(sql: str) -> str:
    """校验并返回原 SQL（方便链式调用），校验失败时抛出 ValueError。"""
    valid, reason = validate_sql(sql)
    if not valid:
        raise ValueError(reason)
    return sql


# ─── 单元测试（手动运行） ───────────────────────────────


def _run_self_test():
    """运行内置测试用例，验证各类 SQL 语句的拦截情况。"""
    test_cases = [
        # (sql, expected_valid)
        # ── 应该通过的 ──
        ("SELECT * FROM user_info", True),
        ("select name, age from users", True),
        ("SELECT COUNT(*) FROM card_transaction", True),
        ("SELECT * FROM users WHERE name = 'hello'", True),
        ("SELECT * FROM users WHERE name = 'hello; DROP TABLE users;'", True),
        ("EXPLAIN QUERY PLAN SELECT * FROM users", True),
        ("WITH cte AS (SELECT * FROM users) SELECT * FROM cte", True),
        ("SELECT a.amount FROM card_transaction a", True),
        ("SELECT 1 AS delete_flag FROM users", True),

        # ── 应该拦截的 ──
        ("DROP TABLE users", False),
        ("delete from users", False),
        ("UPDATE users SET name = 'x'", False),
        ("INSERT INTO users VALUES (1)", False),
        ("ALTER TABLE users ADD COLUMN x INT", False),
        ("CREATE TABLE evil (id INT)", False),
        ("TRUNCATE TABLE users", False),
        ("SELECT * FROM users; DROP TABLE users", False),
        ("PRAGMA writable_schema = ON", False),
        ("ATTACH DATABASE '/tmp/evil.db' AS evil", False),
        ("VACUUM", False),
        ("REINDEX", False),
        ("SELECT 1; SELECT 2", False),
    ]

    passed = 0
    failed = 0

    print("=" * 50)
    print("SQL 安全校验器 — 自测报告")
    print("=" * 50)
    for sql, expected in test_cases:
        valid, reason = validate_sql(sql)
        status = "✅" if valid == expected else "❌"
        if valid == expected:
            passed += 1
        else:
            failed += 1
        expected_label = "通过" if expected else "拦截"
        actual_label = "✅ 通过" if valid else f"⛔ 拦截（{reason}）"
        print(f"  {status} [{expected_label}] {sql[:70]}")
        print(f"      结果：{actual_label}")

    print("=" * 50)
    print(f"总计：{passed} 通过 / {failed} 失败 / {len(test_cases)} 总用例")
    print("=" * 50)
    return failed == 0


if __name__ == "__main__":
    _run_self_test()
