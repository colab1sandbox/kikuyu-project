"""
Main Routes with Hybrid System Integration
Updated routes to work with the new hybrid prompt system
"""

import json
import logging
from datetime import datetime
from flask import (
    Blueprint, render_template, request, redirect, url_for, flash,
    session, jsonify, current_app
)

from app import db
from app.models import Prompt, Translation, User, CommunitySubmission
from app.forms import TranslationForm, CommunitySubmissionForm
from app.utils import (
    get_or_create_user, is_admin, admin_required, save_translation,
    can_user_submit, check_duplicate_translation, validate_kikuyu_text,
    get_translation_stats
)
from app.services.smart_selector import SmartPromptSelector
from app.services.csv_prompt_manager import CSVPromptManager
from app.services.community_service import CommunitySubmissionService
from app.services.analytics import AnalyticsService


# Create main blueprint
main_bp = Blueprint('main', __name__)


@main_bp.route('/')
def index():
    """Landing page with enhanced statistics"""
    try:
        # Get comprehensive statistics
        analytics_service = AnalyticsService()
        stats = analytics_service.get_overview_metrics()

        # Get recent activity summary
        recent_activity = get_recent_activity_summary()

        return render_template(
            'index.html',
            stats=stats,
            recent_activity=recent_activity
        )
    except Exception as e:
        logging.error(f"Error in index route: {e}")
        # Fallback to basic stats
        basic_stats = {
            'total_prompts': Prompt.query.filter_by(status='active').count(),
            'total_translations': Translation.query.count(),
            'total_users': User.query.count()
        }
        return render_template('index.html', stats=basic_stats, recent_activity={})


@main_bp.route('/translate', methods=['GET', 'POST'])
def translate():
    """Main translation interface with smart prompt selection"""
    user = get_or_create_user()

    # Check if user can submit
    can_submit, reason = can_user_submit(user)
    if not can_submit and request.method == 'POST':
        flash(reason, 'error')
        return redirect(url_for('main.translate'))

    form = TranslationForm()

    if request.method == 'GET':
        try:
            # Use CSV prompt manager for prompt selection
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
                    category=prompt_data.get('category', 'csv_dataset'),
                    source_type='csv_dataset',
                    difficulty_level='medium'
                )
                db.session.add(prompt)
                db.session.commit()

            # Update prompt_data with database ID
            prompt_data['id'] = prompt.id

            form.prompt_id.data = prompt.id

            # Add context for user experience
            context = {
                'selection_strategy': prompt_data.get('selection_strategy', 'balanced'),
                'category': prompt.category,
                'difficulty': prompt.difficulty_level,
                'source_type': prompt.source_type
            }

            return render_template(
                'translate.html',
                form=form,
                prompt=prompt,
                user=user,
                context=context
            )

        except Exception as e:
            logging.error(f"Error selecting prompt for user {user.id}: {e}")
            flash('Error getting prompt. Please try again.', 'error')
            return redirect(url_for('main.index'))

    elif request.method == 'POST':
        if form.validate_on_submit():
            prompt_id = form.prompt_id.data
            kikuyu_text = form.kikuyu_text.data

            try:
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
    """Thank you page after submission with next steps - optimized"""
    user = get_or_create_user()

    # Use cached submission count instead of query for speed
    user_translations = user.submission_count

    # Suggest next actions
    suggestions = []
    if user_translations == 1:
        suggestions.append("Great start! Try a few more translations to get comfortable.")
    elif user_translations % 5 == 0:
        suggestions.append("You're doing great! Consider submitting your own English sentences.")

    return render_template(
        'thank_you.html',
        user=user,
        translation_count=user_translations,
        suggestions=suggestions
    )


@main_bp.route('/contribute')
def contribute():
    """Community contribution page"""
    return render_template('contribute.html')


@main_bp.route('/submit-prompt', methods=['GET', 'POST'])
def submit_prompt():
    """Community prompt submission"""
    form = CommunitySubmissionForm()

    if request.method == 'POST' and form.validate_on_submit():
        try:
            # Get submitter info (using utils function for proper truncation)
            from app.utils import get_client_info
            submitter_info = get_client_info()

            # Submit via community service
            community_service = CommunitySubmissionService()
            result = community_service.submit_prompt(
                text=form.text.data,
                category=form.category.data,
                difficulty=form.difficulty.data,
                submitter_info=submitter_info
            )

            if result['success']:
                flash(result['message'], 'success')
                return redirect(url_for('main.contribute'))
            else:
                flash(result['error'], 'error')
                if 'suggestions' in result:
                    for suggestion in result['suggestions']:
                        flash(suggestion, 'info')

        except Exception as e:
            logging.error(f"Error submitting community prompt: {e}")
            flash('Error submitting prompt. Please try again.', 'error')

    return render_template('submit_prompt.html', form=form)


