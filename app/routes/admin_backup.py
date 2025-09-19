"""
Admin Routes for Hybrid Corpus Management
Comprehensive admin interface for managing the hybrid prompt system
"""

import json
import logging
import csv
from datetime import datetime, timedelta
from io import StringIO, BytesIO
from flask import (
    Blueprint, render_template, request, redirect, url_for, flash,
    jsonify, send_file, current_app
)
from werkzeug.utils import secure_filename

from app import db
from app.models import (
    Prompt, Translation, User, AdminAction, CommunitySubmission,
    DomainCoverage, CorpusStatistics, UserProgress
)
from app.utils import admin_required, is_admin
from app.services.corpus_builder import CorpusBuilder
from app.services.smart_selector import SmartPromptSelector, CoverageAnalyzer
from app.services.openrouter import OpenRouterClient
from app.services.community_service import CommunitySubmissionService
from app.services.quality_control import QualityControlPipeline


# Create admin blueprint
admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


@admin_bp.route('/')
@admin_required
def dashboard():
    """Simplified admin dashboard"""
    from app.models import Translation, User, Prompt
    from app.services.csv_prompt_manager import CSVPromptManager

    # Get basic statistics
    total_translations = Translation.query.count()
    pending_translations = Translation.query.filter_by(status='pending').count()
    approved_translations = Translation.query.filter_by(status='approved').count()
    total_users = User.query.count()

    stats = {
        'total_translations': total_translations,
        'pending_translations': pending_translations,
        'approved_translations': approved_translations,
        'total_users': total_users
    }

    # Get CSV cache statistics
    try:
        csv_manager = CSVPromptManager()
        cache_stats = csv_manager.get_cache_stats()
    except Exception as e:
        cache_stats = {
            'total_prompts': 0,
            'used_prompts': 0,
            'available_prompts': 0,
            'cache_health': 'unknown'
        }

    return render_template(
        'admin/dashboard.html',
        stats=stats,
        cache_stats=cache_stats,
        recent_activity=[],
        system_health={'status': 'ok'}
    )


@admin_bp.route('/corpus-management')
@admin_required
def corpus_management():
    """Corpus building and management interface"""
    corpus_builder = CorpusBuilder()

    # Get current corpus statistics
    corpus_stats = corpus_builder.analyze_coverage()

    # Get source distribution
    source_distribution = get_source_distribution()

    # Get recent builds
    recent_builds = get_recent_corpus_builds()

    return render_template(
        'admin/corpus_management.html',
        corpus_stats=corpus_stats,
        source_distribution=source_distribution,
        recent_builds=recent_builds
    )


@admin_bp.route('/build-corpus', methods=['POST'])
@admin_required
def build_corpus():
    """Build corpus from various sources"""
    build_type = request.form.get('build_type', 'initial')
    target_size = int(request.form.get('target_size', 10000))

    try:
        corpus_builder = CorpusBuilder()

        if build_type == 'initial':
            results = corpus_builder.build_initial_corpus(target_size)
            flash(f'Initial corpus built: {sum(results.values())} sentences', 'success')

        elif build_type == 'scale':
            results = corpus_builder.scale_corpus(target_size)
            flash(f'Corpus scaled: {sum(results.values())} sentences added', 'success')

        elif build_type == 'gap_fill':
            # Use smart selector to identify gaps
            analyzer = CoverageAnalyzer()
            gaps = analyzer.analyze_gaps()

            # Generate targeted prompts
            openrouter = OpenRouterClient()
            if openrouter.can_make_api_call():
                prompts = openrouter.generate_targeted_prompts(gaps, target_size)

                # Save to database
                saved_count = 0
                for prompt_data in prompts:
                    prompt = Prompt(
                        text=prompt_data['text'],
                        category=prompt_data['category'],
                        source_type=prompt_data['source_type'],
                        source_file=prompt_data['source_file'],
                        difficulty_level=prompt_data['difficulty_level'],
                        quality_score=prompt_data['quality_score'],
                        prompt_metadata=json.dumps(prompt_data.get('metadata', {}))
                    )
                    db.session.add(prompt)
                    saved_count += 1

                db.session.commit()
                flash(f'Gap-filling complete: {saved_count} targeted prompts generated', 'success')
            else:
                flash('API limit reached. Cannot generate new prompts today.', 'error')

        # Log the corpus build
        log_admin_action(
            'corpus_build',
            f'Built {build_type} corpus with target size {target_size}',
            details={'build_type': build_type, 'target_size': target_size, 'results': results}
        )

    except Exception as e:
        logging.error(f"Error building corpus: {e}")
        flash(f'Error building corpus: {str(e)}', 'error')
        db.session.rollback()

    return redirect(url_for('admin.corpus_management'))


