from flask import Blueprint, request, jsonify
from src.extensions import db
from settings.company_settings import Settings
from user.enhanced_auth_middleware import require_permission_jwt
from user.audit_logger import audit_decorator

bp = Blueprint("settings", __name__)

@bp.route("/", methods=["GET"])
@require_permission_jwt('settings', 'read')
def get_settings():
    settings = Settings.query.first()
    if not settings:
        return jsonify({"message": "No settings found"}), 404
    
    return jsonify({
        "id": settings.id,
        "business_name": settings.business_name,
        "business_type": settings.business_type,
        "registration_number": settings.registration_number,
        "gst_number": settings.gst_number,
        "pan_number": settings.pan_number,
        "logo_path": settings.logo_path,
        "tagline": settings.tagline,
        "primary_phone": settings.primary_phone,
        "secondary_phone": settings.secondary_phone,
        "primary_email": settings.primary_email,
        "secondary_email": settings.secondary_email,
        "website": settings.website,
        "registered_address": settings.registered_address,
        "billing_address": settings.billing_address,
        "shipping_address": settings.shipping_address,
        "city": settings.city,
        "state": settings.state,
        "postal_code": settings.postal_code,
        "country": settings.country,
        "bank_name": settings.bank_name,
        "account_number": settings.account_number,
        "ifsc_code": settings.ifsc_code,
        "branch": settings.branch,
        "created_at": settings.created_at.isoformat() if settings.created_at else None,
        "updated_at": settings.updated_at.isoformat() if settings.updated_at else None
    }), 200

@bp.route("/", methods=["POST"])
@require_permission_jwt('settings', 'write')
@audit_decorator('settings', 'CREATE')
def create_settings():
    # Check if settings already exist
    if Settings.query.first():
        return jsonify({"error": "Settings already exist. Use PUT to update."}), 400
    
    data = request.get_json() or {}
    
    settings = Settings()
    for key, value in data.items():
        if hasattr(settings, key):
            setattr(settings, key, value)
    
    db.session.add(settings)
    db.session.commit()
    return jsonify({"message": "Settings created successfully"}), 201

@bp.route("/", methods=["PUT"])
@require_permission_jwt('settings', 'write')
@audit_decorator('settings', 'UPDATE')
def update_settings():
    data = request.get_json() or {}
    
    settings = Settings.query.first()
    if not settings:
        return jsonify({"error": "Settings not found"}), 404
    
    for key, value in data.items():
        if hasattr(settings, key):
            setattr(settings, key, value)
    
    db.session.commit()
    return jsonify({"message": "Settings updated successfully"}), 200