"""
Quality Control and Validation Pipeline
Comprehensive system for maintaining data quality across all prompt sources
"""

import re
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Set
from collections import Counter
from sqlalchemy import and_, or_, func, desc

from app.models import (
    Prompt, Translation, CommunitySubmission, DomainCoverage,
    CorpusStatistics, AdminAction, db
)
from app import db


class QualityControlPipeline:
    """Main quality control orchestrator"""

    def __init__(self):
        self.prompt_validator = PromptValidator()
        self.translation_validator = TranslationValidator()
        self.duplicate_detector = DuplicateDetector()
        self.quality_scorer = QualityScorer()
        self.batch_processor = BatchProcessor()

    def run_full_quality_audit(self) -> Dict:
        """Run comprehensive quality audit on entire corpus"""
        audit_results = {
            'timestamp': datetime.utcnow().isoformat(),
            'prompt_audit': {},
            'translation_audit': {},
            'duplicate_analysis': {},
            'quality_distribution': {},
            'recommendations': []
        }

        # Audit prompts
        print("Auditing prompts...")
        audit_results['prompt_audit'] = self.audit_prompts()

        # Audit translations
        print("Auditing translations...")
        audit_results['translation_audit'] = self.audit_translations()

        # Detect duplicates
        print("Detecting duplicates...")
        audit_results['duplicate_analysis'] = self.duplicate_detector.find_all_duplicates()

        # Analyze quality distribution
        print("Analyzing quality distribution...")
        audit_results['quality_distribution'] = self.quality_scorer.analyze_distribution()

        # Generate recommendations
        audit_results['recommendations'] = self.generate_recommendations(audit_results)

        # Update corpus statistics
        self.update_corpus_statistics(audit_results)

        return audit_results

    def audit_prompts(self) -> Dict:
        """Audit all prompts for quality issues"""
        prompts = Prompt.query.filter_by(status='active').all()
        audit_results = {
            'total_prompts': len(prompts),
            'valid_prompts': 0,
            'invalid_prompts': 0,
            'warnings': 0,
            'issues_by_category': {},
            'issues_by_source': {},
            'detailed_issues': []
        }

        for prompt in prompts:
            validation_result = self.prompt_validator.validate_prompt(prompt)

            if validation_result['valid']:
                audit_results['valid_prompts'] += 1
            else:
                audit_results['invalid_prompts'] += 1
                audit_results['detailed_issues'].append({
                    'prompt_id': prompt.id,
                    'text': prompt.text[:50] + '...',
                    'category': prompt.category,
                    'source_type': prompt.source_type,
                    'issues': validation_result['issues']
                })

            audit_results['warnings'] += len(validation_result.get('warnings', []))

            # Group issues by category and source
            category = prompt.category or 'unknown'
            source = prompt.source_type or 'unknown'

            if not validation_result['valid']:
                audit_results['issues_by_category'][category] = \
                    audit_results['issues_by_category'].get(category, 0) + 1
                audit_results['issues_by_source'][source] = \
                    audit_results['issues_by_source'].get(source, 0) + 1

        return audit_results

    def audit_translations(self) -> Dict:
        """Audit translations for quality issues"""
        translations = Translation.query.filter(
            Translation.status.in_(['pending', 'approved'])
        ).all()

        audit_results = {
            'total_translations': len(translations),
            'valid_translations': 0,
            'invalid_translations': 0,
            'suspicious_translations': 0,
            'issues_by_category': {},
            'detailed_issues': []
        }

        for translation in translations:
            validation_result = self.translation_validator.validate_translation(translation)

            if validation_result['valid']:
                audit_results['valid_translations'] += 1
            else:
                audit_results['invalid_translations'] += 1

            if validation_result.get('suspicious', False):
                audit_results['suspicious_translations'] += 1

            if not validation_result['valid'] or validation_result.get('suspicious'):
                audit_results['detailed_issues'].append({
                    'translation_id': translation.id,
                    'prompt_text': translation.prompt.text[:30] + '...',
                    'kikuyu_text': translation.kikuyu_text[:30] + '...',
                    'issues': validation_result.get('issues', []),
                    'suspicious_reasons': validation_result.get('suspicious_reasons', [])
                })

            # Group by category
            category = translation.prompt.category or 'unknown'
            if not validation_result['valid']:
                audit_results['issues_by_category'][category] = \
                    audit_results['issues_by_category'].get(category, 0) + 1

        return audit_results

    def process_new_prompts(self, prompt_ids: List[int]) -> Dict:
        """Process and validate newly added prompts"""
        results = {
            'processed': 0,
            'valid': 0,
            'invalid': 0,
            'flagged_for_review': []
        }

        for prompt_id in prompt_ids:
            prompt = Prompt.query.get(prompt_id)
            if not prompt:
                continue

            validation_result = self.prompt_validator.validate_prompt(prompt)
            results['processed'] += 1

            if validation_result['valid']:
                results['valid'] += 1
                # Update quality score if needed
                if validation_result.get('calculated_quality'):
                    prompt.quality_score = validation_result['calculated_quality']
            else:
                results['invalid'] += 1
                # Flag for admin review
                prompt.status = 'flagged'
                results['flagged_for_review'].append({
                    'prompt_id': prompt.id,
                    'issues': validation_result['issues']
                })

        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logging.error(f"Error processing new prompts: {e}")

        return results

    def generate_recommendations(self, audit_results: Dict) -> List[Dict]:
        """Generate actionable recommendations based on audit results"""
        recommendations = []

        # Prompt quality recommendations
        prompt_audit = audit_results.get('prompt_audit', {})
        if prompt_audit.get('invalid_prompts', 0) > 0:
            invalid_ratio = prompt_audit['invalid_prompts'] / prompt_audit['total_prompts']
            if invalid_ratio > 0.1:  # More than 10% invalid
                recommendations.append({
                    'type': 'critical',
                    'area': 'prompt_quality',
                    'issue': f"{prompt_audit['invalid_prompts']} invalid prompts detected",
                    'action': 'Review and clean invalid prompts immediately',
                    'priority': 'high'
                })

        # Source quality recommendations
        issues_by_source = prompt_audit.get('issues_by_source', {})
        for source, issue_count in issues_by_source.items():
            if issue_count > 10:  # Arbitrary threshold
                recommendations.append({
                    'type': 'warning',
                    'area': 'source_quality',
                    'issue': f"Source '{source}' has {issue_count} quality issues",
                    'action': f'Review {source} extraction/generation process',
                    'priority': 'medium'
                })

        # Duplicate recommendations
        duplicates = audit_results.get('duplicate_analysis', {})
        if duplicates.get('total_duplicates', 0) > 0:
            recommendations.append({
                'type': 'warning',
                'area': 'data_integrity',
                'issue': f"{duplicates['total_duplicates']} duplicates found",
                'action': 'Remove duplicate prompts to improve data quality',
                'priority': 'medium'
            })

        # Quality distribution recommendations
        quality_dist = audit_results.get('quality_distribution', {})
        if quality_dist.get('average_quality', 1.0) < 0.7:
            recommendations.append({
                'type': 'warning',
                'area': 'overall_quality',
                'issue': f"Average quality score is {quality_dist['average_quality']:.2f}",
                'action': 'Focus on higher-quality sources and improve generation',
                'priority': 'medium'
            })

        return recommendations

    def update_corpus_statistics(self, audit_results: Dict):
        """Update corpus statistics based on audit results"""
        stats = CorpusStatistics.query.first()
        if not stats:
            stats = CorpusStatistics()
            db.session.add(stats)

        stats.update_statistics()

        # Add quality metrics from audit
        quality_dist = audit_results.get('quality_distribution', {})
        stats.avg_quality_score = quality_dist.get('average_quality', 0.0)

        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logging.error(f"Error updating corpus statistics: {e}")


