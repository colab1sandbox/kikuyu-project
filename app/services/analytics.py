"""
Analytics and Coverage Tracking Service
Comprehensive analytics for the hybrid translation platform
"""

import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from collections import defaultdict, Counter
from sqlalchemy import func, and_, or_, desc, extract

from app.models import (
    Prompt, Translation, User, CommunitySubmission,
    DomainCoverage, CorpusStatistics, UserProgress, db
)


class AnalyticsService:
    """Main analytics service for comprehensive platform insights"""

    def __init__(self):
        self.coverage_tracker = CoverageTracker()
        self.user_analytics = UserAnalytics()
        self.quality_analytics = QualityAnalytics()
        self.performance_analytics = PerformanceAnalytics()

    def get_dashboard_metrics(self) -> Dict:
        """Get key metrics for admin dashboard"""
        return {
            'overview': self.get_overview_metrics(),
            'coverage': self.coverage_tracker.get_coverage_summary(),
            'user_engagement': self.user_analytics.get_engagement_summary(),
            'quality_metrics': self.quality_analytics.get_quality_summary(),
            'performance': self.performance_analytics.get_performance_summary(),
            'trends': self.get_trend_data()
        }

    def get_overview_metrics(self) -> Dict:
        """Get high-level overview metrics"""
        total_prompts = Prompt.query.filter_by(status='active').count()
        total_translations = Translation.query.count()
        approved_translations = Translation.query.filter_by(status='approved').count()
        total_users = User.query.count()
        active_users_week = User.query.filter(
            User.last_activity >= datetime.utcnow() - timedelta(days=7)
        ).count()

        return {
            'total_prompts': total_prompts,
            'total_translations': total_translations,
            'approved_translations': approved_translations,
            'approval_rate': (approved_translations / total_translations * 100) if total_translations > 0 else 0,
            'total_users': total_users,
            'active_users_week': active_users_week,
            'engagement_rate': (active_users_week / total_users * 100) if total_users > 0 else 0
        }

    def get_trend_data(self, days: int = 30) -> Dict:
        """Get trend data for the last N days"""
        start_date = datetime.utcnow() - timedelta(days=days)

        # Daily translation trends
        daily_translations = db.session.query(
            func.date(Translation.timestamp).label('date'),
            func.count(Translation.id).label('count')
        ).filter(
            Translation.timestamp >= start_date
        ).group_by(
            func.date(Translation.timestamp)
        ).order_by('date').all()

        # Daily user registration trends
        daily_users = db.session.query(
            func.date(User.created_at).label('date'),
            func.count(User.id).label('count')
        ).filter(
            User.created_at >= start_date
        ).group_by(
            func.date(User.created_at)
        ).order_by('date').all()

        # Daily prompt creation trends
        daily_prompts = db.session.query(
            func.date(Prompt.date_generated).label('date'),
            func.count(Prompt.id).label('count')
        ).filter(
            Prompt.date_generated >= start_date
        ).group_by(
            func.date(Prompt.date_generated)
        ).order_by('date').all()

        return {
            'daily_translations': [
                {'date': date.isoformat(), 'count': count}
                for date, count in daily_translations
            ],
            'daily_users': [
                {'date': date.isoformat(), 'count': count}
                for date, count in daily_users
            ],
            'daily_prompts': [
                {'date': date.isoformat(), 'count': count}
                for date, count in daily_prompts
            ]
        }

    def generate_comprehensive_report(self) -> Dict:
        """Generate comprehensive analytics report"""
        report = {
            'generated_at': datetime.utcnow().isoformat(),
            'overview': self.get_overview_metrics(),
            'coverage_analysis': self.coverage_tracker.get_detailed_coverage(),
            'user_analytics': self.user_analytics.get_detailed_analytics(),
            'quality_analysis': self.quality_analytics.get_detailed_analysis(),
            'performance_metrics': self.performance_analytics.get_detailed_metrics(),
            'recommendations': self.generate_recommendations()
        }

        return report

    def generate_recommendations(self) -> List[Dict]:
        """Generate actionable recommendations based on analytics"""
        recommendations = []

        # Coverage recommendations
        coverage_data = self.coverage_tracker.get_coverage_summary()
        for category, data in coverage_data.get('by_category', {}).items():
            if data['completion_percentage'] < 25:
                recommendations.append({
                    'type': 'critical',
                    'area': 'coverage',
                    'category': category,
                    'issue': f'Very low coverage in {category}',
                    'recommendation': f'Focus on generating more {category} prompts',
                    'priority': 'high'
                })

        # User engagement recommendations
        engagement_data = self.user_analytics.get_engagement_summary()
        if engagement_data['average_submissions_per_user'] < 3:
            recommendations.append({
                'type': 'warning',
                'area': 'user_engagement',
                'issue': 'Low user engagement',
                'recommendation': 'Improve user experience and incentives',
                'priority': 'medium'
            })

        # Quality recommendations
        quality_data = self.quality_analytics.get_quality_summary()
        if quality_data['average_quality'] < 0.7:
            recommendations.append({
                'type': 'warning',
                'area': 'quality',
                'issue': 'Below-average quality scores',
                'recommendation': 'Review and improve prompt generation sources',
                'priority': 'medium'
            })

        return recommendations


