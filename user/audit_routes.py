from flask import Blueprint, request, jsonify, send_file, make_response
from user.user import AuditLog, User
from user.jwt_middleware import jwt_required, get_current_user
from src.extensions import db
from datetime import datetime
import pandas as pd
import io
import json

bp = Blueprint('audit', __name__)

@bp.route('/audit-logs/', methods=['GET'])
@jwt_required
def get_audit_logs():
    """Get audit logs with filtering options"""
    current_user = get_current_user()
    if not current_user or current_user['role'] != 'admin':
        return jsonify({'error': 'Admin access required'}), 403
    
    # Query parameters
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 20))
    module = request.args.get('module')
    action = request.args.get('action')
    user_id = request.args.get('user_id')
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    
    # Build query
    query = AuditLog.query
    
    if module:
        query = query.filter(AuditLog.module_name == module)
    if action:
        query = query.filter(AuditLog.action.contains(action))
    if user_id:
        query = query.filter(AuditLog.user_id == int(user_id))
    if date_from:
        try:
            dt_from = datetime.fromisoformat(date_from)
            query = query.filter(AuditLog.timestamp >= dt_from)
        except ValueError:
            return jsonify({'error': 'Invalid date_from format'}), 400
    if date_to:
        try:
            dt_to = datetime.fromisoformat(date_to)
            query = query.filter(AuditLog.timestamp <= dt_to)
        except ValueError:
            return jsonify({'error': 'Invalid date_to format'}), 400
    
    # Order by timestamp descending
    query = query.order_by(AuditLog.timestamp.desc())
    
    # Paginate
    paginated = query.paginate(page=page, per_page=per_page, error_out=False)
    
    # Format response
    audit_logs = []
    for log in paginated.items:
        audit_logs.append({
            'user_id': log.user_id,
            'username': log.username,
            'user_role': log.user_role,
            'action': log.action,
            'module_name': log.module_name,
            'record_id': log.record_id,
            'old_data': log.old_data,
            'new_data': log.new_data,
            'ip_address': log.ip_address,
            'timestamp': log.timestamp.isoformat(),
            'description': format_audit_description(log)
        })
    
    return jsonify({
        'audit_logs': audit_logs,
        'pagination': {
            'page': paginated.page,
            'per_page': paginated.per_page,
            'total': paginated.total,
            'pages': paginated.pages,
            'has_next': paginated.has_next,
            'has_prev': paginated.has_prev
        }
    }), 200

@bp.route('/audit-logs/user/<int:user_id>/', methods=['GET'])
@jwt_required
def get_logs_by_user_id(user_id):
    current_user = get_current_user()
    if not current_user or current_user['role'] != 'admin':
        return jsonify({'error': 'Admin access required'}), 403
    
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 20))
    
    paginated = AuditLog.query.filter_by(user_id=user_id).order_by(AuditLog.timestamp.desc()).paginate(page=page, per_page=per_page, error_out=False)
    
    return jsonify({
        'audit_logs': [format_log(log) for log in paginated.items],
        'pagination': get_pagination_info(paginated)
    }), 200

@bp.route('/audit-logs/username/<username>/', methods=['GET'])
@jwt_required
def get_logs_by_username(username):
    current_user = get_current_user()
    if not current_user or current_user['role'] != 'admin':
        return jsonify({'error': 'Admin access required'}), 403
    
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 20))
    
    paginated = AuditLog.query.filter_by(username=username).order_by(AuditLog.timestamp.desc()).paginate(page=page, per_page=per_page, error_out=False)
    
    return jsonify({
        'audit_logs': [format_log(log) for log in paginated.items],
        'pagination': get_pagination_info(paginated)
    }), 200

@bp.route('/audit-logs/module/<module_name>/', methods=['GET'])
@jwt_required
def get_logs_by_module(module_name):
    current_user = get_current_user()
    if not current_user or current_user['role'] != 'admin':
        return jsonify({'error': 'Admin access required'}), 403
    
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 20))
    
    paginated = AuditLog.query.filter_by(module_name=module_name).order_by(AuditLog.timestamp.desc()).paginate(page=page, per_page=per_page, error_out=False)
    
    return jsonify({
        'audit_logs': [format_log(log) for log in paginated.items],
        'pagination': get_pagination_info(paginated)
    }), 200