class PromptValidator:
    """Validates individual prompts for quality and appropriateness"""

    def __init__(self):
        self.min_words = 3
        self.max_words = 30
        self.min_chars = 10
        self.max_chars = 200

    def validate_prompt(self, prompt: Prompt) -> Dict:
        """Validate a single prompt"""
        validation_result = {
            'valid': True,
            'issues': [],
            'warnings': [],
            'calculated_quality': None
        }

        text = prompt.text.strip() if prompt.text else ''

        # Basic validation
        basic_issues = self._validate_basic_requirements(text)
        validation_result['issues'].extend(basic_issues)

        # Content validation
        content_issues = self._validate_content(text)
        validation_result['issues'].extend(content_issues)

        # Structure validation
        structure_warnings = self._validate_structure(text)
        validation_result['warnings'].extend(structure_warnings)

        # Category validation
        category_issues = self._validate_category_match(text, prompt.category)
        validation_result['warnings'].extend(category_issues)

        # Source validation
        source_issues = self._validate_source_quality(prompt)
        validation_result['warnings'].extend(source_issues)

        # Calculate quality score
        validation_result['calculated_quality'] = self._calculate_quality_score(
            text, prompt, len(validation_result['issues']), len(validation_result['warnings'])
        )

        # Determine overall validity
        validation_result['valid'] = len(validation_result['issues']) == 0

        return validation_result

    def _validate_basic_requirements(self, text: str) -> List[str]:
        """Validate basic text requirements"""
        issues = []

        if not text:
            issues.append("Text is empty")
            return issues

        words = text.split()
        if len(words) < self.min_words:
            issues.append(f"Too few words: {len(words)} (minimum: {self.min_words})")

        if len(words) > self.max_words:
            issues.append(f"Too many words: {len(words)} (maximum: {self.max_words})")

        if len(text) < self.min_chars:
            issues.append(f"Too short: {len(text)} characters (minimum: {self.min_chars})")

        if len(text) > self.max_chars:
            issues.append(f"Too long: {len(text)} characters (maximum: {self.max_chars})")

        return issues

    def _validate_content(self, text: str) -> List[str]:
        """Validate content quality and appropriateness"""
        issues = []

        # Character validation
        if not re.match(r'^[A-Za-z0-9\s\.,\?!\'"-]+$', text):
            issues.append("Contains invalid characters")

        # Language validation
        if not self._is_likely_english(text):
            issues.append("Does not appear to be English")

        # Inappropriate content
        if self._contains_inappropriate_content(text):
            issues.append("Contains inappropriate content")

        # Repetitive content
        if self._is_too_repetitive(text):
            issues.append("Content is too repetitive")

        return issues

    def _validate_structure(self, text: str) -> List[str]:
        """Validate text structure"""
        warnings = []

        if not text[0].isupper():
            warnings.append("Should start with capital letter")

        if not text[-1] in '.!?':
            warnings.append("Should end with punctuation")

        # Check for excessive punctuation
        punct_count = sum(1 for char in text if char in '.,!?;:')
        if punct_count > len(text.split()) * 0.3:
            warnings.append("Excessive punctuation")

        return warnings

    def _validate_category_match(self, text: str, category: str) -> List[str]:
        """Validate if text matches its category"""
        warnings = []

        if not category:
            return warnings

        # Category-specific keywords
        category_keywords = {
            'agriculture': ['farm', 'crop', 'plant', 'harvest', 'livestock', 'field', 'soil'],
            'health': ['health', 'medicine', 'doctor', 'hospital', 'sick', 'treatment'],
            'education': ['school', 'learn', 'teach', 'student', 'book', 'study'],
            'family': ['family', 'mother', 'father', 'child', 'home', 'parent'],
            'weather': ['weather', 'rain', 'sun', 'hot', 'cold', 'wind', 'season'],
            'technology': ['computer', 'phone', 'internet', 'technology', 'digital']
        }

        if category in category_keywords:
            keywords = category_keywords[category]
            text_lower = text.lower()
            has_relevant_keyword = any(keyword in text_lower for keyword in keywords)

            if not has_relevant_keyword:
                warnings.append(f"May not match category '{category}'")

        return warnings

    def _validate_source_quality(self, prompt: Prompt) -> List[str]:
        """Validate source-specific quality indicators"""
        warnings = []

        if prompt.source_type == 'llm' and prompt.quality_score and prompt.quality_score < 0.8:
            warnings.append("LLM-generated prompt has low quality score")

        if prompt.source_type == 'community' and not prompt.quality_score:
            warnings.append("Community prompt missing quality assessment")

        if prompt.usage_count > 100:
            warnings.append("Prompt has been used frequently - consider rotating")

        return warnings

    def _is_likely_english(self, text: str) -> bool:
        """Check if text is likely English"""
        common_english = [
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
            'of', 'with', 'by', 'is', 'are', 'was', 'were', 'have', 'has', 'had'
        ]

        words = text.lower().split()
        if not words:
            return False

        english_words = sum(1 for word in words if word.strip('.,!?') in common_english)
        return (english_words / len(words)) >= 0.15

    def _contains_inappropriate_content(self, text: str) -> bool:
        """Check for inappropriate content"""
        inappropriate_words = [
            'damn', 'hell', 'stupid', 'idiot', 'hate', 'kill', 'die', 'death'
        ]
        text_lower = text.lower()
        return any(word in text_lower for word in inappropriate_words)

    def _is_too_repetitive(self, text: str) -> bool:
        """Check for excessive repetition"""
        words = text.lower().split()
        if len(words) < 4:
            return False

        word_counts = Counter(words)
        max_count = max(word_counts.values())
        return max_count > len(words) * 0.4

    def _calculate_quality_score(self, text: str, prompt: Prompt,
                                issue_count: int, warning_count: int) -> float:
        """Calculate quality score for prompt"""
        base_score = 0.8

        # Penalize for issues and warnings
        base_score -= issue_count * 0.2
        base_score -= warning_count * 0.05

        # Bonus for good length
        words = text.split()
        if 5 <= len(words) <= 20:
            base_score += 0.1

        # Bonus for proper structure
        if text[0].isupper() and text[-1] in '.!?':
            base_score += 0.05

        # Source-specific adjustments
        if prompt.source_type == 'corpus':
            base_score += 0.05  # Corpus is generally higher quality

        return max(0.1, min(1.0, base_score))