@admin_bp.route('/prompt-management')
@admin_required
def prompt_management():
    """Manage individual prompts"""
    page = request.args.get('page', 1, type=int)
    category = request.args.get('category', '')
    source_type = request.args.get('source_type', '')
    quality_filter = request.args.get('quality', '')

    # Build query
    query = Prompt.query

    if category:
        query = query.filter_by(category=category)
    if source_type:
        query = query.filter_by(source_type=source_type)
    if quality_filter:
        if quality_filter == 'high':
            query = query.filter(Prompt.quality_score >= 0.8)
        elif quality_filter == 'low':
            query = query.filter(Prompt.quality_score < 0.6)

    # Paginate results
    prompts = query.order_by(Prompt.date_generated.desc()).paginate(
        page=page, per_page=50, error_out=False
    )

    # Get filter options
    categories = db.session.query(Prompt.category).distinct().all()
    categories = [cat[0] for cat in categories if cat[0]]

    source_types = db.session.query(Prompt.source_type).distinct().all()
    source_types = [source[0] for source in source_types if source[0]]

    return render_template(
        'admin/prompt_management.html',
        prompts=prompts,
        categories=categories,
        source_types=source_types,
        current_filters={
            'category': category,
            'source_type': source_type,
            'quality': quality_filter
        }
    )


@admin_bp.route('/prompt/<int:prompt_id>/edit', methods=['GET', 'POST'])
@admin_required
def edit_prompt(prompt_id):
    """Edit individual prompt"""
    prompt = Prompt.query.get_or_404(prompt_id)

    if request.method == 'POST':
        try:
            prompt.text = request.form['text']
            prompt.category = request.form['category']
            prompt.difficulty_level = request.form['difficulty_level']
            prompt.status = request.form['status']

            # Recalculate quality score if text changed
            if request.form['text'] != prompt.text:
                from app.services.quality_control import PromptValidator
                validator = PromptValidator()
                validation_result = validator.validate_prompt(prompt)
                if validation_result.get('calculated_quality'):
                    prompt.quality_score = validation_result['calculated_quality']

            db.session.commit()

            log_admin_action(
                'prompt_edit',
                f'Edited prompt {prompt_id}',
                details={'prompt_id': prompt_id, 'changes': request.form.to_dict()}
            )

            flash('Prompt updated successfully', 'success')
            return redirect(url_for('admin.prompt_management'))

        except Exception as e:
            logging.error(f"Error updating prompt {prompt_id}: {e}")
            flash(f'Error updating prompt: {str(e)}', 'error')
            db.session.rollback()

    return render_template('admin/edit_prompt.html', prompt=prompt)


@admin_bp.route('/prompt/<int:prompt_id>/delete', methods=['POST'])
@admin_required
def delete_prompt(prompt_id):
    """Delete a prompt"""
    prompt = Prompt.query.get_or_404(prompt_id)

    try:
        # Check if prompt has translations
        translation_count = Translation.query.filter_by(prompt_id=prompt_id).count()

        if translation_count > 0:
            # Soft delete - mark as inactive
            prompt.status = 'deleted'
            db.session.commit()
            flash(f'Prompt marked as deleted (has {translation_count} translations)', 'success')
        else:
            # Hard delete
            db.session.delete(prompt)
            db.session.commit()
            flash('Prompt permanently deleted', 'success')

        log_admin_action(
            'prompt_delete',
            f'Deleted prompt {prompt_id}',
            details={'prompt_id': prompt_id, 'had_translations': translation_count > 0}
        )

    except Exception as e:
        logging.error(f"Error deleting prompt {prompt_id}: {e}")
        flash(f'Error deleting prompt: {str(e)}', 'error')
        db.session.rollback()

    return redirect(url_for('admin.prompt_management'))


