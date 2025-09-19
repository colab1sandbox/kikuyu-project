import json
import logging
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify, current_app
from app import db
from app.models import Prompt, Translation, User, AdminAction
from app.forms import TranslationForm, AdminLoginForm, AdminModerationForm, PromptManagementForm
from app.utils import (
    get_or_create_user, is_admin, admin_required, save_translation,
    can_user_submit, check_duplicate_translation, validate_kikuyu_text,
    get_translation_stats, export_translations_data
)
from app.services.csv_prompt_manager import CSVPromptManager
from app.services.openrouter import OpenRouterClient

# Create blueprint
main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def index():
    """Landing page"""
    stats = get_translation_stats()
    return render_template('index.html', stats=stats)

@main_bp.route('/translate', methods=['GET', 'POST'])
def translate():
    """Main translation interface"""
    user = get_or_create_user()

    # Check if user can submit
    can_submit, reason = can_user_submit(user)
    if not can_submit and request.method == 'POST':
        flash(reason, 'error')
        return redirect(url_for('main.translate'))

    form = TranslationForm()

    if request.method == 'GET':
        # Get next prompt from CSV dataset
        csv_manager = CSVPromptManager()
        prompt_data = csv_manager.get_next_prompt(user.session_id)

        if not prompt_data:
            flash('No prompts available at the moment. Please try again later.', 'error')
            return redirect(url_for('main.index'))

        # Store prompt in database if not already there
        prompt = Prompt.query.filter_by(text=prompt_data['text']).first()
        if not prompt:
            prompt = Prompt(
                text=prompt_data['text'],
                category=prompt_data.get('category', 'general'),
                date_generated=datetime.fromisoformat(prompt_data['date_generated']),
                usage_count=0,
                status='active'
            )
            db.session.add(prompt)
            db.session.commit()

        form.prompt_id.data = prompt.id

        return render_template('translate.html', form=form, prompt=prompt, user=user)

    elif request.method == 'POST':
        if form.validate_on_submit():
            prompt_id = form.prompt_id.data
            kikuyu_text = form.kikuyu_text.data

            # Validate text
            is_valid, error_msg = validate_kikuyu_text(kikuyu_text)
            if not is_valid:
                flash(error_msg, 'error')
                prompt = Prompt.query.get(prompt_id)
                return render_template('translate.html', form=form, prompt=prompt, user=user)

            # Check for duplicates
            if check_duplicate_translation(kikuyu_text, prompt_id):
                flash('This translation has already been submitted for this prompt.', 'error')
                prompt = Prompt.query.get(prompt_id)
                return render_template('translate.html', form=form, prompt=prompt, user=user)

            # Save translation
            try:
                translation = save_translation(prompt_id, kikuyu_text, user)
                flash('Thank you! Your translation has been submitted for review.', 'success')

                # Log the submission
                logging.info(f"Translation submitted: ID {translation.id}, User {user.session_id}")

                return redirect(url_for('main.thank_you'))

            except Exception as e:
                logging.error(f"Error saving translation: {e}")
                flash('An error occurred while saving your translation. Please try again.', 'error')
                prompt = Prompt.query.get(prompt_id)
                return render_template('translate.html', form=form, prompt=prompt, user=user)

        else:
            # Form validation failed
            prompt_id = form.prompt_id.data
            prompt = Prompt.query.get(prompt_id) if prompt_id else None
            return render_template('translate.html', form=form, prompt=prompt, user=user)

@main_bp.route('/thank-you')
def thank_you():
    """Thank you page after submission"""
    user = get_or_create_user()
    return render_template('thank_you.html', user=user)