class TranslationValidator:
    """Validates Kikuyu translations"""

    def validate_translation(self, translation: Translation) -> Dict:
        """Validate a translation"""
        validation_result = {
            'valid': True,
            'issues': [],
            'suspicious': False,
            'suspicious_reasons': []
        }

        kikuyu_text = translation.kikuyu_text.strip() if translation.kikuyu_text else ''
        english_text = translation.prompt.text.strip() if translation.prompt else ''

        # Basic validation
        if not kikuyu_text:
            validation_result['valid'] = False
            validation_result['issues'].append("Translation is empty")
            return validation_result

        # Length validation
        english_words = len(english_text.split()) if english_text else 0
        kikuyu_words = len(kikuyu_text.split())

        # Suspicious length ratios
        if english_words > 0:
            ratio = kikuyu_words / english_words
            if ratio > 3 or ratio < 0.3:
                validation_result['suspicious'] = True
                validation_result['suspicious_reasons'].append(
                    f"Unusual length ratio: {ratio:.2f} (Kikuyu/English)"
                )

        # Character validation for Kikuyu
        if not self._is_valid_kikuyu_text(kikuyu_text):
            validation_result['valid'] = False
            validation_result['issues'].append("Contains invalid characters for Kikuyu")

        # Duplication check
        if kikuyu_text.lower() == english_text.lower():
            validation_result['suspicious'] = True
            validation_result['suspicious_reasons'].append("Translation identical to English")

        # Copy-paste detection
        if self._looks_like_copy_paste(kikuyu_text):
            validation_result['suspicious'] = True
            validation_result['suspicious_reasons'].append("Appears to be copy-pasted text")

        return validation_result

    def _is_valid_kikuyu_text(self, text: str) -> bool:
        """Check if text contains valid Kikuyu characters"""
        # Allow standard Latin characters plus some common Kikuyu patterns
        valid_pattern = r'^[A-Za-z\s\.,\?!\'"-ĩũĩũ]+$'
        return re.match(valid_pattern, text) is not None

    def _looks_like_copy_paste(self, text: str) -> bool:
        """Detect potential copy-paste submissions"""
        # Check for URLs
        if 'http' in text.lower() or 'www.' in text.lower():
            return True

        # Check for English-looking patterns
        english_indicators = ['the ', 'and ', 'that ', 'this ', 'with ']
        text_lower = text.lower()
        english_count = sum(1 for indicator in english_indicators if indicator in text_lower)

        return english_count > len(text.split()) * 0.3