@admin_bp.route('/translation-review')
@admin_required
def translation_review():
    """Review pending translations"""
    page = request.args.get('page', 1, type=int)
    status_filter = request.args.get('status', 'pending')
    category_filter = request.args.get('category', '')

    # Build query
    query = Translation.query.join(Prompt)

    if status_filter:
        query = query.filter(Translation.status == status_filter)
    if category_filter:
        query = query.filter(Prompt.category == category_filter)

    translations = query.order_by(Translation.timestamp.desc()).paginate(
        page=page, per_page=20, error_out=False
    )

    # Get categories for filter
    categories = db.session.query(Prompt.category).distinct().all()
    categories = [cat[0] for cat in categories if cat[0]]

    return render_template(
        'admin/translation_review.html',
        translations=translations,
        categories=categories,
        current_filters={
            'status': status_filter,
            'category': category_filter
        }
    )


@admin_bp.route('/translation/<int:translation_id>/moderate', methods=['POST'])
@admin_required
def moderate_translation(translation_id):
    """Moderate a translation (approve/reject/flag)"""
    translation = Translation.query.get_or_404(translation_id)
    action = request.form.get('action')
    notes = request.form.get('notes', '')

    try:
        if action == 'approve':
            translation.status = 'approved'
        elif action == 'reject':
            translation.status = 'rejected'
        elif action == 'flag':
            translation.status = 'flagged'
        else:
            flash('Invalid action', 'error')
            return redirect(url_for('admin.translation_review'))

        # Log admin action
        admin_action = AdminAction(
            translation_id=translation_id,
            action=action,
            admin_id=request.remote_addr,  # Use IP as admin ID for now
            notes=notes
        )
        db.session.add(admin_action)
        db.session.commit()

        flash(f'Translation {action}ed successfully', 'success')

        log_admin_action(
            'translation_moderate',
            f'{action.title()}ed translation {translation_id}',
            details={'translation_id': translation_id, 'action': action, 'notes': notes}
        )

    except Exception as e:
        logging.error(f"Error moderating translation {translation_id}: {e}")
        flash(f'Error moderating translation: {str(e)}', 'error')
        db.session.rollback()

    return redirect(url_for('admin.translation_review'))


@admin_bp.route('/community-submissions')
@admin_required
def community_submissions():
    """Review community-submitted prompts"""
    page = request.args.get('page', 1, type=int)
    status_filter = request.args.get('status', 'pending')

    query = CommunitySubmission.query
    if status_filter:
        query = query.filter_by(status=status_filter)

    submissions = query.order_by(
        CommunitySubmission.quality_score.desc(),
        CommunitySubmission.submission_timestamp.desc()
    ).paginate(page=page, per_page=20, error_out=False)

    # Get submission statistics
    submission_stats = CommunitySubmissionService().get_submission_stats()

    return render_template(
        'admin/community_submissions.html',
        submissions=submissions,
        submission_stats=submission_stats,
        current_status=status_filter
    )


@admin_bp.route('/community-submission/<int:submission_id>/review', methods=['POST'])
@admin_required
def review_community_submission(submission_id):
    """Review a community submission"""
    action = request.form.get('action')
    notes = request.form.get('notes', '')
    admin_id = request.remote_addr  # Use IP as admin ID for now

    try:
        community_service = CommunitySubmissionService()
        result = community_service.review_submission(submission_id, action, admin_id, notes)

        if result['success']:
            flash(result['message'], 'success')
            log_admin_action(
                'community_review',
                f'Reviewed community submission {submission_id}: {action}',
                details={'submission_id': submission_id, 'action': action, 'notes': notes}
            )
        else:
            flash(result['error'], 'error')

    except Exception as e:
        logging.error(f"Error reviewing community submission {submission_id}: {e}")
        flash(f'Error reviewing submission: {str(e)}', 'error')

    return redirect(url_for('admin.community_submissions'))


@admin_bp.route('/quality-control')
@admin_required
def quality_control():
    """Quality control dashboard"""
    # Run quality audit
    qc_pipeline = QualityControlPipeline()
    audit_results = qc_pipeline.run_full_quality_audit()

    return render_template(
        'admin/quality_control.html',
        audit_results=audit_results
    )