@main_bp.route('/api/next-prompt')
def api_next_prompt():
    """API endpoint to get next prompt"""
    try:
        user = get_or_create_user()

        # Check if user can submit
        can_submit, reason = can_user_submit(user)
        if not can_submit:
            return jsonify({'error': reason}), 429

        cache_manager = CSVPromptManager()
        prompt_data = cache_manager.get_next_prompt(user.session_id)

        if not prompt_data:
            return jsonify({'error': 'No prompts available'}), 404

        return jsonify({
            'prompt': prompt_data['text'],
            'category': prompt_data.get('category', 'general'),
            'prompt_id': prompt_data['id']
        })

    except Exception as e:
        logging.error(f"Error in api_next_prompt: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@main_bp.route('/skip-prompt/<prompt_id>', methods=['POST'])
def skip_prompt(prompt_id):
    """Skip current prompt and return it to the available pool"""
    try:
        user = get_or_create_user()

        # Return the prompt to the available pool
        cache_manager = CSVPromptManager()
        success = cache_manager.return_prompt_to_pool(prompt_id)

        if success:
            logging.info(f"User {user.session_id} skipped prompt {prompt_id}")
            flash('Prompt skipped. You can get a new one!', 'info')
        else:
            flash('Could not skip prompt. Please try again.', 'error')

        return redirect(url_for('main.translate'))

    except Exception as e:
        logging.error(f"Error in skip_prompt: {e}")
        flash('An error occurred while skipping the prompt.', 'error')
        return redirect(url_for('main.translate'))

# Admin Routes
@main_bp.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    """Admin login page"""
    if is_admin():
        return redirect(url_for('main.admin_dashboard'))

    form = AdminLoginForm()

    if form.validate_on_submit():
        password = form.password.data
        correct_password = current_app.config.get('ADMIN_PASSWORD', 'admin123')

        if password == correct_password:
            session['admin_logged_in'] = True
            flash('Admin login successful', 'success')
            return redirect(url_for('main.admin_dashboard'))
        else:
            flash('Invalid password', 'error')

    return render_template('admin/login.html', form=form)

@main_bp.route('/admin/logout')
def admin_logout():
    """Admin logout"""
    session.pop('admin_logged_in', None)
    flash('Logged out successfully', 'success')
    return redirect(url_for('main.index'))

@main_bp.route('/admin')
@admin_required
def admin_dashboard():
    """Admin dashboard"""
    stats = get_translation_stats()

    # Get cache stats
    cache_manager = CSVPromptManager()
    cache_stats = cache_manager.get_cache_stats()

    # Get recent translations
    recent_translations = db.session.query(Translation, Prompt, User).join(
        Prompt
    ).join(User).order_by(Translation.timestamp.desc()).limit(10).all()

    return render_template('admin/dashboard.html',
                         stats=stats,
                         cache_stats=cache_stats,
                         recent_translations=recent_translations)

@main_bp.route('/admin/submissions')
@admin_required
def admin_submissions():
    """View all submissions for moderation"""
    page = request.args.get('page', 1, type=int)
    status_filter = request.args.get('status', '')

    query = db.session.query(Translation, Prompt, User).join(
        Prompt
    ).join(User)

    if status_filter:
        query = query.filter(Translation.status == status_filter)

    submissions = query.order_by(Translation.timestamp.desc()).paginate(
        page=page, per_page=20, error_out=False
    )

    return render_template('admin/submissions.html',
                         submissions=submissions,
                         status_filter=status_filter)

@main_bp.route('/admin/moderate/<int:translation_id>', methods=['POST'])
@admin_required
def admin_moderate(translation_id):
    """Moderate a specific translation"""
    translation = Translation.query.get_or_404(translation_id)

    # Get action directly from form data (simplified approach)
    action = request.form.get('action')

    if action in ['approved', 'rejected']:
        # Update translation status
        translation.status = action

        # Log admin action
        admin_action = AdminAction(
            translation_id=translation_id,
            action=action,
            admin_id=session.get('admin_id', 'admin'),
            timestamp=datetime.utcnow(),
            notes=f'Translation {action} via simplified interface'
        )

        db.session.add(admin_action)
        db.session.commit()

        flash(f'Translation {action} successfully', 'success')
    else:
        flash('Invalid action', 'error')

    return redirect(url_for('main.admin_submissions'))

@main_bp.route('/admin/cache-status')
@admin_required
def admin_cache_status():
    """View prompt cache status"""
    cache_manager = CSVPromptManager()
    cache_stats = cache_manager.get_cache_stats()

    # Test OpenRouter connection
    openrouter = OpenRouterClient()
    connection_test = openrouter.test_connection()

    return render_template('admin/cache_status.html',
                         cache_stats=cache_stats,
                         connection_test=connection_test)

@main_bp.route('/admin/refill', methods=['POST'])
@admin_required
def admin_refill():
    """Manually refill prompt cache"""
    try:
        cache_manager = CSVPromptManager()
        success = cache_manager.refill_cache(force=True)

        if success:
            flash('Prompt cache refilled successfully!', 'success')
        else:
            flash('Failed to refill cache. Check API limits and connection.', 'error')

    except Exception as e:
        logging.error(f"Error in admin refill: {e}")
        flash('An error occurred during cache refill.', 'error')

    return redirect(url_for('main.admin_cache_status'))

@main_bp.route('/admin/export')
@admin_required
def admin_export():
    """Export translation data as JSON or CSV"""
    status_filter = request.args.get('status', 'approved')
    format_type = request.args.get('format', 'json').lower()

    try:
        data = export_translations_data(status_filter)
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')

        if format_type == 'csv':
            # Import csv module at the top if not already imported
            import csv
            from io import StringIO
            from flask import make_response

            output = StringIO()
            if data:
                writer = csv.DictWriter(output, fieldnames=data[0].keys())
                writer.writeheader()
                writer.writerows(data)

            response = make_response(output.getvalue())
            response.headers['Content-Type'] = 'text/csv'
            response.headers['Content-Disposition'] = f'attachment; filename=kikuyu_translations_{status_filter}_{timestamp}.csv'
            return response

        else:  # JSON format
            from flask import make_response
            import json

            export_data = {
                'success': True,
                'data': data,
                'count': len(data),
                'status_filter': status_filter,
                'exported_at': datetime.utcnow().isoformat()
            }

            response = make_response(json.dumps(export_data, indent=2, ensure_ascii=False))
            response.headers['Content-Type'] = 'application/json'
            response.headers['Content-Disposition'] = f'attachment; filename=kikuyu_translations_{status_filter}_{timestamp}.json'
            return response

    except Exception as e:
        logging.error(f"Error in admin export: {e}")
        return jsonify({'error': 'Export failed'}), 500

# Error handlers
@main_bp.app_errorhandler(404)
def not_found_error(error):
    return render_template('errors/404.html'), 404

@main_bp.app_errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('errors/500.html'), 500

@main_bp.app_errorhandler(429)
def ratelimit_handler(e):
    return render_template('errors/429.html'), 429