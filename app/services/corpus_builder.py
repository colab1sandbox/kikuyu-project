"""
Corpus Builder Service - Multi-source English sentence extraction and processing
Supports Wikipedia, Tatoeba, News, Educational content, and Community sources
"""

import requests
import json
import csv
import re
import os
import gzip
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from flask import current_app
import sqlite3


class CorpusBuilder:
    """Main corpus builder orchestrating multiple data sources"""

    def __init__(self):
        self.data_dir = os.path.join(current_app.root_path, '..', 'data', 'corpus')
        self.ensure_data_directories()

        # Initialize extractors
        self.extractors = {
            'tatoeba': TatoebaExtractor(self.data_dir),
            'wikipedia': WikipediaExtractor(self.data_dir),
            'news': NewsExtractor(self.data_dir),
            'education': EducationExtractor(self.data_dir),
            'conversation': ConversationExtractor(self.data_dir),
            'technical': TechnicalExtractor(self.data_dir)
        }

        self.processor = SentenceProcessor()

    def ensure_data_directories(self):
        """Create necessary directories for corpus data"""
        os.makedirs(self.data_dir, exist_ok=True)
        os.makedirs(os.path.join(self.data_dir, 'raw'), exist_ok=True)
        os.makedirs(os.path.join(self.data_dir, 'processed'), exist_ok=True)
        os.makedirs(os.path.join(self.data_dir, 'downloads'), exist_ok=True)

    def build_initial_corpus(self, target_size: int = 70000):
        """Build initial corpus with immediate sources (Tatoeba + Wikipedia)"""
        print(f"Building initial corpus targeting {target_size} sentences...")

        results = {}

        # Phase 1: Quick wins - Tatoeba (immediate download)
        print("Phase 1: Extracting from Tatoeba...")
        tatoeba_sentences = self.extractors['tatoeba'].extract_sentences(limit=10000)
        results['tatoeba'] = len(tatoeba_sentences)

        # Phase 2: Wikipedia Simple English
        print("Phase 2: Extracting from Wikipedia...")
        wiki_sentences = self.extractors['wikipedia'].extract_sentences(limit=50000)
        results['wikipedia'] = len(wiki_sentences)

        # Phase 3: Basic conversation patterns
        print("Phase 3: Creating conversation patterns...")
        conv_sentences = self.extractors['conversation'].extract_sentences(limit=5000)
        results['conversation'] = len(conv_sentences)

        # Combine and process
        all_sentences = tatoeba_sentences + wiki_sentences + conv_sentences
        processed_sentences = self.processor.process_batch(all_sentences)

        # Save to database
        self.save_to_database(processed_sentences)

        print(f"Initial corpus built: {results}")
        return results

    def scale_corpus(self, target_size: int = 500000):
        """Scale corpus to medium size with additional sources"""
        print(f"Scaling corpus to {target_size} sentences...")

        results = {}

        # News extraction
        news_sentences = self.extractors['news'].extract_sentences(limit=200000)
        results['news'] = len(news_sentences)

        # Educational content
        edu_sentences = self.extractors['education'].extract_sentences(limit=100000)
        results['education'] = len(edu_sentences)

        # Technical documentation
        tech_sentences = self.extractors['technical'].extract_sentences(limit=80000)
        results['technical'] = len(tech_sentences)

        # Process and save
        all_sentences = news_sentences + edu_sentences + tech_sentences
        processed_sentences = self.processor.process_batch(all_sentences)
        self.save_to_database(processed_sentences)

        print(f"Corpus scaled: {results}")
        return results

    def build_million_scale(self):
        """Build million+ scale corpus"""
        print("Building million-scale corpus...")

        # This would involve:
        # - Common Crawl processing
        # - Book corpus from Project Gutenberg
        # - Social media data (cleaned)
        # - Domain-specific corpora

        # Implementation would be similar but with larger data sources
        pass

    def save_to_database(self, sentences: List[Dict]):
        """Save processed sentences to database"""
        from app.models import Prompt
        from app import db

        for sentence_data in sentences:
            prompt = Prompt(
                text=sentence_data['text'],
                category=sentence_data['category'],
                source_type=sentence_data['source_type'],
                source_file=sentence_data.get('source_file', ''),
                difficulty_level=sentence_data.get('difficulty', 'basic'),
                keywords=json.dumps(sentence_data.get('keywords', [])),
                prompt_metadata=json.dumps(sentence_data.get('metadata', {})),
                quality_score=sentence_data.get('quality_score', 0.8)
            )
            db.session.add(prompt)

        try:
            db.session.commit()
            print(f"Saved {len(sentences)} sentences to database")
        except Exception as e:
            db.session.rollback()
            print(f"Error saving to database: {e}")

    def analyze_coverage(self) -> Dict:
        """Analyze current corpus coverage by category and difficulty"""
        from app.models import Prompt

        coverage = {}
        prompts = Prompt.query.all()

        # Category distribution
        category_counts = {}
        for prompt in prompts:
            category_counts[prompt.category] = category_counts.get(prompt.category, 0) + 1

        coverage['categories'] = category_counts
        coverage['total_prompts'] = len(prompts)
        coverage['average_quality'] = sum(p.quality_score for p in prompts) / len(prompts) if prompts else 0

        return coverage