class DuplicateDetector:
    """Detects duplicate prompts and translations"""

    def find_all_duplicates(self) -> Dict:
        """Find all duplicates in the system"""
        result = {
            'prompt_duplicates': self.find_prompt_duplicates(),
            'translation_duplicates': self.find_translation_duplicates(),
            'total_duplicates': 0
        }

        result['total_duplicates'] = (
            len(result['prompt_duplicates']) + len(result['translation_duplicates'])
        )

        return result

    def find_prompt_duplicates(self) -> List[Dict]:
        """Find duplicate prompts"""
        # Group prompts by normalized text
        prompts = Prompt.query.filter_by(status='active').all()
        text_groups = {}

        for prompt in prompts:
            normalized = self._normalize_text(prompt.text)
            if normalized not in text_groups:
                text_groups[normalized] = []
            text_groups[normalized].append(prompt)

        # Find groups with duplicates
        duplicates = []
        for normalized_text, prompt_group in text_groups.items():
            if len(prompt_group) > 1:
                duplicates.append({
                    'normalized_text': normalized_text,
                    'count': len(prompt_group),
                    'prompt_ids': [p.id for p in prompt_group],
                    'sources': list(set(p.source_type for p in prompt_group))
                })

        return duplicates

    def find_translation_duplicates(self) -> List[Dict]:
        """Find duplicate translations for the same prompt"""
        # Find prompts with multiple translations
        duplicates = []

        prompt_translation_counts = db.session.query(
            Translation.prompt_id,
            func.count(Translation.id).label('count')
        ).group_by(Translation.prompt_id).having(
            func.count(Translation.id) > 1
        ).all()

        for prompt_id, count in prompt_translation_counts:
            translations = Translation.query.filter_by(prompt_id=prompt_id).all()

            # Check for identical translations
            text_groups = {}
            for translation in translations:
                normalized = self._normalize_text(translation.kikuyu_text)
                if normalized not in text_groups:
                    text_groups[normalized] = []
                text_groups[normalized].append(translation)

            for normalized_text, translation_group in text_groups.items():
                if len(translation_group) > 1:
                    duplicates.append({
                        'prompt_id': prompt_id,
                        'normalized_text': normalized_text,
                        'count': len(translation_group),
                        'translation_ids': [t.id for t in translation_group]
                    })

        return duplicates

    def _normalize_text(self, text: str) -> str:
        """Normalize text for comparison"""
        if not text:
            return ''

        # Convert to lowercase, remove extra spaces and punctuation
        normalized = re.sub(r'[^\w\s]', '', text.lower())
        normalized = re.sub(r'\s+', ' ', normalized).strip()

        return normalized