class CoverageTracker:
    """Track translation coverage across domains and categories"""

    def get_coverage_summary(self) -> Dict:
        """Get summary of coverage across all categories"""
        # Get coverage by category
        category_coverage = db.session.query(
            Prompt.category,
            func.count(Prompt.id).label('prompt_count'),
            func.count(Translation.id).label('translation_count')
        ).outerjoin(Translation).group_by(Prompt.category).all()

        coverage_by_category = {}
        total_prompts = 0
        total_translations = 0

        for category, prompt_count, translation_count in category_coverage:
            category_name = category or 'unknown'
            coverage_percentage = (translation_count / prompt_count * 100) if prompt_count > 0 else 0

            coverage_by_category[category_name] = {
                'prompt_count': prompt_count,
                'translation_count': translation_count,
                'coverage_percentage': round(coverage_percentage, 2)
            }

            total_prompts += prompt_count
            total_translations += translation_count

        # Overall coverage
        overall_coverage = (total_translations / total_prompts * 100) if total_prompts > 0 else 0

        return {
            'overall_coverage_percentage': round(overall_coverage, 2),
            'total_prompts': total_prompts,
            'total_translations': total_translations,
            'by_category': coverage_by_category
        }

    def get_detailed_coverage(self) -> Dict:
        """Get detailed coverage analysis"""
        summary = self.get_coverage_summary()

        # Add source type analysis
        source_coverage = db.session.query(
            Prompt.source_type,
            func.count(Prompt.id).label('prompt_count'),
            func.count(Translation.id).label('translation_count'),
            func.avg(Prompt.quality_score).label('avg_quality')
        ).outerjoin(Translation).group_by(Prompt.source_type).all()

        coverage_by_source = {}
        for source, prompt_count, translation_count, avg_quality in source_coverage:
            coverage_percentage = (translation_count / prompt_count * 100) if prompt_count > 0 else 0
            coverage_by_source[source or 'unknown'] = {
                'prompt_count': prompt_count,
                'translation_count': translation_count,
                'coverage_percentage': round(coverage_percentage, 2),
                'average_quality': round(avg_quality or 0, 2)
            }

        # Add difficulty level analysis
        difficulty_coverage = db.session.query(
            Prompt.difficulty_level,
            func.count(Prompt.id).label('prompt_count'),
            func.count(Translation.id).label('translation_count')
        ).outerjoin(Translation).group_by(Prompt.difficulty_level).all()

        coverage_by_difficulty = {}
        for difficulty, prompt_count, translation_count in difficulty_coverage:
            coverage_percentage = (translation_count / prompt_count * 100) if prompt_count > 0 else 0
            coverage_by_difficulty[difficulty or 'unknown'] = {
                'prompt_count': prompt_count,
                'translation_count': translation_count,
                'coverage_percentage': round(coverage_percentage, 2)
            }

        return {
            **summary,
            'by_source': coverage_by_source,
            'by_difficulty': coverage_by_difficulty
        }

    def track_coverage_changes(self, days: int = 7) -> Dict:
        """Track coverage changes over time"""
        start_date = datetime.utcnow() - timedelta(days=days)

        # Get translations in the time period
        recent_translations = db.session.query(
            Prompt.category,
            func.count(Translation.id).label('count')
        ).join(Translation).filter(
            Translation.timestamp >= start_date
        ).group_by(Prompt.category).all()

        changes = {}
        for category, count in recent_translations:
            changes[category or 'unknown'] = count

        return {
            'period_days': days,
            'changes_by_category': changes,
            'total_new_translations': sum(changes.values())
        }

    def identify_coverage_gaps(self) -> Dict:
        """Identify categories with significant coverage gaps"""
        coverage_data = self.get_coverage_summary()

        gaps = {
            'critical_gaps': [],  # <25% coverage
            'moderate_gaps': [],  # 25-50% coverage
            'recommendations': []
        }

        for category, data in coverage_data['by_category'].items():
            coverage_pct = data['coverage_percentage']

            if coverage_pct < 25:
                gaps['critical_gaps'].append({
                    'category': category,
                    'coverage_percentage': coverage_pct,
                    'prompt_count': data['prompt_count'],
                    'translation_count': data['translation_count']
                })
                gaps['recommendations'].append(
                    f"Critical: {category} needs immediate attention ({coverage_pct:.1f}% coverage)"
                )
            elif coverage_pct < 50:
                gaps['moderate_gaps'].append({
                    'category': category,
                    'coverage_percentage': coverage_pct,
                    'prompt_count': data['prompt_count'],
                    'translation_count': data['translation_count']
                })
                gaps['recommendations'].append(
                    f"Moderate: Consider prioritizing {category} ({coverage_pct:.1f}% coverage)"
                )

        return gaps


