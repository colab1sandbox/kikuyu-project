"""
Community Submission Service - Handle community-contributed English prompts
Includes submission, validation, review, and approval workflows
"""

import re
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from flask import current_app, request
from sqlalchemy import and_, or_, desc

from app.models import (
    CommunitySubmission, Prompt, User, DomainCoverage,
    AdminAction, db
)


class CommunitySubmissionService:
    """Service for managing community-submitted prompts"""

    def __init__(self):
        self.validator = SubmissionValidator()
        self.reviewer = SubmissionReviewer()
        self.quality_assessor = QualityAssessor()

    def submit_prompt(self, text: str, category: str = None,
                     difficulty: str = 'basic', submitter_info: Dict = None) -> Dict:
        """
        Submit a new prompt from the community

        Args:
            text: English sentence to submit
            category: Optional category classification
            difficulty: Difficulty level (basic, intermediate, advanced)
            submitter_info: Optional submitter information

        Returns:
            Dictionary with submission result
        """
        # Validate the submission
        validation_result = self.validator.validate_submission(text, category, difficulty)
        if not validation_result['valid']:
            return {
                'success': False,
                'error': validation_result['error'],
                'suggestions': validation_result.get('suggestions', [])
            }

        # Check for duplicates
        duplicate_check = self._check_for_duplicates(text)
        if duplicate_check['is_duplicate']:
            return {
                'success': False,
                'error': 'This sentence has already been submitted',
                'duplicate_id': duplicate_check['existing_id']
            }

        # Assess initial quality
        quality_score = self.quality_assessor.assess_submission(text, category)

        # Create submission record
        try:
            submission = CommunitySubmission(
                text=text.strip(),
                category=category or self._auto_categorize(text),
                difficulty_level=difficulty,
                submitted_by=submitter_info.get('user_id') if submitter_info else None,
                submission_ip=submitter_info.get('ip_address') if submitter_info else None,
                quality_score=quality_score
            )

            db.session.add(submission)
            db.session.commit()

            # Update domain coverage tracking
            self._update_submission_stats(submission.category)

            logging.info(f"Community submission received: {submission.id}")

            return {
                'success': True,
                'submission_id': submission.id,
                'message': 'Your submission has been received and will be reviewed',
                'estimated_review_time': '1-3 days',
                'quality_score': quality_score
            }

        except Exception as e:
            db.session.rollback()
            logging.error(f"Error creating community submission: {e}")
            return {
                'success': False,
                'error': 'Failed to save submission. Please try again.'
            }

    def get_pending_submissions(self, limit: int = 50, category: str = None) -> List[Dict]:
        """Get pending submissions for admin review"""
        query = CommunitySubmission.query.filter_by(status='pending')

        if category:
            query = query.filter_by(category=category)

        submissions = query.order_by(
            desc(CommunitySubmission.quality_score),
            CommunitySubmission.submission_timestamp
        ).limit(limit).all()

        return [self._format_submission_for_review(sub) for sub in submissions]

    def review_submission(self, submission_id: int, action: str,
                         admin_id: str, notes: str = None) -> Dict:
        """
        Review a community submission

        Args:
            submission_id: ID of submission to review
            action: 'approve', 'reject', or 'request_changes'
            admin_id: Identifier of reviewing admin
            notes: Optional review notes

        Returns:
            Dictionary with review result
        """
        submission = CommunitySubmission.query.get(submission_id)
        if not submission:
            return {'success': False, 'error': 'Submission not found'}

        if submission.status != 'pending':
            return {'success': False, 'error': 'Submission already reviewed'}

        try:
            if action == 'approve':
                return self._approve_submission(submission, admin_id, notes)
            elif action == 'reject':
                return self._reject_submission(submission, admin_id, notes)
            elif action == 'request_changes':
                return self._request_changes(submission, admin_id, notes)
            else:
                return {'success': False, 'error': 'Invalid action'}

        except Exception as e:
            db.session.rollback()
            logging.error(f"Error reviewing submission {submission_id}: {e}")
            return {'success': False, 'error': 'Review failed. Please try again.'}

    def _approve_submission(self, submission: CommunitySubmission,
                           admin_id: str, notes: str = None) -> Dict:
        """Approve a submission and convert to prompt"""
        # Create prompt from submission
        prompt = submission.approve(admin_id, notes)

        # Update domain coverage
        self._update_domain_coverage(submission.category, 'approved')

        db.session.commit()

        logging.info(f"Community submission {submission.id} approved, created prompt {prompt.id}")

        return {
            'success': True,
            'message': 'Submission approved and added to prompt pool',
            'prompt_id': prompt.id
        }

    def _reject_submission(self, submission: CommunitySubmission,
                          admin_id: str, notes: str = None) -> Dict:
        """Reject a submission"""
        submission.status = 'rejected'
        submission.reviewed_by = admin_id
        submission.review_timestamp = datetime.utcnow()
        submission.review_notes = notes

        db.session.commit()

        return {
            'success': True,
            'message': 'Submission rejected',
            'reason': notes
        }

    def _request_changes(self, submission: CommunitySubmission,
                        admin_id: str, notes: str = None) -> Dict:
        """Request changes to a submission"""
        submission.status = 'changes_requested'
        submission.reviewed_by = admin_id
        submission.review_timestamp = datetime.utcnow()
        submission.review_notes = notes

        db.session.commit()

        return {
            'success': True,
            'message': 'Changes requested',
            'requested_changes': notes
        }

    def get_submission_stats(self) -> Dict:
        """Get statistics about community submissions"""
        total_submissions = CommunitySubmission.query.count()
        pending = CommunitySubmission.query.filter_by(status='pending').count()
        approved = CommunitySubmission.query.filter_by(status='approved').count()
        rejected = CommunitySubmission.query.filter_by(status='rejected').count()

        # Category breakdown
        category_stats = db.session.query(
            CommunitySubmission.category,
            db.func.count(CommunitySubmission.id).label('count'),
            db.func.avg(CommunitySubmission.quality_score).label('avg_quality')
        ).group_by(CommunitySubmission.category).all()

        # Recent submission trend
        week_ago = datetime.utcnow() - timedelta(days=7)
        recent_submissions = CommunitySubmission.query.filter(
            CommunitySubmission.submission_timestamp >= week_ago
        ).count()

        return {
            'total_submissions': total_submissions,
            'pending_review': pending,
            'approved': approved,
            'rejected': rejected,
            'approval_rate': (approved / total_submissions * 100) if total_submissions > 0 else 0,
            'recent_submissions_week': recent_submissions,
            'category_breakdown': {
                category: {'count': count, 'avg_quality': float(avg_quality or 0)}
                for category, count, avg_quality in category_stats
            }
        }

    def _check_for_duplicates(self, text: str) -> Dict:
        """Check if submission is a duplicate"""
        text_normalized = text.strip().lower()

        # Check in existing submissions
        existing_submission = CommunitySubmission.query.filter(
            db.func.lower(CommunitySubmission.text) == text_normalized
        ).first()

        if existing_submission:
            return {
                'is_duplicate': True,
                'existing_id': existing_submission.id,
                'existing_status': existing_submission.status
            }

        # Check in existing prompts
        existing_prompt = Prompt.query.filter(
            db.func.lower(Prompt.text) == text_normalized
        ).first()

        if existing_prompt:
            return {
                'is_duplicate': True,
                'existing_id': existing_prompt.id,
                'existing_status': 'already_in_use'
            }

        return {'is_duplicate': False}

    def _auto_categorize(self, text: str) -> str:
        """Automatically categorize submission based on content"""
        text_lower = text.lower()

        categories = {
            'greetings': ['hello', 'hi', 'good morning', 'good evening', 'goodbye', 'bye'],
            'family': ['mother', 'father', 'child', 'family', 'parent', 'sister', 'brother', 'home'],
            'agriculture': ['farm', 'crop', 'plant', 'harvest', 'field', 'livestock', 'farming', 'grow'],
            'health': ['health', 'medicine', 'doctor', 'hospital', 'sick', 'treatment', 'medicine'],
            'education': ['school', 'learn', 'teach', 'student', 'book', 'study', 'education'],
            'weather': ['weather', 'rain', 'sun', 'hot', 'cold', 'wind', 'season', 'climate'],
            'technology': ['computer', 'phone', 'internet', 'technology', 'digital', 'online'],
            'business': ['business', 'work', 'job', 'trade', 'money', 'market', 'sell', 'buy']
        }

        for category, keywords in categories.items():
            if any(keyword in text_lower for keyword in keywords):
                return category

        return 'general'

    def _update_submission_stats(self, category: str):
        """Update submission statistics"""
        # This would update tracking tables
        pass

    def _update_domain_coverage(self, category: str, action: str):
        """Update domain coverage when submission is approved"""
        coverage = DomainCoverage.query.filter_by(category=category).first()
        if not coverage:
            coverage = DomainCoverage(category=category, current_count=0, target_count=1000)
            db.session.add(coverage)

        if action == 'approved':
            coverage.approved_count += 1
            coverage.current_count += 1
            coverage.update_coverage()

    def _format_submission_for_review(self, submission: CommunitySubmission) -> Dict:
        """Format submission for admin review interface"""
        return {
            'id': submission.id,
            'text': submission.text,
            'category': submission.category,
            'difficulty_level': submission.difficulty_level,
            'quality_score': submission.quality_score,
            'submission_timestamp': submission.submission_timestamp.isoformat(),
            'submitted_by': submission.submitted_by,
            'submission_ip': submission.submission_ip,
            'validation_info': self.validator.get_detailed_validation(submission.text)
        }


