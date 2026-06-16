"""
Flask Web API for Multi-Agent Data Query System
提供RESTful API接口供前端调用，支持普通查询和流式SSE查询。
"""

from flask import Flask, request, jsonify, send_from_directory, Response, stream_with_context, send_file
from flask_cors import CORS
import os
import sys
import json
from typing import Dict, Any

# 将当前目录添加到Python路径
sys.path.insert(0, os.path.dirname(__file__))

from agent import MultiAgentSystem

app = Flask(__name__, static_folder='static', static_url_path='')
CORS(app)  # 允许跨域请求

# 全局系统实例（用于存储不同用户的会话）
user_systems: Dict[str, MultiAgentSystem] = {}

from dotenv import load_dotenv
from logger import get_logger

logger = get_logger(__name__)
load_dotenv()  


def get_or_create_system(user_id: str) -> MultiAgentSystem:
    """获取或创建用户的系统实例"""
    if user_id not in user_systems:
        system = MultiAgentSystem()
        system.login(user_id)
        user_systems[user_id] = system
    return user_systems[user_id]


@app.route('/')
def index():
    """返回前端页面"""
    return send_from_directory('static', 'index.html')


@app.route('/api/login', methods=['POST'])
def login():
    """用户登录接口"""
    try:
        data = request.json
        user_id = data.get('user_id', 'guest')
        
        # 创建或获取用户系统
        system = get_or_create_system(user_id)

        # 直接从长期记忆数据库加载用户信息（无需等待对话总结）
        ltm = system.master_agent.long_term_memory
        profile = ltm.get_user_profile(user_id)
        preferences = ltm.get_all_preferences(user_id)
        knowledge = ltm.get_all_knowledge(user_id, limit=50)

        return jsonify({
            'success': True,
            'user_id': user_id,
            'session_id': system.session_id,
            'message': f'欢迎 {user_id}！',
            'user_info': {
                'logged_in': True,
                'user_id': user_id,
                'session_id': system.session_id,
                'profile': profile,
                'preferences': preferences,
                'knowledge': knowledge
            }
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/query', methods=['POST'])
def query():
    """查询接口"""
    try:
        data = request.json
        user_id = data.get('user_id', 'guest')
        question = data.get('question', '')
        
        if not question.strip():
            return jsonify({
                'success': False,
                'error': '问题不能为空'
            }), 400
        
        # 获取用户系统
        system = get_or_create_system(user_id)
        
        # 执行查询
        answer = system.query(question)
        
        return jsonify({
            'success': True,
            'answer': answer,
            'user_id': user_id,
            'session_id': system.session_id
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/new_session', methods=['POST'])
def new_session():
    """创建新会话"""
    try:
        data = request.json
        user_id = data.get('user_id', 'guest')
        
        system = get_or_create_system(user_id)
        system.new_session()
        
        return jsonify({
            'success': True,
            'session_id': system.session_id,
            'message': '已开始新会话'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/user_info', methods=['POST'])
def user_info():
    """获取用户信息"""
    try:
        data = request.json
        user_id = data.get('user_id', 'guest')
        
        system = get_or_create_system(user_id)
        # 直接读取长期记忆，包括知识列表
        ltm = system.master_agent.long_term_memory
        info = system.get_user_info()
        info['knowledge'] = ltm.get_all_knowledge(user_id, limit=50)

        return jsonify({
            'success': True,
            'user_info': info
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/query_stream', methods=['POST'])
def query_stream():
    """流式查询接口（Server-Sent Events）
    
    前端使用 fetch + ReadableStream 接收，实现逐字打字效果。
    事件类型：
      - status: 处理状态更新（如"正在查询数据库..."）
      - intent: 识别到的意图类型
      - sql: 生成的SQL语句（含重试次数）
      - sources: 联网搜索来源URL列表
      - chart: ECharts图表配置JSON
      - chunk: LLM输出的文字片段（流式）
      - error: 错误信息（非致命，继续处理）
      - done: 流结束标志（含完整answer）
    """
    try:
        data = request.json
        user_id = data.get('user_id', 'guest')
        question = data.get('question', '')
        
        if not question.strip():
            return jsonify({'success': False, 'error': '问题不能为空'}), 400
        
        system = get_or_create_system(user_id)
        
        def generate():
            try:
                for event in system.stream_query(question):
                    yield event
            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"
                yield f"data: {json.dumps({'type': 'done', 'answer': f'系统错误: {str(e)}'})}\n\n"
        
        return Response(
            stream_with_context(generate()),
            mimetype='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'X-Accel-Buffering': 'no',
                'Connection': 'keep-alive'
            }
        )
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/health', methods=['GET'])
def health():
    """健康检查接口"""
    search_available = False
    try:
        if user_systems:
            first_system = next(iter(user_systems.values()))
            search_available = first_system.master_agent.search_agent.available
    except Exception:
        pass
    
    return jsonify({
        'status': 'healthy',
        'active_users': len(user_systems),
        'features': {
            'sql_self_correction': True,
            'streaming': True,
            'web_search': search_available,
            'data_visualization': True
        }
    })


@app.route('/api/export', methods=['POST'])
def export_data():
    """导出查询结果（Excel / PDF）

    请求体：
        user_id: 用户 ID
        format: 导出格式 "excel" 或 "pdf"（默认 excel）

    返回文件下载响应。
    """
    from datetime import datetime
    from export import export_to_excel, export_to_pdf

    try:
        data = request.json
        user_id = data.get('user_id', 'guest')
        export_format = data.get('format', 'excel')

        system = get_or_create_system(user_id)
        thread_id = f"{user_id}_{system.session_id}"

        # 从会话数据中获取最近一次查询结果
        session_data = system.master_agent.session_data
        thread_data = session_data.get(thread_id, {})

        sql_result = thread_data.get("last_sql_result", {}) or {}
        search_result = thread_data.get("last_search_result") or {}
        last_answer = thread_data.get("last_answer", "")
        chart_config = thread_data.get("last_chart_config")

        # 优先取 SQL 原生数据，其次搜索结果
        data_json = ""
        if sql_result.get("data") and not sql_result.get("error"):
            data_json = sql_result["data"]
        elif search_result.get("data"):
            data_json = search_result["data"]

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        if export_format == "excel":
            buf = export_to_excel(data_json, chart_config=chart_config)
            return send_file(
                buf,
                mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                as_attachment=True,
                download_name=f"query_result_{timestamp}.xlsx"
            )

        elif export_format == "pdf":
            buf = export_to_pdf(last_answer, data_json)
            return send_file(
                buf,
                mimetype="application/pdf",
                as_attachment=True,
                download_name=f"query_report_{timestamp}.pdf"
            )

        else:
            return jsonify({"success": False, "error": f"不支持的导出格式: {export_format}"}), 400

    except ImportError as e:
        return jsonify({
            "success": False,
            "error": f"导出功能缺少依赖库: {str(e)}。请执行: pip install openpyxl fpdf2"
        }), 500
    except Exception as e:
        return jsonify({"success": False, "error": f"导出失败: {str(e)}"}), 500


@app.route('/api/export_info', methods=['POST'])
def export_info():
    """查询当前会话是否有可导出的数据，供前端控制导出按钮显示。"""
    try:
        data = request.json
        user_id = data.get('user_id', 'guest')

        system = get_or_create_system(user_id)
        thread_id = f"{user_id}_{system.session_id}"
        thread_data = system.master_agent.session_data.get(thread_id, {})

        has_data = thread_data.get("has_data", False)
        has_answer = bool(thread_data.get("last_answer"))

        return jsonify({
            "success": True,
            "has_data": has_data,
            "has_answer": has_answer,
            "can_export": has_data or has_answer
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


if __name__ == '__main__':
    # 检查环境变量
    if not os.getenv("DASHSCOPE_API_KEY"):
        logger.critical("未设置 DASHSCOPE_API_KEY 环境变量")
        sys.exit(1)

    logger.info("信用卡刷卡金数据分析系统 Web API 启动中...")
    logger.info("访问地址: http://localhost:5001")
    
    app.run(host='0.0.0.0', port=5001, debug=True)