class UserAnalytics:
    """Analyze user behavior and engagement patterns"""

    def get_engagement_summary(self) -> Dict:
        """Get user engagement summary"""
        total_users = User.query.count()

        # Active users in different periods
        now = datetime.utcnow()
        active_1d = User.query.filter(User.last_activity >= now - timedelta(days=1)).count()
        active_7d = User.query.filter(User.last_activity >= now - timedelta(days=7)).count()
        active_30d = User.query.filter(User.last_activity >= now - timedelta(days=30)).count()

        # Submission statistics
        user_submissions = db.session.query(
            func.count(Translation.id).label('submission_count')
        ).join(User).group_by(User.id).all()

        submission_counts = [count[0] for count in user_submissions]
        avg_submissions = sum(submission_counts) / len(submission_counts) if submission_counts else 0

        # User retention
        week_ago = now - timedelta(days=7)
        month_ago = now - timedelta(days=30)

        new_users_week = User.query.filter(User.created_at >= week_ago).count()
        active_new_users = User.query.filter(
            and_(
                User.created_at >= week_ago,
                User.last_activity >= week_ago
            )
        ).count()

        retention_rate = (active_new_users / new_users_week * 100) if new_users_week > 0 else 0

        return {
            'total_users': total_users,
            'active_1_day': active_1d,
            'active_7_days': active_7d,
            'active_30_days': active_30d,
            'average_submissions_per_user': round(avg_submissions, 2),
            'weekly_retention_rate': round(retention_rate, 2),
            'engagement_rates': {
                '1_day': (active_1d / total_users * 100) if total_users > 0 else 0,
                '7_days': (active_7d / total_users * 100) if total_users > 0 else 0,
                '30_days': (active_30d / total_users * 100) if total_users > 0 else 0
            }
        }

    def get_detailed_analytics(self) -> Dict:
        """Get detailed user analytics"""
        summary = self.get_engagement_summary()

        # User distribution by submission count
        submission_distribution = db.session.query(
            func.count(Translation.id).label('submission_count'),
            func.count(User.id).label('user_count')
        ).join(Translation).group_by(User.id).subquery()

        distribution_query = db.session.query(
            submission_distribution.c.submission_count,
            func.count().label('users_with_count')
        ).group_by(submission_distribution.c.submission_count).all()

        # Create buckets for better visualization
        buckets = defaultdict(int)
        for submission_count, user_count in distribution_query:
            if submission_count == 1:
                buckets['1'] += user_count
            elif submission_count <= 3:
                buckets['2-3'] += user_count
            elif submission_count <= 5:
                buckets['4-5'] += user_count
            elif submission_count <= 10:
                buckets['6-10'] += user_count
            else:
                buckets['10+'] += user_count

        # User growth over time
        user_growth = db.session.query(
            func.date(User.created_at).label('date'),
            func.count(User.id).label('new_users')
        ).filter(
            User.created_at >= datetime.utcnow() - timedelta(days=30)
        ).group_by(
            func.date(User.created_at)
        ).order_by('date').all()

        return {
            **summary,
            'submission_distribution': dict(buckets),
            'user_growth': [
                {'date': date.isoformat(), 'new_users': count}
                for date, count in user_growth
            ]
        }

    def analyze_user_patterns(self) -> Dict:
        """Analyze user behavior patterns"""
        # Time-based patterns
        hourly_activity = db.session.query(
            extract('hour', Translation.timestamp).label('hour'),
            func.count(Translation.id).label('count')
        ).group_by(extract('hour', Translation.timestamp)).all()

        daily_activity = db.session.query(
            extract('dow', Translation.timestamp).label('day_of_week'),
            func.count(Translation.id).label('count')
        ).group_by(extract('dow', Translation.timestamp)).all()

        # Session patterns
        session_lengths = db.session.query(
            User.id,
            func.count(Translation.id).label('session_translations'),
            func.min(Translation.timestamp).label('session_start'),
            func.max(Translation.timestamp).label('session_end')
        ).join(Translation).group_by(User.id).all()

        avg_session_length = 0
        if session_lengths:
            session_durations = []
            for user_id, trans_count, start, end in session_lengths:
                if start and end and trans_count > 1:
                    duration = (end - start).total_seconds() / 60  # minutes
                    session_durations.append(duration)

            avg_session_length = sum(session_durations) / len(session_durations) if session_durations else 0

        return {
            'hourly_activity': [
                {'hour': int(hour), 'count': count}
                for hour, count in hourly_activity
            ],
            'daily_activity': [
                {'day_of_week': int(day), 'count': count}
                for day, count in daily_activity
            ],
            'average_session_length_minutes': round(avg_session_length, 2)
        }