class SubmissionValidator:
    """Validates community submissions for quality and appropriateness"""

    def __init__(self):
        self.min_length = 3
        self.max_length = 30
        self.min_chars = 10
        self.max_chars = 200

    def validate_submission(self, text: str, category: str = None,
                          difficulty: str = 'basic') -> Dict:
        """Comprehensive validation of a submission"""
        validation_result = {
            'valid': True,
            'error': None,
            'warnings': [],
            'suggestions': []
        }

        # Basic text validation
        if not text or not text.strip():
            validation_result['valid'] = False
            validation_result['error'] = 'Text cannot be empty'
            return validation_result

        text = text.strip()

        # Length validation
        words = text.split()
        if len(words) < self.min_length:
            validation_result['valid'] = False
            validation_result['error'] = f'Sentence too short. Minimum {self.min_length} words required'
            return validation_result

        if len(words) > self.max_length:
            validation_result['valid'] = False
            validation_result['error'] = f'Sentence too long. Maximum {self.max_length} words allowed'
            return validation_result

        if len(text) < self.min_chars:
            validation_result['valid'] = False
            validation_result['error'] = f'Text too short. Minimum {self.min_chars} characters required'
            return validation_result

        if len(text) > self.max_chars:
            validation_result['valid'] = False
            validation_result['error'] = f'Text too long. Maximum {self.max_chars} characters allowed'
            return validation_result

        # Character validation
        if not re.match(r'^[A-Za-z0-9\s\.,\?!\'"-]+$', text):
            validation_result['valid'] = False
            validation_result['error'] = 'Text contains invalid characters. Only letters, numbers, and basic punctuation allowed'
            return validation_result

        # Content quality checks
        quality_issues = self._check_content_quality(text)
        if quality_issues['has_issues']:
            validation_result['valid'] = False
            validation_result['error'] = quality_issues['primary_issue']
            validation_result['suggestions'] = quality_issues['suggestions']
            return validation_result

        # Language check
        if not self._is_likely_english(text):
            validation_result['valid'] = False
            validation_result['error'] = 'Text does not appear to be in English'
            return validation_result

        # Grammar and structure checks
        structure_warnings = self._check_structure(text)
        validation_result['warnings'].extend(structure_warnings)

        # Category validation
        if category and not self._is_valid_category(category):
            validation_result['warnings'].append(f'Category "{category}" is not recognized')

        return validation_result

    def _check_content_quality(self, text: str) -> Dict:
        """Check content quality issues"""
        issues = {
            'has_issues': False,
            'primary_issue': None,
            'suggestions': []
        }

        text_lower = text.lower()

        # Check for inappropriate content
        inappropriate_words = ['damn', 'hell', 'stupid', 'idiot', 'hate']
        if any(word in text_lower for word in inappropriate_words):
            issues['has_issues'] = True
            issues['primary_issue'] = 'Text contains inappropriate language'
            issues['suggestions'].append('Please use respectful, family-friendly language')

        # Check for repetitive words
        words = text_lower.split()
        word_count = {}
        for word in words:
            word_count[word] = word_count.get(word, 0) + 1

        max_repetition = max(word_count.values()) if word_count else 0
        if max_repetition > len(words) * 0.4:  # More than 40% repetition
            issues['has_issues'] = True
            issues['primary_issue'] = 'Text has too much repetition'
            issues['suggestions'].append('Try to use more varied vocabulary')

        # Check for all caps
        if text.isupper() and len(text) > 10:
            issues['suggestions'].append('Consider using normal capitalization instead of all caps')

        # Check for question marks or complex punctuation
        if text.count('?') > 2 or text.count('!') > 2:
            issues['suggestions'].append('Consider simplifying punctuation for better translation')

        return issues

    def _is_likely_english(self, text: str) -> bool:
        """Basic check if text is likely English"""
        # Simple heuristic - check for common English words
        common_english = [
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with',
            'by', 'is', 'are', 'was', 'were', 'have', 'has', 'had', 'will', 'would', 'could',
            'should', 'can', 'may', 'might', 'this', 'that', 'these', 'those', 'i', 'you',
            'he', 'she', 'it', 'we', 'they', 'me', 'him', 'her', 'us', 'them'
        ]

        words = text.lower().split()
        english_word_count = sum(1 for word in words if word.strip('.,!?') in common_english)

        # If at least 20% of words are common English words, consider it English
        return len(words) == 0 or (english_word_count / len(words)) >= 0.2

    def _check_structure(self, text: str) -> List[str]:
        """Check sentence structure and provide warnings"""
        warnings = []

        # Check capitalization
        if not text[0].isupper():
            warnings.append('Consider starting the sentence with a capital letter')

        # Check ending punctuation
        if not text[-1] in '.!?':
            warnings.append('Consider ending the sentence with proper punctuation')

        # Check for very long words (might be errors)
        words = text.split()
        long_words = [word for word in words if len(word) > 15]
        if long_words:
            warnings.append(f'Very long words detected: {", ".join(long_words)}. Please verify spelling')

        return warnings

    def _is_valid_category(self, category: str) -> bool:
        """Check if category is valid"""
        valid_categories = [
            'greetings', 'family', 'agriculture', 'health', 'education',
            'weather', 'technology', 'business', 'culture', 'general',
            'conversation', 'news', 'science', 'history', 'geography'
        ]
        return category.lower() in valid_categories

    def get_detailed_validation(self, text: str) -> Dict:
        """Get detailed validation information for admin review"""
        words = text.split()

        return {
            'word_count': len(words),
            'character_count': len(text),
            'has_punctuation': any(char in text for char in '.,!?'),
            'capitalization_correct': text[0].isupper() if text else False,
            'estimated_difficulty': self._estimate_difficulty(text),
            'suggested_category': self._suggest_category(text),
            'quality_indicators': self._get_quality_indicators(text)
        }

    def _estimate_difficulty(self, text: str) -> str:
        """Estimate difficulty level of text"""
        words = text.split()
        avg_word_length = sum(len(word.strip('.,!?')) for word in words) / len(words) if words else 0
        complex_words = sum(1 for word in words if len(word.strip('.,!?')) > 8)

        if len(words) <= 8 and avg_word_length <= 5 and complex_words == 0:
            return 'basic'
        elif len(words) <= 15 and avg_word_length <= 7 and complex_words <= 2:
            return 'intermediate'
        else:
            return 'advanced'

    def _suggest_category(self, text: str) -> str:
        """Suggest most appropriate category"""
        # Reuse the auto-categorization logic
        from app.services.community_service import CommunitySubmissionService
        service = CommunitySubmissionService()
        return service._auto_categorize(text)

    def _get_quality_indicators(self, text: str) -> Dict:
        """Get quality indicators for the text"""
        words = text.split()
        unique_words = set(word.lower().strip('.,!?') for word in words)

        return {
            'vocabulary_diversity': len(unique_words) / len(words) if words else 0,
            'sentence_complexity': 'simple' if len(words) <= 10 else 'complex',
            'punctuation_appropriate': text[-1] in '.!?' if text else False,
            'length_appropriate': 5 <= len(words) <= 20
        }