@main_bp.route('/api/next-prompt')
def api_next_prompt():
    """API endpoint to get next prompt with smart selection"""
    try:
        user = get_or_create_user()

        # Check if user can submit
        can_submit, reason = can_user_submit(user)
        if not can_submit:
            return jsonify({'error': reason}), 429

        # Get preferred category from query params
        preferred_category = request.args.get('category')

        # Use smart selector
        smart_selector = SmartPromptSelector()
        prompt_data = smart_selector.select_next_prompt(user.id, preferred_category)

        if not prompt_data:
            return jsonify({'error': 'No prompts available'}), 404

        return jsonify({
            'prompt_id': prompt_data['id'],
            'text': prompt_data['text'],
            'category': prompt_data['category'],
            'difficulty_level': prompt_data['difficulty_level'],
            'selection_strategy': prompt_data.get('selection_strategy', 'balanced'),
            'metadata': prompt_data.get('metadata', {})
        })

    except Exception as e:
        logging.error(f"Error in api_next_prompt: {e}")
        return jsonify({'error': 'Internal server error'}), 500


@main_bp.route('/api/skip-prompt', methods=['POST'])
def api_skip_prompt():
    """Skip current prompt and get a new one"""
    try:
        user = get_or_create_user()
        data = request.get_json()
        prompt_id = data.get('prompt_id')

        if not prompt_id:
            return jsonify({'error': 'Prompt ID required'}), 400

        # Log the skip
        logging.info(f"User {user.session_id} skipped prompt {prompt_id}")

        # Get next prompt
        smart_selector = SmartPromptSelector()
        next_prompt = smart_selector.select_next_prompt(user.id)

        if not next_prompt:
            return jsonify({'error': 'No more prompts available'}), 404

        return jsonify({
            'prompt_id': next_prompt['id'],
            'text': next_prompt['text'],
            'category': next_prompt['category'],
            'message': 'Prompt skipped successfully'
        })

    except Exception as e:
        logging.error(f"Error in api_skip_prompt: {e}")
        return jsonify({'error': 'Internal server error'}), 500


@main_bp.route('/skip-prompt/<prompt_id>', methods=['POST'])
def skip_prompt(prompt_id):
    """Skip current prompt and return it to the available pool"""
    try:
        user = get_or_create_user()

        # Return the prompt to the available pool using CSV manager
        csv_manager = CSVPromptManager()
        success = csv_manager.return_prompt_to_pool(prompt_id)

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


@main_bp.route('/api/user-progress')
def api_user_progress():
    """Get user progress information"""
    try:
        user = get_or_create_user()

        # Get user statistics
        total_translations = Translation.query.filter_by(user_id=user.id).count()
        approved_translations = Translation.query.filter(
            Translation.user_id == user.id,
            Translation.status == 'approved'
        ).count()

        # Get category breakdown
        category_progress = db.session.query(
            Prompt.category,
            db.func.count(Translation.id).label('count')
        ).join(Translation).filter(
            Translation.user_id == user.id
        ).group_by(Prompt.category).all()

        categories = {
            category or 'unknown': count
            for category, count in category_progress
        }

        return jsonify({
            'total_translations': total_translations,
            'approved_translations': approved_translations,
            'approval_rate': (approved_translations / total_translations * 100) if total_translations > 0 else 0,
            'categories': categories,
            'member_since': user.created_at.isoformat(),
            'last_activity': user.last_activity.isoformat() if user.last_activity else None
        })

    except Exception as e:
        logging.error(f"Error in api_user_progress: {e}")
        return jsonify({'error': 'Internal server error'}), 500