class QualityAnalytics:
    """Analyze quality metrics across the platform"""

    def get_quality_summary(self) -> Dict:
        """Get quality metrics summary"""
        # Overall quality distribution
        total_prompts = Prompt.query.filter_by(status='active').count()
        high_quality = Prompt.query.filter(Prompt.quality_score >= 0.8).count()
        medium_quality = Prompt.query.filter(
            and_(Prompt.quality_score >= 0.6, Prompt.quality_score < 0.8)
        ).count()
        low_quality = Prompt.query.filter(Prompt.quality_score < 0.6).count()

        avg_quality = db.session.query(func.avg(Prompt.quality_score)).scalar() or 0

        # Quality by source
        quality_by_source = db.session.query(
            Prompt.source_type,
            func.avg(Prompt.quality_score).label('avg_quality'),
            func.count(Prompt.id).label('count')
        ).group_by(Prompt.source_type).all()

        return {
            'average_quality': round(avg_quality, 3),
            'total_prompts': total_prompts,
            'quality_distribution': {
                'high_quality': high_quality,
                'medium_quality': medium_quality,
                'low_quality': low_quality,
                'percentages': {
                    'high': (high_quality / total_prompts * 100) if total_prompts > 0 else 0,
                    'medium': (medium_quality / total_prompts * 100) if total_prompts > 0 else 0,
                    'low': (low_quality / total_prompts * 100) if total_prompts > 0 else 0
                }
            },
            'by_source': {
                source: {
                    'average_quality': round(avg_quality, 3),
                    'count': count
                }
                for source, avg_quality, count in quality_by_source
            }
        }

    def get_detailed_analysis(self) -> Dict:
        """Get detailed quality analysis"""
        summary = self.get_quality_summary()

        # Quality trends over time
        quality_trends = db.session.query(
            func.date(Prompt.date_generated).label('date'),
            func.avg(Prompt.quality_score).label('avg_quality'),
            func.count(Prompt.id).label('count')
        ).filter(
            Prompt.date_generated >= datetime.utcnow() - timedelta(days=30)
        ).group_by(
            func.date(Prompt.date_generated)
        ).order_by('date').all()

        # Quality by category
        quality_by_category = db.session.query(
            Prompt.category,
            func.avg(Prompt.quality_score).label('avg_quality'),
            func.count(Prompt.id).label('count')
        ).group_by(Prompt.category).all()

        return {
            **summary,
            'quality_trends': [
                {
                    'date': date.isoformat(),
                    'average_quality': round(avg_quality, 3),
                    'count': count
                }
                for date, avg_quality, count in quality_trends
            ],
            'by_category': {
                category or 'unknown': {
                    'average_quality': round(avg_quality, 3),
                    'count': count
                }
                for category, avg_quality, count in quality_by_category
            }
        }

    def identify_quality_issues(self) -> Dict:
        """Identify quality issues and recommendations"""
        issues = {
            'low_quality_prompts': [],
            'source_issues': [],
            'category_issues': [],
            'recommendations': []
        }

        # Find individual low-quality prompts
        low_quality_prompts = Prompt.query.filter(
            Prompt.quality_score < 0.5
        ).order_by(Prompt.quality_score.asc()).limit(10).all()

        for prompt in low_quality_prompts:
            issues['low_quality_prompts'].append({
                'id': prompt.id,
                'text': prompt.text[:50] + '...',
                'quality_score': prompt.quality_score,
                'source_type': prompt.source_type,
                'category': prompt.category
            })

        # Find problematic sources
        source_quality = db.session.query(
            Prompt.source_type,
            func.avg(Prompt.quality_score).label('avg_quality'),
            func.count(Prompt.id).label('count')
        ).group_by(Prompt.source_type).all()

        for source, avg_quality, count in source_quality:
            if avg_quality < 0.7 and count > 5:
                issues['source_issues'].append({
                    'source': source,
                    'average_quality': round(avg_quality, 3),
                    'count': count
                })
                issues['recommendations'].append(
                    f"Review {source} source quality (avg: {avg_quality:.2f})"
                )

        return issues


