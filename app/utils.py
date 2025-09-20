import uuid
import hashlib
import unicodedata
import re
from datetime import datetime, timedelta
from flask import session, request
from functools import wraps
from sqlalchemy import text
from app import db
from app.models import User, Translation, Prompt

# Simple in-memory cache for stats
_stats_cache = {'data': None, 'timestamp': None}
_cache_duration = timedelta(minutes=5)  # Cache for 5 minutes

def get_or_create_user() -> User:
    """Get or create a user based on session ID - optimized"""
    session_id = session.get('user_session_id')

    if not session_id:
        # Generate new session ID
        session_id = str(uuid.uuid4())
        session['user_session_id'] = session_id

    # Try to find existing user
    user = User.query.filter_by(session_id=session_id).first()

    current_time = datetime.utcnow()

    if not user:
        # Create new user
        user = User(
            session_id=session_id,
            created_at=current_time,
            submission_count=0,
            last_activity=current_time
        )
        db.session.add(user)
    else:
        # Update last activity for existing user
        user.last_activity = current_time

    # Single commit for both cases
    db.session.commit()

    return user

def is_admin() -> bool:
    """Check if current session is authenticated as admin"""
    return session.get('admin_logged_in', False)

def admin_required(f):
    """Decorator to require admin authentication"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not is_admin():
            from flask import redirect, url_for, flash
            flash('Admin access required', 'error')
            return redirect(url_for('main.admin_login'))
        return f(*args, **kwargs)
    return decorated_function

def get_client_info() -> dict:
    """Get client IP and user agent for logging"""
    return {
        'ip_address': (request.environ.get('HTTP_X_FORWARDED_FOR', request.remote_addr) or '')[:45],
        'user_agent': (request.environ.get('HTTP_USER_AGENT', '') or '')[:255]
    }

def normalize_kikuyu_text(text: str) -> str:
    """Robust Unicode normalization for Kikuyu text with special characters"""
    if not text:
        return ""

    try:
        # Strip whitespace
        text = text.strip()

        # Unicode normalize to handle composed/decomposed characters consistently
        # NFD = decomposed form, then recompose with NFC
        text = unicodedata.normalize('NFC', unicodedata.normalize('NFD', text))

        # Convert to lowercase (handles Unicode properly)
        text = text.lower()

        # Remove extra whitespace between words
        text = re.sub(r'\s+', ' ', text)

        return text
    except Exception:
        # Fallback to basic normalization if Unicode processing fails
        return text.strip().lower()

def hash_text(text: str) -> str:
    """Create a hash of text for duplicate detection - Unicode safe"""
    try:
        normalized = normalize_kikuyu_text(text)
        return hashlib.sha256(normalized.encode('utf-8')).hexdigest()
    except Exception:
        # Fallback hash if Unicode fails
        return hashlib.sha256(text.encode('utf-8', errors='ignore')).hexdigest()

def check_duplicate_translation(kikuyu_text: str, prompt_id: int) -> bool:
    """Check if a translation already exists - Unicode safe and optimized"""
    try:
        # Robust Unicode normalization
        normalized_text = normalize_kikuyu_text(kikuyu_text)

        if not normalized_text:
            return False

        # Fast query using only indexed columns with Unicode-safe comparison
        existing = Translation.query.filter(
            Translation.prompt_id == prompt_id,
            db.func.lower(db.func.trim(Translation.kikuyu_text)) == normalized_text
        ).first()

        return existing is not None
    except Exception:
        # Fallback to basic check if Unicode processing fails
        try:
            basic_normalized = kikuyu_text.strip().lower()
            existing = Translation.query.filter(
                Translation.prompt_id == prompt_id,
                db.func.lower(Translation.kikuyu_text) == basic_normalized
            ).first()
            return existing is not None
        except Exception:
            # Last resort - assume not duplicate if we can't check
            return False

def save_translation(prompt_id: int, kikuyu_text: str, user: User) -> Translation:
    """Save a new translation to the database - optimized for speed"""
    client_info = get_client_info()

    translation = Translation(
        prompt_id=prompt_id,
        user_id=user.id,
        kikuyu_text=kikuyu_text.strip(),
        timestamp=datetime.utcnow(),
        status='pending',
        ip_address=client_info['ip_address'],
        user_agent=client_info['user_agent']
    )

    # Batch all operations in single transaction
    db.session.add(translation)

    # Update user submission count (already in session)
    user.submission_count += 1

    # Update prompt usage count with efficient update
    db.session.execute(
        text("UPDATE prompts SET usage_count = usage_count + 1 WHERE id = :prompt_id"),
        {"prompt_id": prompt_id}
    )

    # Single commit for all operations
    db.session.commit()

    return translation

def can_user_submit(user: User) -> tuple[bool, str]:
    """
    Check if user can submit more translations

    Returns:
        Tuple of (can_submit: bool, reason: str)
    """
    from flask import current_app

    daily_limit = current_app.config.get('DAILY_SUBMISSION_LIMIT')

    # If daily limit is None, allow unlimited submissions
    if daily_limit is None:
        return True, ""

    # Check daily submission limit (legacy support)
    today = datetime.utcnow().date()
    today_submissions = Translation.query.filter(
        Translation.user_id == user.id,
        db.func.date(Translation.timestamp) == today
    ).count()

    if today_submissions >= daily_limit:
        return False, f"Daily submission limit reached ({daily_limit} translations per day)"

    return True, ""

def get_translation_stats() -> dict:
    """Get overall translation statistics - cached for performance"""
    global _stats_cache

    # Check if cache is valid
    now = datetime.utcnow()
    if (_stats_cache['data'] is not None and
        _stats_cache['timestamp'] is not None and
        now - _stats_cache['timestamp'] < _cache_duration):
        return _stats_cache['data']

    try:
        # Fast single query approach
        total_translations = db.session.scalar(text("SELECT COUNT(*) FROM translation"))
        approved_translations = db.session.scalar(text("SELECT COUNT(*) FROM translation WHERE status = 'approved'"))
        total_users = db.session.scalar(text("SELECT COUNT(*) FROM \"user\""))
        total_prompts = db.session.scalar(text("SELECT COUNT(*) FROM prompt"))

        stats = {
            'total_translations': total_translations or 0,
            'pending_translations': (total_translations or 0) - (approved_translations or 0),
            'approved_translations': approved_translations or 0,
            'total_users': total_users or 0,
            'total_prompts': total_prompts or 0
        }

        # Update cache
        _stats_cache['data'] = stats
        _stats_cache['timestamp'] = now

        return stats
    except Exception:
        # Fallback to avoid crashes
        fallback = {
            'total_translations': 0,
            'pending_translations': 0,
            'approved_translations': 0,
            'total_users': 0,
            'total_prompts': 0
        }

        # Cache fallback too
        _stats_cache['data'] = fallback
        _stats_cache['timestamp'] = now

        return fallback

def export_translations_data(status_filter: str = None) -> list:
    """
    Export translation data for analysis

    Args:
        status_filter: Filter by translation status (approved, pending, etc.)

    Returns:
        List of translation data dictionaries
    """
    query = db.session.query(
        Translation.id,
        Translation.kikuyu_text,
        Translation.timestamp,
        Translation.status,
        Prompt.text.label('english_text'),
        Prompt.category,
        User.session_id
    ).join(Prompt).join(User)

    if status_filter:
        query = query.filter(Translation.status == status_filter)

    results = query.order_by(Translation.timestamp.desc()).all()

    export_data = []
    for row in results:
        export_data.append({
            'id': row.id,
            'english_text': row.english_text,
            'kikuyu_text': row.kikuyu_text,
            'category': row.category,
            'status': row.status,
            'timestamp': row.timestamp.isoformat(),
            'user_session': row.session_id
        })

    return export_data

def validate_kikuyu_text(text: str) -> tuple[bool, str]:
    """
    Validate Kikuyu text input - Unicode safe for special characters

    Args:
        text: The text to validate

    Returns:
        Tuple of (is_valid: bool, error_message: str)
    """
    try:
        if not text or not text.strip():
            return False, "Translation cannot be empty"

        # Use Unicode-safe normalization
        normalized_text = normalize_kikuyu_text(text)

        if not normalized_text:
            return False, "Translation cannot be empty"

        if len(normalized_text) < 2:
            return False, "Translation is too short"

        if len(normalized_text) > 1000:
            return False, "Translation is too long (maximum 1000 characters)"

        # Check for suspicious patterns
        if normalized_text.isnumeric():
            return False, "Translation cannot be only numbers"

        # Check for too many repeated characters (Unicode safe)
        if any(char * 10 in normalized_text for char in set(normalized_text) if char.isalpha()):
            return False, "Translation contains too many repeated characters"

        # Enhanced character validation for Kikuyu
        allowed_chars = set('.,!?;:\'"()-–—''""…')  # Extended punctuation

        for char in normalized_text:
            # Allow letters (including all Unicode letters with diacritics)
            # Allow numbers, spaces and allowed punctuation
            if (char.isalpha() or
                char.isdigit() or
                char.isspace() or
                char in allowed_chars or
                unicodedata.category(char) in ['Mn', 'Mc', 'Lm']):  # Mark categories + letter modifiers
                continue
            else:
                # More informative error for special characters
                char_name = unicodedata.name(char, f"U+{ord(char):04X}")
                return False, f"Translation contains unsupported character: '{char}' ({char_name})"

        return True, ""
    except Exception as e:
        # Fallback validation if Unicode processing fails
        try:
            basic_text = text.strip()
            if len(basic_text) < 2:
                return False, "Translation is too short"
            if len(basic_text) > 1000:
                return False, "Translation is too long"
            return True, ""
        except Exception:
            return False, "Translation contains invalid characters"