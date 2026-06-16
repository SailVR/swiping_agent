"""
基于FastMCP的SQL查询工具服务器

提供简单的SQL执行功能，方便扩展不同的数据源。
"""

import sqlite3
import json
from pathlib import Path

from mcp.server.fastmcp import FastMCP

# SQL 安全校验
from sql_validator import validate_sql

# 创建FastMCP服务器
mcp = FastMCP("sql-query-server")

# 数据库配置
DB_CONFIG = {
    "type": "sqlite",
    "path": Path(__file__).parent / "data" / "credit_bonus.db"
}


@mcp.tool()
def execute_sql(sql: str) -> str:
    """执行SQL查询

    Args:
        sql: SQL查询语句
        db_type: 数据库类型（sqlite）

    Returns:
        JSON格式的查询结果
    """
    # ── SQL 安全校验：只允许 SELECT / WITH / EXPLAIN 等只读查询 ──
    valid, reason = validate_sql(sql)
    if not valid:
        error_output = json.dumps({
            "error": f"SQL 安全拦截: {reason}",
            "sql": sql
        }, ensure_ascii=False)
        return error_output

    return _execute_sqlite(sql)


def _execute_sqlite(sql: str) -> str:
    """执行SQLite查询"""
    db_path = DB_CONFIG["path"]
    
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute(sql)
        rows = cursor.fetchall()
        
        if rows:
            result = [dict(row) for row in rows]
            output = json.dumps(result, ensure_ascii=False, indent=2)
        else:
            output = json.dumps({"message": "查询结果为空"})
        
        conn.close()
        return output
        
    except sqlite3.Error as e:
        error_output = json.dumps({
            "error": f"SQL执行错误: {str(e)}",
            "sql": sql
        }, ensure_ascii=False)
        return error_output
    except Exception as e:
        error_output = json.dumps({
            "error": f"未知错误: {str(e)}"
        }, ensure_ascii=False)
        return error_output

if __name__ == "__main__":
    mcp.run()