class QualityScorer:
    """Analyzes quality distribution across the corpus"""

    def analyze_distribution(self) -> Dict:
        """Analyze quality score distribution"""
        prompts = Prompt.query.filter_by(status='active').all()

        if not prompts:
            return {'average_quality': 0, 'distribution': {}}

        quality_scores = [p.quality_score or 0.8 for p in prompts]

        # Calculate distribution
        distribution = {
            'high_quality': sum(1 for score in quality_scores if score >= 0.8),
            'medium_quality': sum(1 for score in quality_scores if 0.6 <= score < 0.8),
            'low_quality': sum(1 for score in quality_scores if score < 0.6)
        }

        # By source type
        source_quality = {}
        for prompt in prompts:
            source = prompt.source_type or 'unknown'
            if source not in source_quality:
                source_quality[source] = []
            source_quality[source].append(prompt.quality_score or 0.8)

        source_averages = {
            source: sum(scores) / len(scores)
            for source, scores in source_quality.items()
        }

        return {
            'average_quality': sum(quality_scores) / len(quality_scores),
            'total_prompts': len(prompts),
            'distribution': distribution,
            'by_source': source_averages
        }


class BatchProcessor:
    """Process quality control tasks in batches"""

    def process_quality_updates(self, batch_size: int = 100) -> Dict:
        """Process quality updates in batches"""
        results = {
            'processed': 0,
            'updated': 0,
            'errors': 0
        }

        # Process prompts without quality scores
        prompts_without_scores = Prompt.query.filter(
            or_(Prompt.quality_score.is_(None), Prompt.quality_score == 0)
        ).limit(batch_size).all()

        validator = PromptValidator()

        for prompt in prompts_without_scores:
            try:
                validation_result = validator.validate_prompt(prompt)
                if validation_result.get('calculated_quality'):
                    prompt.quality_score = validation_result['calculated_quality']
                    results['updated'] += 1

                results['processed'] += 1

            except Exception as e:
                logging.error(f"Error processing prompt {prompt.id}: {e}")
                results['errors'] += 1

        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logging.error(f"Error committing quality updates: {e}")
            results['errors'] += len(prompts_without_scores)

        return results