class SubmissionReviewer:
    """Handles submission review workflow"""

    def get_review_priority_score(self, submission: CommunitySubmission) -> float:
        """Calculate priority score for review ordering"""
        score = submission.quality_score or 0.5

        # Bonus for high-need categories
        category_priorities = {
            'agriculture': 0.2,
            'health': 0.2,
            'education': 0.15,
            'culture': 0.15,
            'technology': 0.1
        }
        score += category_priorities.get(submission.category, 0)

        # Time factor (older submissions get priority)
        days_old = (datetime.utcnow() - submission.submission_timestamp).days
        score += min(days_old * 0.01, 0.1)

        return min(score, 1.0)


class QualityAssessor:
    """Assesses quality of community submissions"""

    def assess_submission(self, text: str, category: str = None) -> float:
        """Assess quality score for a submission"""
        score = 0.7  # Base score

        words = text.split()

        # Length appropriateness
        if 5 <= len(words) <= 15:
            score += 0.1
        elif 3 <= len(words) <= 20:
            score += 0.05

        # Vocabulary diversity
        unique_words = set(word.lower().strip('.,!?') for word in words)
        diversity = len(unique_words) / len(words) if words else 0
        score += diversity * 0.1

        # Grammar indicators
        if text[0].isupper() and text[-1] in '.!?':
            score += 0.05

        # Category relevance
        if category and self._has_category_relevance(text, category):
            score += 0.1

        return min(max(score, 0.1), 1.0)

    def _has_category_relevance(self, text: str, category: str) -> bool:
        """Check if text is relevant to category"""
        category_keywords = {
            'agriculture': ['farm', 'crop', 'plant', 'harvest', 'livestock', 'field'],
            'health': ['health', 'medicine', 'doctor', 'hospital', 'treatment'],
            'education': ['school', 'learn', 'teach', 'student', 'book', 'study'],
            'family': ['family', 'mother', 'father', 'child', 'home', 'parent'],
            'technology': ['computer', 'phone', 'internet', 'technology', 'digital']
        }

        keywords = category_keywords.get(category, [])
        text_lower = text.lower()
        return any(keyword in text_lower for keyword in keywords)