class PerformanceAnalytics:
    """Track platform performance metrics"""

    def get_performance_summary(self) -> Dict:
        """Get performance metrics summary"""
        # API usage tracking
        from app.services.openrouter import OpenRouterClient
        openrouter = OpenRouterClient()
        api_stats = openrouter.get_usage_statistics()

        # Database size metrics
        prompt_count = Prompt.query.count()
        translation_count = Translation.query.count()
        user_count = User.query.count()

        # Processing metrics
        processing_stats = self._get_processing_metrics()

        return {
            'api_usage': api_stats,
            'database_size': {
                'prompts': prompt_count,
                'translations': translation_count,
                'users': user_count
            },
            'processing': processing_stats
        }

    def get_detailed_metrics(self) -> Dict:
        """Get detailed performance metrics"""
        summary = self.get_performance_summary()

        # Growth rates
        growth_metrics = self._calculate_growth_rates()

        # System utilization
        utilization_metrics = self._get_utilization_metrics()

        return {
            **summary,
            'growth_rates': growth_metrics,
            'utilization': utilization_metrics
        }

    def _get_processing_metrics(self) -> Dict:
        """Get processing performance metrics"""
        # Average processing times (would be tracked in real implementation)
        return {
            'avg_prompt_generation_time': 2.5,  # seconds
            'avg_translation_save_time': 0.3,   # seconds
            'avg_quality_assessment_time': 0.8  # seconds
        }

    def _calculate_growth_rates(self) -> Dict:
        """Calculate growth rates for key metrics"""
        now = datetime.utcnow()
        week_ago = now - timedelta(days=7)
        month_ago = now - timedelta(days=30)

        # Prompt growth
        prompts_week = Prompt.query.filter(Prompt.date_generated >= week_ago).count()
        prompts_month = Prompt.query.filter(Prompt.date_generated >= month_ago).count()

        # Translation growth
        translations_week = Translation.query.filter(Translation.timestamp >= week_ago).count()
        translations_month = Translation.query.filter(Translation.timestamp >= month_ago).count()

        # User growth
        users_week = User.query.filter(User.created_at >= week_ago).count()
        users_month = User.query.filter(User.created_at >= month_ago).count()

        return {
            'prompts': {
                'weekly': prompts_week,
                'monthly': prompts_month
            },
            'translations': {
                'weekly': translations_week,
                'monthly': translations_month
            },
            'users': {
                'weekly': users_week,
                'monthly': users_month
            }
        }

    def _get_utilization_metrics(self) -> Dict:
        """Get system utilization metrics"""
        # In a real implementation, these would track actual system resources
        return {
            'database_utilization': 45,  # percentage
            'api_utilization': 30,      # percentage of daily limit
            'storage_utilization': 25   # percentage of allocated storage
        }