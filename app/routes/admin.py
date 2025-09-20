"""
Simplified Admin Routes - Working Basic Functionality Only
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from app import db
from app.models import Translation, User, Prompt
from app.utils import admin_required
from app.services.csv_prompt_manager import CSVPromptManager

# Create admin blueprint
admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


@admin_bp.route('/')
@admin_required
def dashboard():
    """Simple working admin dashboard"""
    try:
        # Get basic statistics from database
        # Note: Rejected translations are no longer stored (returned to CSV pool)
        total_translations = db.session.query(Translation).count()
        pending_translations = db.session.query(Translation).filter_by(status='pending').count()
        approved_translations = db.session.query(Translation).filter_by(status='approved').count()
        total_users = db.session.query(User).count()

        stats = {
            'total_translations': total_translations,
            'pending_translations': pending_translations,
            'approved_translations': approved_translations,
            'rejected_translations': 0,  # No longer stored - returned to CSV pool
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
                'cache_health': 'unknown',
                'csv_total_sentences': 0,
                'csv_used_sentences': 0,
                'csv_remaining_sentences': 0
            }

        # Get recent translations for dashboard
        recent_translations = db.session.query(Translation, Prompt, User)\
            .outerjoin(Prompt, Translation.prompt_id == Prompt.id)\
            .outerjoin(User, Translation.user_id == User.id)\
            .order_by(Translation.timestamp.desc())\
            .limit(10).all()

        return render_template(
            'admin/dashboard.html',
            stats=stats,
            cache_stats=cache_stats,
            recent_translations=recent_translations
        )

    except Exception as e:
        flash(f'Error loading dashboard: {str(e)}', 'error')
        return render_template(
            'admin/dashboard.html',
            stats={'total_translations': 0, 'pending_translations': 0, 'approved_translations': 0, 'total_users': 0},
            cache_stats={'total_prompts': 0, 'used_prompts': 0, 'available_prompts': 0, 'cache_health': 'error'},
            recent_translations=[]
        )


@admin_bp.route('/translations')
@admin_required
def view_translations():
    """View all translations with filtering"""
    status_filter = request.args.get('status', 'all')
    page = request.args.get('page', 1, type=int)

    query = Translation.query

    if status_filter != 'all':
        query = query.filter_by(status=status_filter)

    translations = query.order_by(Translation.timestamp.desc()).paginate(
        page=page, per_page=20, error_out=False
    )

    return render_template(
        'admin/translations.html',
        translations=translations,
        status_filter=status_filter
    )


@admin_bp.route('/translation/<int:translation_id>/moderate', methods=['POST'])
@admin_required
def moderate_translation(translation_id):
    """Moderate a translation"""
    translation = Translation.query.get_or_404(translation_id)
    action = request.form.get('action')

    if action == 'approve':
        # Approve and keep translation
        translation.status = 'approved'
        db.session.commit()
        flash('Translation approved successfully', 'success')
    elif action == 'reject':
        # Return prompt back to CSV pool and delete rejected translation
        try:
            prompt = translation.prompt
            if prompt:
                # Return prompt back to CSV for reuse
                csv_manager = CSVPromptManager()
                # Generate the same ID that CSV manager uses (MD5 hash of text)
                import hashlib
                prompt_id = hashlib.md5(prompt.text.encode('utf-8')).hexdigest()[:12]
                csv_manager.return_prompt_to_pool(prompt_id)

                # Delete the rejected translation (don't store rejections)
                db.session.delete(translation)
                db.session.commit()

                flash('Translation rejected and prompt returned to pool for reuse', 'success')
            else:
                # If no prompt found, just delete the translation
                db.session.delete(translation)
                db.session.commit()
                flash('Translation rejected and removed', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error processing rejection: {str(e)}', 'error')
    else:
        flash('Invalid action', 'error')

    return redirect(url_for('admin.view_translations'))


@admin_bp.route('/cache-status')
@admin_required
def cache_status():
    """View CSV cache status"""
    try:
        csv_manager = CSVPromptManager()
        cache_stats = csv_manager.get_cache_stats()
        dataset_info = csv_manager.get_dataset_info()

        # Add connection test for template compatibility
        connection_test = {
            'success': True,
            'message': 'CSV dataset connection is active',
            'sample_prompt': None
        }

        return render_template(
            'admin/cache_status.html',
            cache_stats=cache_stats,
            dataset_info=dataset_info,
            connection_test=connection_test
        )
    except Exception as e:
        flash(f'Error loading cache status: {str(e)}', 'error')
        return redirect(url_for('admin.dashboard'))


@admin_bp.route('/refill-cache', methods=['POST'])
@admin_required
def refill_cache():
    """Refill prompt cache from CSV"""
    try:
        csv_manager = CSVPromptManager()
        success = csv_manager.refill_cache(force=True)

        if success:
            flash('Cache refilled successfully', 'success')
        else:
            flash('Failed to refill cache', 'error')

    except Exception as e:
        flash(f'Error refilling cache: {str(e)}', 'error')

    return redirect(url_for('admin.cache_status'))


@admin_bp.route('/export')
@admin_required
def export():
    """Export approved translations"""
    try:
        format_type = request.args.get('format', 'json')
        status_filter = request.args.get('status', 'approved')

        query = Translation.query.filter_by(status=status_filter)
        translations = query.all()

        if format_type == 'json':
            import json
            data = []
            for t in translations:
                data.append({
                    'id': t.id,
                    'english': t.prompt.text if t.prompt else '',
                    'kikuyu': t.kikuyu_text,
                    'status': t.status,
                    'created_at': t.timestamp.isoformat() if t.timestamp else None
                })

            response = jsonify(data)
            response.headers['Content-Disposition'] = f'attachment; filename=translations_{status_filter}.json'
            return response

        else:  # CSV format
            import csv
            import io
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(['ID', 'English', 'Kikuyu', 'Status', 'Created At'])

            for t in translations:
                writer.writerow([
                    t.id,
                    t.prompt.text if t.prompt else '',
                    t.kikuyu_text,
                    t.status,
                    t.timestamp.isoformat() if t.timestamp else ''
                ])

            output.seek(0)
            from flask import make_response
            response = make_response(output.getvalue())
            response.headers['Content-Type'] = 'text/csv'
            response.headers['Content-Disposition'] = f'attachment; filename=translations_{status_filter}.csv'
            return response

    except Exception as e:
        flash(f'Error exporting data: {str(e)}', 'error')
        return redirect(url_for('admin.dashboard'))


@admin_bp.route('/stats')
@admin_required
def stats():
    """Simple statistics page"""
    try:
        # Get basic counts
        total_translations = Translation.query.count()
        by_status = {
            'pending': Translation.query.filter_by(status='pending').count(),
            'approved': Translation.query.filter_by(status='approved').count(),
            'rejected': 0  # No longer stored - rejected translations are deleted and returned to CSV pool
        }

        total_users = User.query.count()
        total_prompts = Prompt.query.count()

        # Get CSV stats
        csv_manager = CSVPromptManager()
        csv_stats = csv_manager.get_cache_stats()

        return render_template(
            'admin/stats.html',
            total_translations=total_translations,
            by_status=by_status,
            total_users=total_users,
            total_prompts=total_prompts,
            csv_stats=csv_stats
        )

    except Exception as e:
        flash(f'Error loading statistics: {str(e)}', 'error')
        return redirect(url_for('admin.dashboard'))