class TatoebaExtractor:
    """Extract sentences from Tatoeba corpus"""

    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        self.download_url = "https://downloads.tatoeba.org/exports/sentences.tar.bz2"

    def extract_sentences(self, limit: int = 10000) -> List[Dict]:
        """Extract English sentences from Tatoeba"""
        sentences = []

        # Download if not exists
        sentences_file = os.path.join(self.data_dir, 'downloads', 'sentences.csv')
        if not os.path.exists(sentences_file):
            self.download_tatoeba_data()

        # Extract English sentences
        try:
            with open(sentences_file, 'r', encoding='utf-8') as f:
                reader = csv.reader(f, delimiter='\t')
                for row in reader:
                    if len(row) >= 3 and row[1] == 'eng':  # English sentences
                        sentence = row[2].strip()
                        if self.is_valid_sentence(sentence):
                            sentences.append({
                                'text': sentence,
                                'category': self.categorize_sentence(sentence),
                                'source_type': 'corpus',
                                'source_file': 'tatoeba',
                                'difficulty': self.assess_difficulty(sentence),
                                'keywords': self.extract_keywords(sentence),
                                'quality_score': 0.9  # Tatoeba is high quality
                            })

                            if len(sentences) >= limit:
                                break
        except Exception as e:
            print(f"Error extracting Tatoeba sentences: {e}")

        return sentences

    def download_tatoeba_data(self):
        """Download and extract Tatoeba data"""
        print("Downloading Tatoeba corpus...")
        # This would implement the actual download
        # For now, we'll create a mock CSV file
        sentences_file = os.path.join(self.data_dir, 'downloads', 'sentences.csv')

        # Mock some sample data
        sample_sentences = [
            "1\teng\tHello, how are you today?",
            "2\teng\tI like to eat apples.",
            "3\teng\tThe weather is beautiful.",
            "4\teng\tShe is reading a book.",
            "5\teng\tWe went to the market yesterday.",
            "6\teng\tThe farmer planted maize in his field.",
            "7\teng\tChildren are playing in the school yard.",
            "8\teng\tMy mother is cooking dinner.",
            "9\teng\tThe sun rises in the east.",
            "10\teng\tCan you help me with this problem?"
        ]

        os.makedirs(os.path.dirname(sentences_file), exist_ok=True)
        with open(sentences_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(sample_sentences))

        print("Tatoeba data downloaded")

    def is_valid_sentence(self, sentence: str) -> bool:
        """Check if sentence is valid for translation"""
        if len(sentence.split()) < 3 or len(sentence.split()) > 25:
            return False
        if not re.match(r'^[A-Za-z0-9\s\.,\?!\'"-]+$', sentence):
            return False
        return True

    def categorize_sentence(self, sentence: str) -> str:
        """Basic categorization based on keywords"""
        sentence_lower = sentence.lower()

        if any(word in sentence_lower for word in ['hello', 'how are you', 'goodbye', 'please', 'thank you']):
            return 'greetings'
        elif any(word in sentence_lower for word in ['mother', 'father', 'family', 'child', 'sister', 'brother']):
            return 'family'
        elif any(word in sentence_lower for word in ['farm', 'crop', 'plant', 'harvest', 'maize', 'field']):
            return 'agriculture'
        elif any(word in sentence_lower for word in ['school', 'learn', 'teach', 'student', 'book']):
            return 'education'
        elif any(word in sentence_lower for word in ['weather', 'rain', 'sun', 'hot', 'cold']):
            return 'weather'
        else:
            return 'general'

    def assess_difficulty(self, sentence: str) -> str:
        """Assess sentence difficulty"""
        word_count = len(sentence.split())

        if word_count <= 8:
            return 'basic'
        elif word_count <= 15:
            return 'intermediate'
        else:
            return 'advanced'

    def extract_keywords(self, sentence: str) -> List[str]:
        """Extract key words from sentence"""
        # Simple keyword extraction
        words = sentence.lower().split()
        # Filter out common words
        stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'is', 'are', 'was', 'were'}
        keywords = [word.strip('.,!?') for word in words if word not in stop_words and len(word) > 2]
        return keywords[:5]  # Return top 5 keywords


