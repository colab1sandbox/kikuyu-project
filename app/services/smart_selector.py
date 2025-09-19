"""
Smart Prompt Selector - Intelligent prompt selection based on coverage analysis
Balances user progress, domain coverage gaps, and quality distribution
"""

import json
import random
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from sqlalchemy import func, and_, or_
from flask import current_app

from app.models import (
    Prompt, User, Translation, DomainCoverage,
    UserProgress, CorpusStatistics
)
from app import db


class SmartPromptSelector:
    """Intelligent prompt selection system for hybrid corpus"""

    def __init__(self):
        self.coverage_analyzer = CoverageAnalyzer()
        self.gap_detector = GapDetector()
        self.quality_balancer = QualityBalancer()

    def select_next_prompt(self, user_id: int, preferred_category: str = None) -> Optional[Dict]:
        """
        Select the next optimal prompt for a user

        Args:
            user_id: User identifier
            preferred_category: Optional category preference

        Returns:
            Dictionary containing prompt data and selection metadata
        """
        user = User.query.get(user_id)
        if not user:
            return None

        # Analyze current state
        coverage_gaps = self.coverage_analyzer.analyze_gaps()
        user_progress = self.get_user_progress(user_id)
        system_priorities = self.gap_detector.detect_critical_gaps()

        # Determine selection strategy
        selection_strategy = self.determine_strategy(
            coverage_gaps, user_progress, system_priorities, preferred_category
        )

        # Select prompt based on strategy
        prompt = self.execute_selection_strategy(user_id, selection_strategy)

        if prompt:
            # Record selection and update user progress
            self.record_prompt_selection(user_id, prompt.id, selection_strategy)
            return self.format_prompt_response(prompt, selection_strategy)

        return None

    def determine_strategy(self, coverage_gaps: Dict, user_progress: Dict,
                          system_priorities: Dict, preferred_category: str = None) -> Dict:
        """Determine the optimal selection strategy"""

        strategy = {
            'type': 'balanced',
            'priority_categories': [],
            'source_preference': None,
            'difficulty_target': 'basic',
            'weight_distribution': {
                'coverage_gaps': 0.4,
                'user_progress': 0.3,
                'quality_balance': 0.2,
                'randomness': 0.1
            }
        }

        # Critical gap strategy
        if system_priorities.get('critical_gaps'):
            strategy['type'] = 'critical_gap_filling'
            strategy['priority_categories'] = system_priorities['critical_gaps']
            strategy['weight_distribution']['coverage_gaps'] = 0.7
            strategy['weight_distribution']['user_progress'] = 0.2

        # User preference strategy
        elif preferred_category and preferred_category in coverage_gaps:
            strategy['type'] = 'user_preference'
            strategy['priority_categories'] = [preferred_category]
            strategy['weight_distribution']['user_progress'] = 0.5

        # New user onboarding strategy
        elif user_progress.get('total_completed', 0) < 5:
            strategy['type'] = 'onboarding'
            strategy['difficulty_target'] = 'basic'
            strategy['priority_categories'] = ['greetings', 'conversation', 'family']
            strategy['source_preference'] = 'corpus'  # High quality for beginners

        # Balanced exploration strategy
        else:
            underrepresented = coverage_gaps.get('underrepresented_categories', [])
            if underrepresented:
                strategy['priority_categories'] = underrepresented[:3]

        return strategy

    def execute_selection_strategy(self, user_id: int, strategy: Dict) -> Optional[Prompt]:
        """Execute the selection strategy and return a prompt"""

        # Get user's completed prompts to avoid repetition
        completed_prompt_ids = self.get_completed_prompt_ids(user_id)

        # Base query - exclude completed prompts
        base_query = Prompt.query.filter(
            and_(
                Prompt.status == 'active',
                ~Prompt.id.in_(completed_prompt_ids) if completed_prompt_ids else True
            )
        )

        # Apply strategy filters
        if strategy['type'] == 'critical_gap_filling':
            return self.select_for_critical_gaps(base_query, strategy)

        elif strategy['type'] == 'user_preference':
            return self.select_for_user_preference(base_query, strategy)

        elif strategy['type'] == 'onboarding':
            return self.select_for_onboarding(base_query, strategy)

        else:  # balanced
            return self.select_balanced(base_query, strategy)

    def select_for_critical_gaps(self, base_query, strategy: Dict) -> Optional[Prompt]:
        """Select prompt to fill critical coverage gaps"""
        priority_categories = strategy['priority_categories']

        # Prioritize high-quality sources for critical gaps
        prompt = base_query.filter(
            and_(
                Prompt.category.in_(priority_categories),
                Prompt.quality_score >= 0.8,
                or_(
                    Prompt.source_type == 'corpus',
                    Prompt.source_type == 'community'
                )
            )
        ).order_by(
            func.random()
        ).first()

        # Fallback to any prompt in priority categories
        if not prompt:
            prompt = base_query.filter(
                Prompt.category.in_(priority_categories)
            ).order_by(
                Prompt.quality_score.desc(),
                func.random()
            ).first()

        return prompt

    def select_for_user_preference(self, base_query, strategy: Dict) -> Optional[Prompt]:
        """Select prompt based on user preference"""
        preferred_category = strategy['priority_categories'][0]

        # Get prompts in preferred category, ordered by quality and difficulty progression
        prompt = base_query.filter(
            Prompt.category == preferred_category
        ).order_by(
            Prompt.difficulty_level.asc(),  # Progress from basic to advanced
            Prompt.quality_score.desc(),
            func.random()
        ).first()

        return prompt

    def select_for_onboarding(self, base_query, strategy: Dict) -> Optional[Prompt]:
        """Select beginner-friendly prompts for new users"""
        onboarding_categories = strategy['priority_categories']

        prompt = base_query.filter(
            and_(
                Prompt.category.in_(onboarding_categories),
                Prompt.difficulty_level == 'basic',
                Prompt.quality_score >= 0.85,
                Prompt.source_type.in_(['corpus', 'conversation'])  # High-quality sources
            )
        ).order_by(
            func.random()
        ).first()

        return prompt

    def select_balanced(self, base_query, strategy: Dict) -> Optional[Prompt]:
        """Select prompt using balanced approach"""
        weights = strategy['weight_distribution']

        # Get scoring candidates
        candidates = base_query.filter(
            Prompt.quality_score >= 0.7  # Minimum quality threshold
        ).all()

        if not candidates:
            return base_query.first()  # Fallback

        # Score each candidate
        scored_candidates = []
        for prompt in candidates:
            score = self.calculate_candidate_score(prompt, strategy, weights)
            scored_candidates.append((prompt, score))

        # Sort by score and add some randomness
        scored_candidates.sort(key=lambda x: x[1], reverse=True)

        # Select from top 20% with weighted randomness
        top_candidates = scored_candidates[:max(1, len(scored_candidates) // 5)]

        # Weighted random selection from top candidates
        total_weight = sum(score for _, score in top_candidates)
        if total_weight == 0:
            return random.choice(top_candidates)[0]

        rand_val = random.uniform(0, total_weight)
        cumulative = 0

        for prompt, score in top_candidates:
            cumulative += score
            if cumulative >= rand_val:
                return prompt

        return top_candidates[0][0]  # Fallback

    def calculate_candidate_score(self, prompt: Prompt, strategy: Dict, weights: Dict) -> float:
        """Calculate selection score for a candidate prompt"""
        score = 0.0

        # Coverage gap score
        coverage_score = self.coverage_analyzer.get_category_priority_score(prompt.category)
        score += weights['coverage_gaps'] * coverage_score

        # Quality score
        quality_score = prompt.quality_score or 0.8
        score += weights['quality_balance'] * quality_score

        # Diversity bonus (prefer less used prompts)
        usage_penalty = min(prompt.usage_count * 0.1, 0.5)
        score += weights['randomness'] * (1.0 - usage_penalty)

        # Source type preferences
        source_bonus = 0.0
        if strategy.get('source_preference') == prompt.source_type:
            source_bonus = 0.2
        elif prompt.source_type == 'corpus':
            source_bonus = 0.1  # Slight preference for corpus

        score += source_bonus

        return max(0.0, score)

    def get_user_progress(self, user_id: int) -> Dict:
        """Get comprehensive user progress information"""
        user = User.query.get(user_id)
        if not user:
            return {}

        # Overall progress
        total_completed = Translation.query.filter_by(user_id=user_id).count()

        # Category-wise progress
        category_progress = db.session.query(
            Prompt.category,
            func.count(Translation.id).label('completed')
        ).join(
            Translation, Prompt.id == Translation.prompt_id
        ).filter(
            Translation.user_id == user_id
        ).group_by(
            Prompt.category
        ).all()

        category_counts = {cat: count for cat, count in category_progress}

        # Recent activity
        recent_activity = Translation.query.filter(
            and_(
                Translation.user_id == user_id,
                Translation.timestamp >= datetime.utcnow() - timedelta(days=7)
            )
        ).count()

        return {
            'total_completed': total_completed,
            'category_progress': category_counts,
            'recent_activity': recent_activity,
            'user_since': user.created_at,
            'last_activity': user.last_activity
        }

    def get_completed_prompt_ids(self, user_id: int) -> List[int]:
        """Get list of prompt IDs already completed by user"""
        completed = db.session.query(Translation.prompt_id).filter_by(
            user_id=user_id
        ).distinct().all()

        return [prompt_id for prompt_id, in completed]

    def record_prompt_selection(self, user_id: int, prompt_id: int, strategy: Dict):
        """Record prompt selection for analytics"""
        # Update prompt usage count
        prompt = Prompt.query.get(prompt_id)
        if prompt:
            prompt.usage_count += 1

        # Update user progress
        user = User.query.get(user_id)
        if user:
            user.last_activity = datetime.utcnow()

        try:
            db.session.commit()
        except Exception as e:
            current_app.logger.error(f"Error recording prompt selection: {e}")
            db.session.rollback()

    def format_prompt_response(self, prompt: Prompt, strategy: Dict) -> Dict:
        """Format prompt for API response"""
        return {
            'id': prompt.id,
            'text': prompt.text,
            'category': prompt.category,
            'difficulty_level': prompt.difficulty_level,
            'source_type': prompt.source_type,
            'quality_score': prompt.quality_score,
            'selection_strategy': strategy['type'],
            'metadata': {
                'usage_count': prompt.usage_count,
                'keywords': json.loads(prompt.keywords) if prompt.keywords else [],
                'selection_timestamp': datetime.utcnow().isoformat()
            }
        }


class CoverageAnalyzer:
    """Analyzes translation coverage gaps across domains"""

    def analyze_gaps(self) -> Dict:
        """Analyze current coverage gaps"""
        # Get domain coverage stats
        domain_stats = DomainCoverage.query.all()

        # Calculate overall statistics
        total_translations = Translation.query.filter_by(status='approved').count()

        # Identify gaps
        gaps = {
            'total_translations': total_translations,
            'domain_coverage': {},
            'underrepresented_categories': [],
            'quality_gaps': [],
            'source_imbalance': {}
        }

        # Domain analysis
        for domain in domain_stats:
            gaps['domain_coverage'][domain.category] = {
                'current': domain.current_count,
                'target': domain.target_count,
                'completion': domain.completion_percentage,
                'avg_quality': domain.avg_quality_score
            }

            # Identify underrepresented categories
            if domain.completion_percentage < 50:
                gaps['underrepresented_categories'].append(domain.category)

        # Source distribution analysis
        source_counts = db.session.query(
            Prompt.source_type,
            func.count(Prompt.id).label('count')
        ).group_by(Prompt.source_type).all()

        for source, count in source_counts:
            gaps['source_imbalance'][source] = count

        return gaps

    def get_category_priority_score(self, category: str) -> float:
        """Get priority score for a category (higher = more needed)"""
        domain_coverage = DomainCoverage.query.filter_by(category=category).first()

        if not domain_coverage:
            return 0.8  # Default high priority for uncovered categories

        # Inverse of completion percentage (more gaps = higher priority)
        completion = domain_coverage.completion_percentage or 0
        priority_score = max(0.1, (100 - completion) / 100)

        return priority_score


class GapDetector:
    """Detects critical gaps in the translation corpus"""

    def detect_critical_gaps(self) -> Dict:
        """Detect critical gaps requiring immediate attention"""
        gaps = {
            'critical_gaps': [],
            'quality_issues': [],
            'source_imbalances': [],
            'user_engagement_drops': []
        }

        # Critical coverage gaps (< 25% completion)
        critical_domains = DomainCoverage.query.filter(
            DomainCoverage.completion_percentage < 25
        ).all()

        gaps['critical_gaps'] = [domain.category for domain in critical_domains]

        # Quality issues (< 0.7 average quality)
        quality_issues = DomainCoverage.query.filter(
            DomainCoverage.avg_quality_score < 0.7
        ).all()

        gaps['quality_issues'] = [domain.category for domain in quality_issues]

        # Source imbalances
        source_distribution = self.analyze_source_distribution()
        if source_distribution.get('corpus_percentage', 0) < 50:
            gaps['source_imbalances'].append('insufficient_corpus_coverage')

        return gaps

    def analyze_source_distribution(self) -> Dict:
        """Analyze distribution of prompt sources"""
        total_prompts = Prompt.query.count()
        if total_prompts == 0:
            return {}

        source_counts = db.session.query(
            Prompt.source_type,
            func.count(Prompt.id).label('count')
        ).group_by(Prompt.source_type).all()

        distribution = {}
        for source, count in source_counts:
            distribution[f'{source}_count'] = count
            distribution[f'{source}_percentage'] = (count / total_prompts) * 100

        return distribution


class QualityBalancer:
    """Balances quality across different sources and categories"""

    def get_quality_metrics(self) -> Dict:
        """Get comprehensive quality metrics"""
        # Overall quality distribution
        overall_avg = db.session.query(func.avg(Prompt.quality_score)).scalar() or 0

        # Quality by source
        source_quality = db.session.query(
            Prompt.source_type,
            func.avg(Prompt.quality_score).label('avg_quality'),
            func.count(Prompt.id).label('count')
        ).group_by(Prompt.source_type).all()

        # Quality by category
        category_quality = db.session.query(
            Prompt.category,
            func.avg(Prompt.quality_score).label('avg_quality'),
            func.count(Prompt.id).label('count')
        ).group_by(Prompt.category).all()

        return {
            'overall_average': overall_avg,
            'by_source': {source: {'avg': avg, 'count': count}
                         for source, avg, count in source_quality},
            'by_category': {category: {'avg': avg, 'count': count}
                           for category, avg, count in category_quality}
        }

    def recommend_quality_improvements(self) -> Dict:
        """Recommend actions to improve quality balance"""
        metrics = self.get_quality_metrics()
        recommendations = []

        # Check for low-quality sources
        for source, data in metrics['by_source'].items():
            if data['avg'] < 0.7:
                recommendations.append({
                    'type': 'improve_source_quality',
                    'source': source,
                    'current_quality': data['avg'],
                    'action': 'Review and improve extraction/generation for this source'
                })

        # Check for low-quality categories
        for category, data in metrics['by_category'].items():
            if data['avg'] < 0.7:
                recommendations.append({
                    'type': 'improve_category_quality',
                    'category': category,
                    'current_quality': data['avg'],
                    'action': 'Focus on higher-quality sources for this category'
                })

        return {
            'recommendations': recommendations,
            'priority_actions': len([r for r in recommendations if 'improve' in r['type']])
        }