@admin_bp.route('/run-quality-audit', methods=['POST'])
@admin_required
def run_quality_audit():
    """Run comprehensive quality audit"""
    try:
        qc_pipeline = QualityControlPipeline()
        audit_results = qc_pipeline.run_full_quality_audit()

        flash(f'Quality audit completed. Found {audit_results["prompt_audit"]["invalid_prompts"]} invalid prompts', 'success')

        log_admin_action(
            'quality_audit',
            'Ran comprehensive quality audit',
            details={'results_summary': {
                'invalid_prompts': audit_results["prompt_audit"]["invalid_prompts"],
                'invalid_translations': audit_results["translation_audit"]["invalid_translations"],
                'total_duplicates': audit_results["duplicate_analysis"]["total_duplicates"]
            }}
        )

    except Exception as e:
        logging.error(f"Error running quality audit: {e}")
        flash(f'Error running quality audit: {str(e)}', 'error')

    return redirect(url_for('admin.quality_control'))


@admin_bp.route('/analytics')
@admin_required
def analytics():
    """Analytics and reporting dashboard"""
    # Get comprehensive analytics
    analytics_data = get_comprehensive_analytics()

    return render_template(
        'admin/analytics.html',
        analytics=analytics_data
    )


@admin_bp.route('/export-data')
@admin_required
def export_data():
    """Export data in various formats"""
    export_type = request.args.get('type', 'translations')
    format_type = request.args.get('format', 'csv')

    try:
        if export_type == 'translations':
            data = export_translations_data()
        elif export_type == 'prompts':
            data = export_prompts_data()
        elif export_type == 'users':
            data = export_users_data()
        else:
            flash('Invalid export type', 'error')
            return redirect(url_for('admin.analytics'))

        if format_type == 'csv':
            return send_csv_file(data, f'{export_type}_{datetime.now().strftime("%Y%m%d")}.csv')
        elif format_type == 'json':
            return send_json_file(data, f'{export_type}_{datetime.now().strftime("%Y%m%d")}.json')

        log_admin_action(
            'data_export',
            f'Exported {export_type} data in {format_type} format',
            details={'export_type': export_type, 'format': format_type, 'record_count': len(data)}
        )

    except Exception as e:
        logging.error(f"Error exporting data: {e}")
        flash(f'Error exporting data: {str(e)}', 'error')
        return redirect(url_for('admin.analytics'))


@admin_bp.route('/api-status')
@admin_required
def api_status():
    """Check OpenRouter API status and usage"""
    openrouter = OpenRouterClient()

    # Test connection
    connection_test = openrouter.test_connection()

    # Get usage statistics
    usage_stats = openrouter.get_usage_statistics()

    return render_template(
        'admin/api_status.html',
        connection_test=connection_test,
        usage_stats=usage_stats
    )


@admin_bp.route('/manual-refill', methods=['POST'])
@admin_required
def manual_refill():
    """Manually trigger prompt cache refill"""
    try:
        count = int(request.form.get('count', 20))
        generation_type = request.form.get('type', 'general')

        openrouter = OpenRouterClient()

        if not openrouter.can_make_api_call():
            flash('API daily limit reached. Cannot generate new prompts.', 'error')
            return redirect(url_for('admin.api_status'))

        if generation_type == 'gap_fill':
            # Generate targeted prompts for gaps
            analyzer = CoverageAnalyzer()
            gaps = analyzer.analyze_gaps()
            prompts = openrouter.generate_targeted_prompts(gaps, count)
        elif generation_type == 'cultural':
            # Generate cultural prompts
            prompts = openrouter.generate_cultural_prompts(count)
        else:
            # Generate general prompts
            prompts = openrouter.generate_multiple_prompts(count)

        # Save to database
        saved_count = 0
        for prompt_data in prompts:
            prompt = Prompt(
                text=prompt_data['text'],
                category=prompt_data['category'],
                source_type='llm',
                source_file=prompt_data.get('source_file', 'manual_generation'),
                difficulty_level=prompt_data.get('difficulty_level', 'basic'),
                quality_score=prompt_data.get('quality_score', 0.8),
                prompt_metadata=json.dumps(prompt_data.get('metadata', {}))
            )
            db.session.add(prompt)
            saved_count += 1

        db.session.commit()

        flash(f'Successfully generated {saved_count} new prompts', 'success')

        log_admin_action(
            'manual_refill',
            f'Manually generated {saved_count} prompts',
            details={'count': saved_count, 'type': generation_type}
        )

    except Exception as e:
        logging.error(f"Error in manual refill: {e}")
        flash(f'Error generating prompts: {str(e)}', 'error')
        db.session.rollback()

    return redirect(url_for('admin.api_status'))