class WikipediaExtractor:
    """Extract sentences from Wikipedia Simple English"""

    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        self.api_url = "https://simple.wikipedia.org/api/rest_v1/page/random/summary"

    def extract_sentences(self, limit: int = 50000) -> List[Dict]:
        """Extract sentences from Wikipedia Simple English"""
        sentences = []
        articles_processed = 0
        max_articles = min(1000, limit // 50)  # Estimate 50 sentences per article

        print(f"Extracting from Wikipedia Simple English (targeting {max_articles} articles)...")

        while len(sentences) < limit and articles_processed < max_articles:
            try:
                # Get random article
                response = requests.get(self.api_url)
                if response.status_code == 200:
                    article_data = response.json()
                    extract = article_data.get('extract', '')

                    if extract:
                        article_sentences = self.process_article_text(extract, article_data.get('title', 'Unknown'))
                        sentences.extend(article_sentences)
                        articles_processed += 1

                        if articles_processed % 100 == 0:
                            print(f"Processed {articles_processed} articles, extracted {len(sentences)} sentences")

            except Exception as e:
                print(f"Error processing Wikipedia article: {e}")
                continue

        return sentences[:limit]

    def process_article_text(self, text: str, title: str) -> List[Dict]:
        """Process article text into individual sentences"""
        sentences = []

        # Split into sentences
        sentence_list = re.split(r'[.!?]+', text)

        for sentence in sentence_list:
            sentence = sentence.strip()
            if self.is_valid_sentence(sentence):
                sentences.append({
                    'text': sentence,
                    'category': self.categorize_by_title(title),
                    'source_type': 'corpus',
                    'source_file': f'wikipedia_{title.lower().replace(" ", "_")}',
                    'difficulty': self.assess_difficulty(sentence),
                    'keywords': self.extract_keywords(sentence),
                    'quality_score': 0.85,
                    'metadata': {'article_title': title}
                })

        return sentences

    def is_valid_sentence(self, sentence: str) -> bool:
        """Check if sentence is valid"""
        words = sentence.split()
        if len(words) < 5 or len(words) > 30:
            return False
        if not re.match(r'^[A-Za-z0-9\s\.,\?!\'"-]+$', sentence):
            return False
        return True

    def categorize_by_title(self, title: str) -> str:
        """Categorize based on article title"""
        title_lower = title.lower()

        if any(word in title_lower for word in ['science', 'biology', 'chemistry', 'physics']):
            return 'science'
        elif any(word in title_lower for word in ['history', 'war', 'ancient', 'empire']):
            return 'history'
        elif any(word in title_lower for word in ['geography', 'country', 'city', 'mountain', 'river']):
            return 'geography'
        elif any(word in title_lower for word in ['culture', 'art', 'music', 'literature']):
            return 'culture'
        else:
            return 'general'

    def assess_difficulty(self, sentence: str) -> str:
        """Assess sentence difficulty"""
        word_count = len(sentence.split())
        complex_words = len([w for w in sentence.split() if len(w) > 7])

        if word_count <= 10 and complex_words <= 2:
            return 'basic'
        elif word_count <= 20 and complex_words <= 4:
            return 'intermediate'
        else:
            return 'advanced'

    def extract_keywords(self, sentence: str) -> List[str]:
        """Extract keywords from sentence"""
        words = sentence.lower().split()
        stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'is', 'are', 'was', 'were', 'this', 'that', 'these', 'those'}
        keywords = [word.strip('.,!?') for word in words if word not in stop_words and len(word) > 3]
        return keywords[:5]


