from datetime import datetime
from app import db

class Prompt(db.Model):
    """Model for storing English prompts for translation - Enhanced for hybrid system"""
    __tablename__ = 'prompts'

    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(50), nullable=True)  # Greetings, Family, Farming, etc.

    # Hybrid system fields
    source_type = db.Column(db.String(20), nullable=False, default='llm')  # 'corpus', 'llm', 'community'
    source_file = db.Column(db.String(100), nullable=True)  # Original file/source identifier
    difficulty_level = db.Column(db.String(20), default='basic')  # basic, intermediate, advanced
    keywords = db.Column(db.Text, nullable=True)  # JSON array of keywords
    prompt_metadata = db.Column(db.Text, nullable=True)  # JSON additional data
    quality_score = db.Column(db.Float, default=0.8)  # Quality score 0.0-1.0

    # Original fields
    date_generated = db.Column(db.DateTime, default=datetime.utcnow)
    usage_count = db.Column(db.Integer, default=0)
    status = db.Column(db.String(20), default='active')  # active, inactive, deleted

    # Relationship to translations
    translations = db.relationship('Translation', backref='prompt', lazy=True)

    def __repr__(self):
        return f'<Prompt {self.id}: {self.source_type} - {self.text[:50]}...>'

    def to_dict(self):
        """Convert to dictionary for API responses"""
        return {
            'id': self.id,
            'text': self.text,
            'category': self.category,
            'source_type': self.source_type,
            'difficulty_level': self.difficulty_level,
            'quality_score': self.quality_score,
            'usage_count': self.usage_count
        }

class User(db.Model):
    """Model for tracking user sessions and submissions"""
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.String(255), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    submission_count = db.Column(db.Integer, default=0)
    last_activity = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationship to translations
    translations = db.relationship('Translation', backref='user', lazy=True)

    def __repr__(self):
        return f'<User {self.id}: {self.session_id}>'