def get_dashboard_statistics():
    """Get comprehensive dashboard statistics"""
    stats = {}

    # Prompt statistics
    stats['prompts'] = {
        'total': Prompt.query.count(),
        'active': Prompt.query.filter_by(status='active').count(),
        'by_source': {}
    }

    # Source distribution
    source_counts = db.session.query(
        Prompt.source_type,
        db.func.count(Prompt.id).label('count')
    ).group_by(Prompt.source_type).all()

    for source, count in source_counts:
        stats['prompts']['by_source'][source] = count

    # Translation statistics
    stats['translations'] = {
        'total': Translation.query.count(),
        'pending': Translation.query.filter_by(status='pending').count(),
        'approved': Translation.query.filter_by(status='approved').count(),
        'rejected': Translation.query.filter_by(status='rejected').count()
    }

    # User statistics
    stats['users'] = {
        'total': User.query.count(),
        'active_week': User.query.filter(
            User.last_activity >= datetime.utcnow() - timedelta(days=7)
        ).count()
    }

    # Community submissions
    stats['community'] = {
        'total': CommunitySubmission.query.count(),
        'pending': CommunitySubmission.query.filter_by(status='pending').count(),
        'approved': CommunitySubmission.query.filter_by(status='approved').count()
    }

    # Quality statistics
    avg_quality = db.session.query(db.func.avg(Prompt.quality_score)).scalar()
    stats['quality'] = {
        'average_score': round(avg_quality or 0, 2),
        'high_quality': Prompt.query.filter(Prompt.quality_score >= 0.8).count(),
        'low_quality': Prompt.query.filter(Prompt.quality_score < 0.6).count()
    }

    return stats


def get_recent_activity():
    """Get recent system activity"""
    activities = []

    # Recent translations
    recent_translations = Translation.query.order_by(
        Translation.timestamp.desc()
    ).limit(5).all()

    for translation in recent_translations:
        activities.append({
            'type': 'translation',
            'description': f'New translation submitted for prompt {translation.prompt_id}',
            'timestamp': translation.timestamp,
            'details': {'translation_id': translation.id}
        })

    # Recent community submissions
    recent_submissions = CommunitySubmission.query.order_by(
        CommunitySubmission.submission_timestamp.desc()
    ).limit(3).all()

    for submission in recent_submissions:
        activities.append({
            'type': 'community_submission',
            'description': f'New community prompt submitted: "{submission.text[:50]}..."',
            'timestamp': submission.submission_timestamp,
            'details': {'submission_id': submission.id}
        })

    # Sort by timestamp
    activities.sort(key=lambda x: x['timestamp'], reverse=True)

    return activities[:10]


def check_system_health():
    """Check overall system health"""
    health = {
        'status': 'healthy',
        'issues': [],
        'warnings': []
    }

    # Check prompt availability
    active_prompts = Prompt.query.filter_by(status='active').count()
    if active_prompts < 100:
        health['warnings'].append(f'Low prompt count: {active_prompts}')
        if active_prompts < 10:
            health['status'] = 'warning'

    # Check pending reviews
    pending_translations = Translation.query.filter_by(status='pending').count()
    if pending_translations > 50:
        health['warnings'].append(f'High pending review count: {pending_translations}')

    pending_submissions = CommunitySubmission.query.filter_by(status='pending').count()
    if pending_submissions > 20:
        health['warnings'].append(f'High pending submissions: {pending_submissions}')

    # Check API usage
    openrouter = OpenRouterClient()
    usage_stats = openrouter.get_usage_statistics()
    if usage_stats['remaining_calls'] < 5:
        health['warnings'].append('Low API calls remaining')
        if usage_stats['remaining_calls'] == 0:
            health['status'] = 'warning'

    return health


def get_source_distribution():
    """Get prompt source distribution"""
    distribution = db.session.query(
        Prompt.source_type,
        db.func.count(Prompt.id).label('count'),
        db.func.avg(Prompt.quality_score).label('avg_quality')
    ).group_by(Prompt.source_type).all()

    return [
        {
            'source': source,
            'count': count,
            'avg_quality': round(avg_quality or 0, 2)
        }
        for source, count, avg_quality in distribution
    ]


def get_recent_corpus_builds():
    """Get recent corpus building activities"""
    # This would query a corpus_builds table if we had one
    # For now, return empty list
    return []