class NewsExtractor:
    """Extract sentences from news sources"""

    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        self.sources = [
            "https://www.bbc.com/news",
            "https://www.voanews.com/",
            # Add more news sources
        ]

    def extract_sentences(self, limit: int = 200000) -> List[Dict]:
        """Extract sentences from news sources"""
        sentences = []

        # For now, return mock news sentences
        # In production, this would scrape actual news sites
        mock_news = [
            "The government announced new policies for economic development.",
            "Scientists discovered a new species in the Amazon rainforest.",
            "The football team won their match yesterday evening.",
            "Farmers in the region are preparing for the planting season.",
            "The hospital opened a new wing for children's health services.",
            "Students across the country are returning to school this week.",
            "The weather forecast predicts heavy rainfall this weekend.",
            "Local markets are selling fresh vegetables at good prices.",
            "The community center organized a cultural festival last month.",
            "Technology companies are investing in renewable energy projects."
        ]

        for i, sentence in enumerate(mock_news * (limit // len(mock_news) + 1)):
            if len(sentences) >= limit:
                break

            sentences.append({
                'text': sentence,
                'category': 'news',
                'source_type': 'corpus',
                'source_file': 'news_mock',
                'difficulty': 'intermediate',
                'keywords': self.extract_keywords(sentence),
                'quality_score': 0.8
            })

        return sentences[:limit]

    def extract_keywords(self, sentence: str) -> List[str]:
        """Extract keywords"""
        words = sentence.lower().split()
        stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by'}
        keywords = [word.strip('.,!?') for word in words if word not in stop_words and len(word) > 3]
        return keywords[:5]


class EducationExtractor:
    """Extract sentences from educational content"""

    def __init__(self, data_dir: str):
        self.data_dir = data_dir

    def extract_sentences(self, limit: int = 100000) -> List[Dict]:
        """Extract educational sentences"""
        sentences = []

        # Mock educational content
        educational_content = [
            "Mathematics is the study of numbers, shapes, and patterns.",
            "The human body has many different systems that work together.",
            "Plants need sunlight, water, and nutrients to grow properly.",
            "History helps us understand how people lived in the past.",
            "Reading books improves vocabulary and comprehension skills.",
            "Science experiments help students learn about the natural world.",
            "Art and music are important forms of creative expression.",
            "Geography teaches us about different places around the world.",
            "Learning a second language opens many opportunities.",
            "Physical education keeps our bodies healthy and strong."
        ]

        for i, sentence in enumerate(educational_content * (limit // len(educational_content) + 1)):
            if len(sentences) >= limit:
                break

            sentences.append({
                'text': sentence,
                'category': 'education',
                'source_type': 'corpus',
                'source_file': 'education_mock',
                'difficulty': 'basic',
                'keywords': self.extract_keywords(sentence),
                'quality_score': 0.9
            })

        return sentences[:limit]

    def extract_keywords(self, sentence: str) -> List[str]:
        """Extract keywords"""
        words = sentence.lower().split()
        stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'is', 'are'}
        keywords = [word.strip('.,!?') for word in words if word not in stop_words and len(word) > 3]
        return keywords[:5]


class ConversationExtractor:
    """Extract conversational sentences and common phrases"""

    def __init__(self, data_dir: str):
        self.data_dir = data_dir

    def extract_sentences(self, limit: int = 5000) -> List[Dict]:
        """Extract conversation sentences"""
        sentences = []

        conversation_patterns = [
            "Hello, how are you doing today?",
            "What is your name?",
            "Where do you come from?",
            "How old are you?",
            "What do you do for work?",
            "Do you have any children?",
            "What time is it now?",
            "How much does this cost?",
            "Can you help me please?",
            "Thank you very much for your help.",
            "I am sorry for being late.",
            "See you tomorrow morning.",
            "Have a good day!",
            "Please sit down here.",
            "Would you like some tea?",
            "The food tastes very good.",
            "I need to go home now.",
            "Where is the nearest hospital?",
            "Can you speak more slowly?",
            "I don't understand what you said."
        ]

        for sentence in conversation_patterns * (limit // len(conversation_patterns) + 1):
            if len(sentences) >= limit:
                break

            sentences.append({
                'text': sentence,
                'category': 'conversation',
                'source_type': 'corpus',
                'source_file': 'conversation_patterns',
                'difficulty': 'basic',
                'keywords': self.extract_keywords(sentence),
                'quality_score': 0.95
            })

        return sentences[:limit]

    def extract_keywords(self, sentence: str) -> List[str]:
        """Extract keywords"""
        words = sentence.lower().split()
        stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'you', 'i', 'me'}
        keywords = [word.strip('.,!?') for word in words if word not in stop_words and len(word) > 2]
        return keywords[:5]


class TechnicalExtractor:
    """Extract technical and domain-specific sentences"""

    def __init__(self, data_dir: str):
        self.data_dir = data_dir

    def extract_sentences(self, limit: int = 80000) -> List[Dict]:
        """Extract technical sentences"""
        sentences = []

        # Mock technical content across different domains
        technical_content = [
            "The computer program runs on multiple operating systems.",
            "Regular maintenance helps machines work more efficiently.",
            "Database management requires careful planning and organization.",
            "Network security protects information from unauthorized access.",
            "Solar panels convert sunlight into electrical energy.",
            "Medical equipment must be sterilized before each use.",
            "Construction workers follow safety protocols on building sites.",
            "Agricultural machinery increases farming productivity significantly.",
            "Quality control ensures products meet required standards.",
            "Transportation systems connect people and goods across distances."
        ]

        for sentence in technical_content * (limit // len(technical_content) + 1):
            if len(sentences) >= limit:
                break

            sentences.append({
                'text': sentence,
                'category': 'technical',
                'source_type': 'corpus',
                'source_file': 'technical_mock',
                'difficulty': 'advanced',
                'keywords': self.extract_keywords(sentence),
                'quality_score': 0.85
            })

        return sentences[:limit]

    def extract_keywords(self, sentence: str) -> List[str]:
        """Extract keywords"""
        words = sentence.lower().split()
        stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'is', 'are'}
        keywords = [word.strip('.,!?') for word in words if word not in stop_words and len(word) > 3]
        return keywords[:5]


class SentenceProcessor:
    """Process and clean extracted sentences"""

    def process_batch(self, sentences: List[Dict]) -> List[Dict]:
        """Process a batch of sentences"""
        processed = []
        seen_texts = set()

        for sentence in sentences:
            # Deduplicate
            text = sentence['text'].strip()
            if text.lower() in seen_texts:
                continue
            seen_texts.add(text.lower())

            # Clean and validate
            cleaned_text = self.clean_sentence(text)
            if self.is_valid_for_translation(cleaned_text):
                sentence['text'] = cleaned_text
                sentence['quality_score'] = self.calculate_quality_score(sentence)
                processed.append(sentence)

        return processed

    def clean_sentence(self, text: str) -> str:
        """Clean sentence text"""
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text).strip()

        # Ensure proper capitalization
        if text and not text[0].isupper():
            text = text[0].upper() + text[1:]

        # Ensure proper ending punctuation
        if text and text[-1] not in '.!?':
            text += '.'

        return text

    def is_valid_for_translation(self, text: str) -> bool:
        """Check if sentence is suitable for translation"""
        words = text.split()

        # Length check
        if len(words) < 3 or len(words) > 30:
            return False

        # Character check
        if not re.match(r'^[A-Za-z0-9\s\.,\?!\'"-]+$', text):
            return False

        # No excessive repetition
        if len(set(words)) < len(words) * 0.6:
            return False

        return True

    def calculate_quality_score(self, sentence: Dict) -> float:
        """Calculate quality score for sentence"""
        score = sentence.get('quality_score', 0.8)

        text = sentence['text']
        words = text.split()

        # Adjust based on length (prefer 5-20 words)
        if 5 <= len(words) <= 20:
            score += 0.1
        elif len(words) < 5 or len(words) > 25:
            score -= 0.1

        # Adjust based on complexity
        complex_words = sum(1 for word in words if len(word) > 8)
        if complex_words > len(words) * 0.3:
            score -= 0.05

        # Ensure score is between 0 and 1
        return max(0.0, min(1.0, score))