class Translation(db.Model):
    """Model for storing Kikuyu translations"""
    __tablename__ = 'translations'

    id = db.Column(db.Integer, primary_key=True)
    prompt_id = db.Column(db.Integer, db.ForeignKey('prompts.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    kikuyu_text = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='pending')  # pending, approved, rejected, flagged

    # Optional metadata
    ip_address = db.Column(db.String(45))  # For tracking and moderation
    user_agent = db.Column(db.String(255))  # For tracking

    def __repr__(self):
        return f'<Translation {self.id}: {self.kikuyu_text[:30]}...>'

class AdminAction(db.Model):
    """Model for tracking admin moderation actions"""
    __tablename__ = 'admin_actions'

    id = db.Column(db.Integer, primary_key=True)
    translation_id = db.Column(db.Integer, db.ForeignKey('translations.id'), nullable=False)
    action = db.Column(db.String(20), nullable=False)  # approve, reject, flag, delete
    admin_id = db.Column(db.String(100), nullable=False)  # Admin identifier
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    notes = db.Column(db.Text)  # Optional notes about the action

    # Relationship to translation
    translation = db.relationship('Translation', backref='admin_actions')

    def __repr__(self):
        return f'<AdminAction {self.id}: {self.action} on Translation {self.translation_id}>'

class PromptCache(db.Model):
    """Model for tracking prompt cache metadata"""
    __tablename__ = 'prompt_cache'

    id = db.Column(db.Integer, primary_key=True)
    cache_size = db.Column(db.Integer, default=0)
    last_updated = db.Column(db.DateTime, default=datetime.utcnow)
    last_refill = db.Column(db.DateTime)
    api_calls_today = db.Column(db.Integer, default=0)
    api_calls_date = db.Column(db.Date, default=datetime.utcnow().date())

    def __repr__(self):
        return f'<PromptCache: {self.cache_size} prompts, updated {self.last_updated}>'


class DomainCoverage(db.Model):
    """Model for tracking translation coverage by domain/category"""
    __tablename__ = 'domain_coverage'

    id = db.Column(db.Integer, primary_key=True)
    category = db.Column(db.String(50), nullable=False, unique=True)
    target_count = db.Column(db.Integer, default=1000)  # Target number of translations
    current_count = db.Column(db.Integer, default=0)  # Current translations
    completion_percentage = db.Column(db.Float, default=0.0)
    last_updated = db.Column(db.DateTime, default=datetime.utcnow)

    # Quality metrics
    avg_quality_score = db.Column(db.Float, default=0.0)
    approved_count = db.Column(db.Integer, default=0)
    rejected_count = db.Column(db.Integer, default=0)

    def __repr__(self):
        return f'<DomainCoverage {self.category}: {self.completion_percentage}% complete>'

    def update_coverage(self):
        """Update completion percentage"""
        if self.target_count > 0:
            self.completion_percentage = (self.current_count / self.target_count) * 100
        self.last_updated = datetime.utcnow()


class CommunitySubmission(db.Model):
    """Model for community-submitted English prompts"""
    __tablename__ = 'community_submissions'

    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(50), nullable=True)
    difficulty_level = db.Column(db.String(20), default='basic')

    # Submission metadata
    submitted_by = db.Column(db.String(255), nullable=True)  # Optional submitter ID
    submission_timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    submission_ip = db.Column(db.String(45), nullable=True)

    # Review status
    status = db.Column(db.String(20), default='pending')  # pending, approved, rejected
    reviewed_by = db.Column(db.String(100), nullable=True)  # Admin who reviewed
    review_timestamp = db.Column(db.DateTime, nullable=True)
    review_notes = db.Column(db.Text, nullable=True)

    # Quality assessment
    quality_score = db.Column(db.Float, default=0.0)

    def __repr__(self):
        return f'<CommunitySubmission {self.id}: {self.status} - {self.text[:30]}...>'

    def approve(self, admin_id, notes=None):
        """Approve the submission and convert to a prompt"""
        self.status = 'approved'
        self.reviewed_by = admin_id
        self.review_timestamp = datetime.utcnow()
        self.review_notes = notes

        # Create a prompt from this submission
        prompt = Prompt(
            text=self.text,
            category=self.category,
            source_type='community',
            source_file=f'community_submission_{self.id}',
            difficulty_level=self.difficulty_level,
            quality_score=self.quality_score or 0.8
        )
        db.session.add(prompt)
        return prompt


class CorpusStatistics(db.Model):
    """Model for tracking overall corpus statistics"""
    __tablename__ = 'corpus_statistics'

    id = db.Column(db.Integer, primary_key=True)

    # Source distribution
    corpus_count = db.Column(db.Integer, default=0)
    llm_count = db.Column(db.Integer, default=0)
    community_count = db.Column(db.Integer, default=0)
    total_prompts = db.Column(db.Integer, default=0)

    # Translation statistics
    total_translations = db.Column(db.Integer, default=0)
    approved_translations = db.Column(db.Integer, default=0)
    pending_translations = db.Column(db.Integer, default=0)

    # Quality metrics
    avg_quality_score = db.Column(db.Float, default=0.0)
    coverage_completeness = db.Column(db.Float, default=0.0)  # Percentage of target coverage achieved

    # Update timestamps
    last_updated = db.Column(db.DateTime, default=datetime.utcnow)
    last_corpus_build = db.Column(db.DateTime, nullable=True)

    def __repr__(self):
        return f'<CorpusStatistics: {self.total_prompts} prompts, {self.total_translations} translations>'

    def update_statistics(self):
        """Update all statistics from current data"""
        # Count prompts by source
        self.corpus_count = Prompt.query.filter_by(source_type='corpus').count()
        self.llm_count = Prompt.query.filter_by(source_type='llm').count()
        self.community_count = Prompt.query.filter_by(source_type='community').count()
        self.total_prompts = Prompt.query.count()

        # Count translations
        self.total_translations = Translation.query.count()
        self.approved_translations = Translation.query.filter_by(status='approved').count()
        self.pending_translations = Translation.query.filter_by(status='pending').count()

        # Calculate average quality
        avg_quality = db.session.query(db.func.avg(Prompt.quality_score)).scalar()
        self.avg_quality_score = avg_quality or 0.0

        # Calculate coverage completeness
        coverage_query = db.session.query(db.func.avg(DomainCoverage.completion_percentage)).scalar()
        self.coverage_completeness = coverage_query or 0.0

        self.last_updated = datetime.utcnow()


class UserProgress(db.Model):
    """Model for tracking individual user progress across categories"""
    __tablename__ = 'user_progress'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    category = db.Column(db.String(50), nullable=False)

    # Progress tracking
    prompts_completed = db.Column(db.Integer, default=0)
    last_prompt_id = db.Column(db.Integer, db.ForeignKey('prompts.id'), nullable=True)
    last_activity = db.Column(db.DateTime, default=datetime.utcnow)

    # Performance metrics
    avg_response_time = db.Column(db.Float, default=0.0)  # Average time to complete translation
    completion_rate = db.Column(db.Float, default=0.0)  # Percentage of started prompts completed

    # Constraints
    __table_args__ = (db.UniqueConstraint('user_id', 'category', name='user_category_unique'),)

    def __repr__(self):
        return f'<UserProgress User {self.user_id}, {self.category}: {self.prompts_completed} completed>'