@bp.route('/audit-logs/role/<role>/', methods=['GET'])
@jwt_required
def get_logs_by_role(role):
    current_user = get_current_user()
    if not current_user or current_user['role'] != 'admin':
        return jsonify({'error': 'Admin access required'}), 403
    
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 20))
    
    paginated = AuditLog.query.filter_by(user_role=role).order_by(AuditLog.timestamp.desc()).paginate(page=page, per_page=per_page, error_out=False)
    
    return jsonify({
        'audit_logs': [format_log(log) for log in paginated.items],
        'pagination': get_pagination_info(paginated)
    }), 200

@bp.route('/audit-logs/date/<date>/', methods=['GET'])
@jwt_required
def get_logs_by_date(date):
    current_user = get_current_user()
    if not current_user or current_user['role'] != 'admin':
        return jsonify({'error': 'Admin access required'}), 403
    
    try:
        target_date = datetime.fromisoformat(date).date()
    except ValueError:
        return jsonify({'error': 'Invalid date format, use YYYY-MM-DD'}), 400
    
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 20))
    
    paginated = AuditLog.query.filter(db.func.date(AuditLog.timestamp) == target_date).order_by(AuditLog.timestamp.desc()).paginate(page=page, per_page=per_page, error_out=False)
    
    return jsonify({
        'audit_logs': [format_log(log) for log in paginated.items],
        'pagination': get_pagination_info(paginated)
    }), 200

def format_log(log):
    return {
        'user_id': log.user_id,
        'username': log.username,
        'user_role': log.user_role,
        'action': log.action,
        'module_name': log.module_name,
        'record_id': log.record_id,
        'old_data': log.old_data,
        'new_data': log.new_data,
        'ip_address': log.ip_address,
        'timestamp': log.timestamp.isoformat()
    }

def get_pagination_info(paginated):
    return {
        'page': paginated.page,
        'per_page': paginated.per_page,
        'total': paginated.total,
        'pages': paginated.pages,
        'has_next': paginated.has_next,
        'has_prev': paginated.has_prev
    }

@bp.route('/audit-logs/export/', methods=['GET'])
@jwt_required
def export_audit_logs():
    current_user = get_current_user()
    if not current_user or current_user['role'] != 'admin':
        return jsonify({'error': 'Admin access required'}), 403
    
    format_type = request.args.get('format', 'csv').lower()
    module = request.args.get('module')
    user_id = request.args.get('user_id')
    username = request.args.get('username')
    role = request.args.get('role')
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    
    query = AuditLog.query
    
    if module:
        query = query.filter(AuditLog.module_name == module)
    if user_id:
        query = query.filter(AuditLog.user_id == int(user_id))
    if username:
        query = query.filter(AuditLog.username == username)
    if role:
        query = query.filter(AuditLog.user_role == role)
    if date_from:
        dt_from = datetime.fromisoformat(date_from)
        query = query.filter(AuditLog.timestamp >= dt_from)
    if date_to:
        dt_to = datetime.fromisoformat(date_to)
        query = query.filter(AuditLog.timestamp <= dt_to)
    
    logs = query.order_by(AuditLog.timestamp.desc()).all()
    
    data = []
    for log in logs:
        data.append({
            'user_id': log.user_id,
            'username': log.username,
            'user_role': log.user_role,
            'action': log.action,
            'module_name': log.module_name,
            'record_id': log.record_id,
            'old_data': json.dumps(log.old_data) if log.old_data else '',
            'new_data': json.dumps(log.new_data) if log.new_data else '',
            'ip_address': log.ip_address,
            'timestamp': log.timestamp.strftime('%Y-%m-%d %H:%M:%S')
        })
    
    df = pd.DataFrame(data)
    
    if format_type == 'excel':
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Audit_Logs', index=False)
        output.seek(0)
        return send_file(
            output,
            as_attachment=True,
            download_name='audit_logs_export.xlsx',
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    else:
        output = io.StringIO()
        df.to_csv(output, index=False)
        response = make_response(output.getvalue())
        response.headers['Content-Type'] = 'text/csv; charset=utf-8'
        response.headers['Content-Disposition'] = 'attachment; filename=audit_logs_export.csv'
        return response