def get_comprehensive_analytics():
    """Get comprehensive analytics data"""
    analytics = {}

    # Translation trends
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    daily_translations = db.session.query(
        db.func.date(Translation.timestamp).label('date'),
        db.func.count(Translation.id).label('count')
    ).filter(
        Translation.timestamp >= thirty_days_ago
    ).group_by(
        db.func.date(Translation.timestamp)
    ).all()

    analytics['translation_trends'] = [
        {'date': date.isoformat(), 'count': count}
        for date, count in daily_translations
    ]

    # Category distribution
    category_stats = db.session.query(
        Prompt.category,
        db.func.count(Translation.id).label('translation_count'),
        db.func.count(Prompt.id).label('prompt_count')
    ).outerjoin(Translation).group_by(Prompt.category).all()

    analytics['category_distribution'] = [
        {
            'category': category or 'unknown',
            'prompts': prompt_count,
            'translations': translation_count
        }
        for category, translation_count, prompt_count in category_stats
    ]

    # User engagement
    user_stats = db.session.query(
        db.func.count(Translation.id).label('translation_count'),
        User.id
    ).join(Translation).group_by(User.id).all()

    engagement_distribution = {}
    for translation_count, user_id in user_stats:
        bucket = f"{min(translation_count // 5 * 5, 20)}+"
        engagement_distribution[bucket] = engagement_distribution.get(bucket, 0) + 1

    analytics['user_engagement'] = engagement_distribution

    return analytics


def export_translations_data():
    """Export translations data"""
    translations = db.session.query(
        Translation.id,
        Translation.kikuyu_text,
        Prompt.text.label('english_text'),
        Prompt.category,
        Translation.status,
        Translation.timestamp,
        User.session_id.label('user_session')
    ).join(Prompt).join(User).all()

    return [
        {
            'id': t.id,
            'english_text': t.english_text,
            'kikuyu_text': t.kikuyu_text,
            'category': t.category,
            'status': t.status,
            'timestamp': t.timestamp.isoformat(),
            'user_session': t.user_session
        }
        for t in translations
    ]


def export_prompts_data():
    """Export prompts data"""
    prompts = Prompt.query.all()

    return [
        {
            'id': p.id,
            'text': p.text,
            'category': p.category,
            'source_type': p.source_type,
            'difficulty_level': p.difficulty_level,
            'quality_score': p.quality_score,
            'usage_count': p.usage_count,
            'status': p.status,
            'date_generated': p.date_generated.isoformat()
        }
        for p in prompts
    ]


def export_users_data():
    """Export users data"""
    users = db.session.query(
        User.id,
        User.session_id,
        User.created_at,
        User.submission_count,
        User.last_activity,
        db.func.count(Translation.id).label('total_translations')
    ).outerjoin(Translation).group_by(User.id).all()

    return [
        {
            'id': u.id,
            'session_id': u.session_id,
            'created_at': u.created_at.isoformat(),
            'submission_count': u.submission_count,
            'last_activity': u.last_activity.isoformat() if u.last_activity else None,
            'total_translations': u.total_translations
        }
        for u in users
    ]


def send_csv_file(data, filename):
    """Send data as CSV file"""
    if not data:
        flash('No data to export', 'warning')
        return redirect(url_for('admin.analytics'))

    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=data[0].keys())
    writer.writeheader()
    writer.writerows(data)

    mem = BytesIO()
    mem.write(output.getvalue().encode('utf-8'))
    mem.seek(0)

    return send_file(
        mem,
        as_attachment=True,
        download_name=filename,
        mimetype='text/csv'
    )


def send_json_file(data, filename):
    """Send data as JSON file"""
    json_data = json.dumps(data, indent=2, default=str)

    mem = BytesIO()
    mem.write(json_data.encode('utf-8'))
    mem.seek(0)

    return send_file(
        mem,
        as_attachment=True,
        download_name=filename,
        mimetype='application/json'
    )


def log_admin_action(action_type, description, details=None):
    """Log admin action for audit trail"""
    try:
        # This would log to an admin_audit table if we had one
        logging.info(f"Admin action: {action_type} - {description}")
        if details:
            logging.info(f"Details: {json.dumps(details)}")
    except Exception as e:
        logging.error(f"Error logging admin action: {e}")


# Register the blueprint in your app/__init__.py or main routes file
# app.register_blueprint(admin_bp)