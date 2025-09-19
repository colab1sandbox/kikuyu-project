import requests
import json
import logging
from datetime import datetime, date
from flask import current_app
from typing import Optional, Dict, Any

class OpenRouterClient:
    """Client for interacting with OpenRouter API"""

    def __init__(self):
        self.api_key = current_app.config.get('OPENROUTER_API_KEY')
        self.model = current_app.config.get('OPENROUTER_MODEL', 'mistralai/mistral-7b-instruct')
        self.base_url = "https://openrouter.ai/api/v1/chat/completions"
        self.daily_limit = current_app.config.get('OPENROUTER_DAILY_LIMIT', 50)

    def _check_api_key(self) -> bool:
        """Check if API key is configured"""
        if not self.api_key:
            logging.warning("OpenRouter API key not configured")
            return False
        return True

    def _build_headers(self) -> Dict[str, str]:
        """Build headers for API requests"""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": "https://kikuyu-translation.app",
            "X-Title": "Kikuyu Translation Platform",
            "Content-Type": "application/json"
        }

    def _create_prompt_seed(self, category: Optional[str] = None) -> str:
        """Create a seed prompt for generating English sentences"""
        base_prompt = "Generate a simple, culturally appropriate English sentence for Kikuyu translation. "

        if category:
            category_prompts = {
                'greetings': "Focus on common greetings and social interactions.",
                'family': "Focus on family relationships, children, and household topics.",
                'farming': "Focus on agriculture, crops, livestock, and farming activities.",
                'health': "Focus on health, wellness, and medical topics.",
                'school': "Focus on education, learning, and school activities.",
                'weather': "Focus on weather, seasons, and natural phenomena.",
                'general': "Focus on everyday activities and common situations."
            }
            base_prompt += category_prompts.get(category, category_prompts['general'])
        else:
            base_prompt += "The sentence should be about everyday life, culture, or common activities that would be familiar to Kikuyu speakers."

        base_prompt += " Keep it simple, clear, and under 20 words. Return only the English sentence, nothing else."

        return base_prompt

    def generate_prompt(self, category: Optional[str] = None) -> Optional[str]:
        """
        Generate a single English prompt using OpenRouter API

        Args:
            category: Optional category for the prompt (greetings, family, etc.)

        Returns:
            Generated English sentence or None if failed
        """
        if not self._check_api_key():
            return None

        try:
            seed_text = self._create_prompt_seed(category)
            headers = self._build_headers()

            data = {
                "model": self.model,
                "messages": [
                    {
                        "role": "user",
                        "content": seed_text
                    }
                ],
                "temperature": 0.8,
                "max_tokens": 50,
                "top_p": 0.9
            }

            response = requests.post(
                self.base_url,
                headers=headers,
                json=data,
                timeout=30
            )

            if response.status_code == 200:
                result = response.json()

                if 'choices' in result and len(result['choices']) > 0:
                    generated_text = result['choices'][0]['message']['content'].strip()

                    # Clean up the generated text
                    generated_text = generated_text.strip('"\'')

                    # Basic validation
                    if len(generated_text) > 5 and len(generated_text.split()) <= 25:
                        logging.info(f"Generated prompt: {generated_text}")
                        return generated_text
                    else:
                        logging.warning(f"Generated text doesn't meet criteria: {generated_text}")
                        return None
                else:
                    logging.error("No choices in OpenRouter response")
                    return None
            else:
                logging.error(f"OpenRouter API error: {response.status_code} - {response.text}")
                return None

        except requests.exceptions.RequestException as e:
            logging.error(f"Request error when calling OpenRouter: {e}")
            return None
        except Exception as e:
            logging.error(f"Unexpected error in generate_prompt: {e}")
            return None

    def generate_multiple_prompts(self, count: int = 20, categories: Optional[list] = None) -> list:
        """
        Generate multiple prompts in batch

        Args:
            count: Number of prompts to generate
            categories: List of categories to use (will cycle through them)

        Returns:
            List of generated prompts with metadata
        """
        if not self._check_api_key():
            return []

        prompts = []
        default_categories = ['greetings', 'family', 'farming', 'health', 'school', 'weather', 'general']

        if not categories:
            categories = default_categories

        for i in range(count):
            # Cycle through categories
            category = categories[i % len(categories)]

            try:
                text = self.generate_prompt(category)

                if text:
                    prompt_data = {
                        'id': f"prompt_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{i+1}",
                        'text': text,
                        'category': category,
                        'date_generated': datetime.utcnow().isoformat(),
                        'usage_count': 0,
                        'status': 'active'
                    }
                    prompts.append(prompt_data)

                    # Add small delay between requests to respect rate limits
                    import time
                    time.sleep(0.5)
                else:
                    logging.warning(f"Failed to generate prompt {i+1}")

            except Exception as e:
                logging.error(f"Error generating prompt {i+1}: {e}")
                continue

        logging.info(f"Successfully generated {len(prompts)} out of {count} requested prompts")
        return prompts

    def test_connection(self) -> Dict[str, Any]:
        """
        Test the OpenRouter API connection

        Returns:
            Dictionary with test results
        """
        if not self._check_api_key():
            return {
                'success': False,
                'error': 'API key not configured'
            }

        try:
            test_prompt = self.generate_prompt('general')

            if test_prompt:
                return {
                    'success': True,
                    'message': 'OpenRouter API connection successful',
                    'sample_prompt': test_prompt
                }
            else:
                return {
                    'success': False,
                    'error': 'Failed to generate test prompt'
                }

        except Exception as e:
            return {
                'success': False,
                'error': f'Connection test failed: {str(e)}'
            }

    def generate_targeted_prompts(self, gap_analysis: Dict, count: int = 10) -> list:
        """
        Generate prompts specifically to fill identified gaps in coverage

        Args:
            gap_analysis: Analysis of coverage gaps from SmartPromptSelector
            count: Number of prompts to generate

        Returns:
            List of generated prompts targeted at filling gaps
        """
        if not self._check_api_key():
            return []

        prompts = []
        critical_gaps = gap_analysis.get('critical_gaps', [])
        underrepresented = gap_analysis.get('underrepresented_categories', [])

        # Prioritize critical gaps first
        target_categories = critical_gaps + underrepresented
        if not target_categories:
            target_categories = ['general']

        for i in range(count):
            category = target_categories[i % len(target_categories)]

            try:
                # Use specialized prompt generation for gaps
                text = self._generate_gap_filling_prompt(category, gap_analysis)

                if text:
                    prompt_data = {
                        'id': f"gap_fill_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{i+1}",
                        'text': text,
                        'category': category,
                        'source_type': 'llm',
                        'source_file': f'gap_filling_{category}',
                        'difficulty_level': self._assess_difficulty(text),
                        'date_generated': datetime.utcnow().isoformat(),
                        'quality_score': 0.8,  # LLM-generated baseline
                        'metadata': {
                            'generation_purpose': 'gap_filling',
                            'target_category': category,
                            'gap_priority': 'critical' if category in critical_gaps else 'moderate'
                        },
                        'usage_count': 0,
                        'status': 'active'
                    }
                    prompts.append(prompt_data)

                import time
                time.sleep(0.7)  # Slightly longer delay for gap filling requests

            except Exception as e:
                logging.error(f"Error generating gap-filling prompt {i+1}: {e}")
                continue

        logging.info(f"Generated {len(prompts)} gap-filling prompts")
        return prompts

    def _generate_gap_filling_prompt(self, category: str, gap_analysis: Dict) -> Optional[str]:
        """Generate prompt specifically designed to fill category gaps"""

        # Create more targeted prompts for specific gaps
        gap_specific_prompts = {
            'agriculture': "Generate a practical English sentence about farming, crops, or livestock that a Kikuyu farmer would find useful to translate.",
            'technology': "Generate a simple English sentence about modern technology or digital tools that would be relevant in a rural Kenyan context.",
            'health': "Generate a clear English sentence about health, medicine, or wellness that would be important for community health education.",
            'education': "Generate an educational English sentence about learning, school, or knowledge that would be valuable for students and teachers.",
            'business': "Generate a practical English sentence about trade, business, or economic activities relevant to local communities.",
            'culture': "Generate an English sentence about traditions, celebrations, or cultural practices that would resonate with Kikuyu cultural values.",
            'family': "Generate a warm English sentence about family relationships, children, or household life that reflects African family values.",
            'conversation': "Generate a natural English conversation phrase or greeting that would be commonly used in daily social interactions.",
            'weather': "Generate a descriptive English sentence about weather, seasons, or natural phenomena relevant to the Kenyan climate.",
            'general': "Generate a versatile English sentence about daily life that would be useful for general translation practice."
        }

        prompt_text = gap_specific_prompts.get(category, gap_specific_prompts['general'])
        prompt_text += " The sentence should be 5-20 words, culturally appropriate, and avoid complex technical terms. Return only the English sentence."

        try:
            headers = self._build_headers()
            data = {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt_text}],
                "temperature": 0.9,  # Higher creativity for gap filling
                "max_tokens": 50,
                "top_p": 0.95
            }

            response = requests.post(self.base_url, headers=headers, json=data, timeout=30)

            if response.status_code == 200:
                result = response.json()
                if 'choices' in result and len(result['choices']) > 0:
                    generated_text = result['choices'][0]['message']['content'].strip()
                    generated_text = generated_text.strip('"\'')

                    # Enhanced validation for gap-filling prompts
                    if self._validate_gap_filling_prompt(generated_text, category):
                        return generated_text

            return None

        except Exception as e:
            logging.error(f"Error in gap-filling prompt generation: {e}")
            return None

    def _validate_gap_filling_prompt(self, text: str, category: str) -> bool:
        """Enhanced validation for gap-filling prompts"""
        if not text or len(text) < 5:
            return False

        words = text.split()
        if len(words) < 3 or len(words) > 25:
            return False

        # Category-specific validation
        category_keywords = {
            'agriculture': ['farm', 'crop', 'plant', 'harvest', 'livestock', 'field', 'soil', 'seed'],
            'technology': ['computer', 'phone', 'internet', 'digital', 'app', 'website', 'online'],
            'health': ['health', 'medicine', 'doctor', 'hospital', 'sick', 'treatment', 'care'],
            'education': ['school', 'learn', 'teach', 'student', 'book', 'study', 'knowledge'],
            'family': ['family', 'mother', 'father', 'child', 'home', 'parent', 'sister', 'brother'],
            'weather': ['weather', 'rain', 'sun', 'hot', 'cold', 'season', 'wind', 'cloud']
        }

        # Check if prompt contains relevant keywords for the category
        if category in category_keywords:
            text_lower = text.lower()
            has_relevant_keyword = any(keyword in text_lower for keyword in category_keywords[category])
            if not has_relevant_keyword and category != 'general':
                logging.warning(f"Gap-filling prompt lacks relevant keywords for {category}: {text}")
                return False

        return True

    def _assess_difficulty(self, text: str) -> str:
        """Assess difficulty level of generated text"""
        words = text.split()
        word_count = len(words)
        complex_words = sum(1 for word in words if len(word) > 8)

        if word_count <= 8 and complex_words <= 1:
            return 'basic'
        elif word_count <= 15 and complex_words <= 3:
            return 'intermediate'
        else:
            return 'advanced'

    def generate_cultural_prompts(self, count: int = 5) -> list:
        """Generate culturally specific prompts for Kikuyu context"""
        cultural_themes = [
            "Generate a sentence about traditional Kikuyu ceremonies or celebrations",
            "Generate a sentence about Kikuyu agricultural practices and seasonal activities",
            "Generate a sentence about community cooperation and social values",
            "Generate a sentence about elders, wisdom, and traditional knowledge",
            "Generate a sentence about local foods, cooking, or traditional meals"
        ]

        prompts = []
        for i, theme in enumerate(cultural_themes[:count]):
            try:
                headers = self._build_headers()
                full_prompt = f"{theme}. Keep it respectful, accurate, and suitable for translation practice. 5-20 words. Return only the English sentence."

                data = {
                    "model": self.model,
                    "messages": [{"role": "user", "content": full_prompt}],
                    "temperature": 0.85,
                    "max_tokens": 50
                }

                response = requests.post(self.base_url, headers=headers, json=data, timeout=30)

                if response.status_code == 200:
                    result = response.json()
                    if 'choices' in result and len(result['choices']) > 0:
                        text = result['choices'][0]['message']['content'].strip().strip('"\'')

                        if self._validate_cultural_prompt(text):
                            prompt_data = {
                                'id': f"cultural_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{i+1}",
                                'text': text,
                                'category': 'culture',
                                'source_type': 'llm',
                                'source_file': 'cultural_generation',
                                'difficulty_level': self._assess_difficulty(text),
                                'quality_score': 0.85,  # Higher quality for cultural content
                                'metadata': {
                                    'generation_purpose': 'cultural_context',
                                    'theme': theme
                                }
                            }
                            prompts.append(prompt_data)

                import time
                time.sleep(1.0)  # Longer delay for cultural prompts

            except Exception as e:
                logging.error(f"Error generating cultural prompt {i+1}: {e}")
                continue

        return prompts

    def _validate_cultural_prompt(self, text: str) -> bool:
        """Validate cultural prompts for appropriateness"""
        if not text or len(text) < 5:
            return False

        words = text.split()
        if len(words) < 3 or len(words) > 25:
            return False

        # Check for potentially sensitive content (basic check)
        sensitive_words = ['primitive', 'backward', 'savage', 'tribal']
        text_lower = text.lower()
        if any(word in text_lower for word in sensitive_words):
            logging.warning(f"Cultural prompt contains sensitive language: {text}")
            return False

        return True

    def get_usage_statistics(self) -> Dict:
        """Get API usage statistics for monitoring"""
        from app.models import PromptCache

        cache = PromptCache.query.first()
        if not cache:
            return {
                'api_calls_today': 0,
                'daily_limit': self.daily_limit,
                'remaining_calls': self.daily_limit
            }

        remaining = max(0, self.daily_limit - cache.api_calls_today)

        return {
            'api_calls_today': cache.api_calls_today,
            'daily_limit': self.daily_limit,
            'remaining_calls': remaining,
            'last_updated': cache.last_updated.isoformat() if cache.last_updated else None
        }

    def can_make_api_call(self) -> bool:
        """Check if we can make another API call today"""
        stats = self.get_usage_statistics()
        return stats['remaining_calls'] > 0