@main_bp.route('/api/categories')
def api_categories():
    """Get available categories with statistics"""
    try:
        # Get category statistics
        category_stats = db.session.query(
            Prompt.category,
            db.func.count(Prompt.id).label('prompt_count'),
            db.func.count(Translation.id).label('translation_count'),
            db.func.avg(Prompt.quality_score).label('avg_quality')
        ).outerjoin(Translation).group_by(Prompt.category).all()

        categories = []
        for category, prompt_count, translation_count, avg_quality in category_stats:
            coverage_percentage = (translation_count / prompt_count * 100) if prompt_count > 0 else 0

            categories.append({
                'name': category or 'general',
                'prompt_count': prompt_count,
                'translation_count': translation_count,
                'coverage_percentage': round(coverage_percentage, 1),
                'average_quality': round(avg_quality or 0, 2),
                'needs_attention': coverage_percentage < 50
            })

        # Sort by coverage percentage (ascending) to highlight gaps
        categories.sort(key=lambda x: x['coverage_percentage'])

        return jsonify({
            'categories': categories,
            'total_categories': len(categories)
        })

    except Exception as e:
        logging.error(f"Error in api_categories: {e}")
        return jsonify({'error': 'Internal server error'}), 500


@main_bp.route('/api/platform-stats')
def api_platform_stats():
    """Get platform statistics for public display"""
    try:
        analytics_service = AnalyticsService()
        stats = analytics_service.get_overview_metrics()

        # Add some additional public metrics
        recent_activity = Translation.query.filter(
            Translation.timestamp >= datetime.utcnow() - timedelta(days=7)
        ).count()

        community_contributions = CommunitySubmission.query.filter_by(
            status='approved'
        ).count()

        public_stats = {
            'total_translations': stats['total_translations'],
            'approved_translations': stats['approved_translations'],
            'active_users': stats['total_users'],
            'recent_activity_week': recent_activity,
            'community_contributions': community_contributions,
            'platform_quality': round(stats.get('average_quality', 0.8), 2)
        }

        return jsonify(public_stats)

    except Exception as e:
        logging.error(f"Error in api_platform_stats: {e}")
        return jsonify({'error': 'Internal server error'}), 500


@main_bp.route('/statistics')
def statistics():
    """Public statistics page"""
    try:
        analytics_service = AnalyticsService()

        # Get comprehensive statistics for public display
        overview = analytics_service.get_overview_metrics()
        coverage = analytics_service.coverage_tracker.get_coverage_summary()
        trends = analytics_service.get_trend_data(days=30)

        return render_template(
            'statistics.html',
            overview=overview,
            coverage=coverage,
            trends=trends
        )

    except Exception as e:
        logging.error(f"Error in statistics route: {e}")
        flash('Error loading statistics. Please try again.', 'error')
        return redirect(url_for('main.index'))


@main_bp.route('/about')
def about():
    """About page with project information"""
    return render_template('about.html')


@main_bp.route('/help')
def help():
    """Help and FAQ page"""
    return render_template('help.html')


def get_recent_activity_summary():
    """Get recent activity summary for landing page"""
    try:
        from datetime import timedelta

        # Recent translations count
        week_ago = datetime.utcnow() - timedelta(days=7)
        recent_translations = Translation.query.filter(
            Translation.timestamp >= week_ago
        ).count()

        # Recent users count
        recent_users = User.query.filter(
            User.created_at >= week_ago
        ).count()

        # Recent community submissions
        recent_submissions = CommunitySubmission.query.filter(
            CommunitySubmission.submission_timestamp >= week_ago
        ).count()

        return {
            'recent_translations': recent_translations,
            'recent_users': recent_users,
            'recent_submissions': recent_submissions
        }

    except Exception as e:
        logging.error(f"Error getting recent activity: {e}")
        return {
            'recent_translations': 0,
            'recent_users': 0,
            'recent_submissions': 0
        }


@main_bp.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    """Admin login page"""
    from flask import session, current_app
    from app.forms import AdminLoginForm

    # If already logged in, redirect to admin dashboard
    if session.get('admin_logged_in'):
        return redirect(url_for('admin.dashboard'))

    form = AdminLoginForm()

    if form.validate_on_submit():
        password = form.password.data
        admin_password = current_app.config.get('ADMIN_PASSWORD', 'admin123')

        if password == admin_password:
            session['admin_logged_in'] = True
            session.permanent = True
            flash('Successfully logged in as admin', 'success')
            return redirect(url_for('admin.dashboard'))
        else:
            flash('Invalid admin password', 'error')

    return render_template('admin/login.html', form=form)


@main_bp.route('/admin/logout')
def admin_logout():
    """Admin logout"""
    from flask import session
    session.pop('admin_logged_in', None)
    flash('Successfully logged out', 'info')
    return redirect(url_for('main.index'))


# Error handlers
@main_bp.errorhandler(404)
def not_found_error(error):
    return render_template('errors/404.html'), 404


@main_bp.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('errors/500.html'), 500


@main_bp.errorhandler(429)
def rate_limit_error(error):
    return render_template('errors/429.html'), 429