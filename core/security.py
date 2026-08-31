import os
import uuid

from django.core.exceptions import ValidationError


ALLOWED_UPLOAD_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.gif', '.pdf', '.mp4', '.m3u8'}
MAX_UPLOAD_SIZE = 25 * 1024 * 1024
SENSITIVE_LOG_KEYS = {'password', 'secret', 'token', 'authorization', 'razorpay_key_secret', 'secret_key'}


def validate_upload_file(file_obj):
    name = getattr(file_obj, 'name', '')
    ext = os.path.splitext(name.lower())[1]
    if ext not in ALLOWED_UPLOAD_EXTENSIONS:
        raise ValidationError('Unsupported file extension.')
    try:
        size = getattr(file_obj, 'size', 0)
    except (FileNotFoundError, OSError):
        size = 0
    if size > MAX_UPLOAD_SIZE:
        raise ValidationError('File is too large.')


def safe_upload_name(instance, filename):
    ext = os.path.splitext(filename.lower())[1]
    return f"tenant_{instance.tenant_id}/{uuid.uuid4().hex}{ext}"


def redact_log_data(data):
    redacted = {}
    for key, value in (data or {}).items():
        if any(sensitive in key.lower() for sensitive in SENSITIVE_LOG_KEYS):
            redacted[key] = '[REDACTED]'
        else:
            redacted[key] = value
    return redacted
