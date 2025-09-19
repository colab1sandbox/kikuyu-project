from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, PasswordField, SelectField, HiddenField
from wtforms.validators import DataRequired, Length, Optional

class TranslationForm(FlaskForm):
    """Form for submitting Kikuyu translations"""
    prompt_id = HiddenField('Prompt ID', validators=[DataRequired()])
    kikuyu_text = TextAreaField(
        'Kikuyu Translation',
        validators=[
            DataRequired(message='Please provide a Kikuyu translation'),
            Length(min=1, max=1000, message='Translation must be between 1 and 1000 characters')
        ],
        render_kw={
            'placeholder': 'Type your Kikuyu translation here...',
            'rows': 4,
            'class': 'w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-none'
        }
    )

class AdminLoginForm(FlaskForm):
    """Form for admin authentication"""
    password = PasswordField(
        'Admin Password',
        validators=[DataRequired()],
        render_kw={
            'placeholder': 'Enter admin password',
            'class': 'w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent'
        }
    )

class AdminModerationForm(FlaskForm):
    """Form for admin moderation actions"""
    action = SelectField(
        'Action',
        choices=[
            ('approve', 'Approve'),
            ('reject', 'Reject'),
            ('flag', 'Flag for Review')
        ],
        validators=[DataRequired()]
    )
    notes = TextAreaField(
        'Notes (Optional)',
        validators=[Optional(), Length(max=500)],
        render_kw={
            'placeholder': 'Add notes about this action...',
            'rows': 3
        }
    )

class PromptManagementForm(FlaskForm):
    """Form for managing prompts in admin panel"""
    text = TextAreaField(
        'Prompt Text',
        validators=[
            DataRequired(message='Prompt text is required'),
            Length(min=10, max=500, message='Prompt must be between 10 and 500 characters')
        ],
        render_kw={
            'placeholder': 'Enter English prompt for translation...',
            'rows': 3
        }
    )
    category = SelectField(
        'Category',
        choices=[
            ('greetings', 'Greetings'),
            ('family', 'Family'),
            ('farming', 'Farming'),
            ('health', 'Health'),
            ('school', 'School'),
            ('weather', 'Weather'),
            ('general', 'General')
        ],
        validators=[DataRequired()]
    )
    status = SelectField(
        'Status',
        choices=[
            ('active', 'Active'),
            ('inactive', 'Inactive')
        ],
        validators=[DataRequired()]
    )


class CommunitySubmissionForm(FlaskForm):
    """Form for community prompt submissions"""
    text = TextAreaField(
        'English Sentence',
        validators=[
            DataRequired(message='Please provide an English sentence'),
            Length(min=10, max=200, message='Sentence must be between 10 and 200 characters')
        ],
        render_kw={
            'placeholder': 'Enter a clear English sentence for translation...',
            'rows': 3,
            'class': 'w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-none'
        }
    )

    category = SelectField(
        'Category',
        choices=[
            ('greetings', 'Greetings & Social'),
            ('family', 'Family & Home'),
            ('agriculture', 'Agriculture & Farming'),
            ('health', 'Health & Medicine'),
            ('education', 'Education & Learning'),
            ('weather', 'Weather & Nature'),
            ('technology', 'Technology'),
            ('business', 'Business & Trade'),
            ('culture', 'Culture & Traditions'),
            ('conversation', 'Daily Conversation'),
            ('general', 'General')
        ],
        validators=[DataRequired()],
        render_kw={
            'class': 'w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent'
        }
    )

    difficulty = SelectField(
        'Difficulty Level',
        choices=[
            ('basic', 'Basic (Simple words, short sentences)'),
            ('intermediate', 'Intermediate (Common phrases, moderate length)'),
            ('advanced', 'Advanced (Complex sentences, technical terms)')
        ],
        validators=[DataRequired()],
        render_kw={
            'class': 'w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent'
        }
    )