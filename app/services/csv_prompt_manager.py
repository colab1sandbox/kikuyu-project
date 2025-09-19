import csv
import json
import os
import logging
import random
import hashlib
from datetime import datetime, date
from typing import Optional, Dict, List, Any
from flask import current_app

class CSVPromptManager:
    """Manages prompts from a CSV dataset instead of OpenRouter API"""

    def __init__(self):
        self.cache_file = current_app.config.get('PROMPT_CACHE_FILE', 'instance/prompts.json')
        self.csv_file = current_app.config.get('CSV_DATASET_FILE', 'data/englishswahli_dataset.csv')
        self.min_cache_size = current_app.config.get('MIN_CACHE_SIZE', 50)
        self.batch_size = current_app.config.get('PROMPT_BATCH_SIZE', 100)
        self._csv_rows = None
        self._used_csv_indices = set()

    def _ensure_cache_directory(self):
        """Ensure the cache directory exists"""
        cache_dir = os.path.dirname(self.cache_file)
        if cache_dir and not os.path.exists(cache_dir):
            os.makedirs(cache_dir, exist_ok=True)

    def _load_csv_data(self) -> List[str]:
        """Load English sentences from CSV file"""
        if self._csv_rows is None:
            try:
                self._csv_rows = []
                with open(self.csv_file, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        english_text = row.get('English', '').strip()
                        if english_text and len(english_text) > 10:  # Filter out very short sentences
                            self._csv_rows.append(english_text)

                logging.info(f"Loaded {len(self._csv_rows)} English sentences from CSV")

            except Exception as e:
                logging.error(f"Error loading CSV data: {e}")
                self._csv_rows = []

        return self._csv_rows

    def _generate_prompt_id(self, text: str) -> str:
        """Generate a unique ID for a prompt based on its text"""
        return hashlib.md5(text.encode('utf-8')).hexdigest()[:12]

    def _create_prompt_object(self, english_text: str, csv_index: int) -> Dict[str, Any]:
        """Create a prompt object from English text"""
        return {
            "id": self._generate_prompt_id(english_text),
            "text": english_text,
            "category": "csv_dataset",
            "date_generated": datetime.utcnow().isoformat(),
            "usage_count": 0,
            "csv_index": csv_index,
            "source": "csv_dataset"
        }

    def load_cache(self) -> Dict[str, Any]:
        """
        Load cache data from prompts.json

        Returns:
            Dictionary containing cache data with default structure if file doesn't exist
        """
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                # Ensure all required keys exist
                default_structure = {
                    "prompts": [],
                    "used_prompts": [],
                    "metadata": {
                        "last_updated": None,
                        "last_refill": None,
                        "total_generated": 0,
                        "total_used": 0,
                        "csv_file": self.csv_file,
                        "csv_total_rows": 0,
                        "csv_used_indices": []
                    }
                }

                # Merge with defaults
                for key, default_value in default_structure.items():
                    if key not in data:
                        data[key] = default_value
                    elif key == "metadata":
                        for meta_key, meta_default in default_value.items():
                            if meta_key not in data[key]:
                                data[key][meta_key] = meta_default

                # Load used CSV indices
                self._used_csv_indices = set(data["metadata"].get("csv_used_indices", []))

                return data
            else:
                logging.info("Cache file doesn't exist, creating default structure")
                return self._create_default_cache()

        except json.JSONDecodeError as e:
            logging.error(f"Error parsing cache file: {e}")
            return self._create_default_cache()
        except Exception as e:
            logging.error(f"Error loading cache: {e}")
            return self._create_default_cache()

    def _create_default_cache(self) -> Dict[str, Any]:
        """Create default cache structure"""
        csv_data = self._load_csv_data()
        return {
            "prompts": [],
            "used_prompts": [],
            "metadata": {
                "last_updated": datetime.utcnow().isoformat(),
                "last_refill": None,
                "total_generated": 0,
                "total_used": 0,
                "csv_file": self.csv_file,
                "csv_total_rows": len(csv_data),
                "csv_used_indices": []
            }
        }

    def save_cache(self, cache_data: Dict[str, Any]) -> bool:
        """
        Save cache data to prompts.json

        Args:
            cache_data: Cache data to save

        Returns:
            True if successful, False otherwise
        """
        try:
            self._ensure_cache_directory()

            # Update metadata
            cache_data["metadata"]["last_updated"] = datetime.utcnow().isoformat()
            cache_data["metadata"]["csv_used_indices"] = list(self._used_csv_indices)

            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, indent=2, ensure_ascii=False)

            logging.info(f"Cache saved successfully to {self.cache_file}")
            return True

        except Exception as e:
            logging.error(f"Error saving cache: {e}")
            return False

    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the cache and CSV dataset

        Returns:
            Dictionary with cache statistics
        """
        cache = self.load_cache()
        csv_data = self._load_csv_data()

        total_prompts = len(cache["prompts"])
        used_count = len(cache["used_prompts"])
        available_count = total_prompts - used_count
        csv_total = len(csv_data)
        csv_used = len(self._used_csv_indices)
        csv_remaining = csv_total - csv_used

        return {
            "total_prompts": total_prompts,
            "used_prompts": used_count,
            "available_prompts": available_count,
            "cache_health": "healthy" if available_count >= self.min_cache_size else "low",
            "last_updated": cache["metadata"]["last_updated"],
            "last_refill": cache["metadata"]["last_refill"],
            "csv_total_sentences": csv_total,
            "csv_used_sentences": csv_used,
            "csv_remaining_sentences": csv_remaining,
            "csv_usage_percentage": round((csv_used / csv_total * 100), 2) if csv_total > 0 else 0
        }

    def get_next_prompt(self, user_session_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the next available prompt for a user

        Args:
            user_session_id: User's session ID for tracking

        Returns:
            Prompt dictionary or None if no prompts available
        """
        cache = self.load_cache()

        # Check if cache needs refilling
        available_prompts = [p for p in cache["prompts"] if p["id"] not in cache["used_prompts"]]

        if len(available_prompts) < self.min_cache_size:
            logging.info(f"🔄 AUTO-REFILL: Cache low ({len(available_prompts)}/{self.min_cache_size} prompts), triggering automatic refill")
            refill_success = self.refill_cache()
            if refill_success:
                cache = self.load_cache()
                available_prompts = [p for p in cache["prompts"] if p["id"] not in cache["used_prompts"]]
                logging.info(f"✅ AUTO-REFILL: Successfully refilled cache. Now have {len(available_prompts)} available prompts")
            else:
                logging.error(f"❌ AUTO-REFILL: Failed to refill cache automatically")

        if not available_prompts:
            logging.warning("No available prompts in cache")
            return None

        # Get the first available prompt
        prompt = available_prompts[0].copy()

        # Mark prompt as used
        cache["used_prompts"].append(prompt["id"])
        cache["metadata"]["total_used"] += 1

        # Update usage count for the prompt
        for p in cache["prompts"]:
            if p["id"] == prompt["id"]:
                p["usage_count"] += 1
                break

        # Save updated cache
        self.save_cache(cache)

        logging.info(f"Served prompt {prompt['id']} to user {user_session_id}")
        return prompt

    def refill_cache(self, force: bool = False) -> bool:
        """
        Refill the cache with new prompts from CSV dataset

        Args:
            force: Force refill even if cache seems adequate

        Returns:
            True if successful, False otherwise
        """
        try:
            cache = self.load_cache()
            csv_data = self._load_csv_data()

            if not csv_data:
                logging.error("No CSV data available for refilling cache")
                return False

            # Check if we need to refill
            available_count = len(cache["prompts"]) - len(cache["used_prompts"])

            if not force and available_count >= self.min_cache_size:
                logging.info(f"Cache refill not needed ({available_count} prompts available)")
                return True

            # Calculate how many prompts to generate
            prompts_needed = max(self.batch_size, self.min_cache_size - available_count)

            # Get unused CSV indices
            total_csv_indices = set(range(len(csv_data)))
            available_csv_indices = total_csv_indices - self._used_csv_indices

            if not available_csv_indices:
                logging.warning("All CSV sentences have been used!")
                return False

            # Select random unused indices
            indices_to_use = random.sample(
                list(available_csv_indices),
                min(prompts_needed, len(available_csv_indices))
            )

            logging.info(f"Generating {len(indices_to_use)} new prompts from CSV")

            # Create new prompt objects
            new_prompts = []
            for idx in indices_to_use:
                english_text = csv_data[idx]
                prompt_obj = self._create_prompt_object(english_text, idx)
                new_prompts.append(prompt_obj)
                self._used_csv_indices.add(idx)

            if new_prompts:
                # Add new prompts to cache
                cache["prompts"].extend(new_prompts)
                cache["metadata"]["last_refill"] = datetime.utcnow().isoformat()
                cache["metadata"]["total_generated"] += len(new_prompts)

                # Save updated cache
                if self.save_cache(cache):
                    logging.info(f"Successfully added {len(new_prompts)} prompts to cache")
                    return True
                else:
                    logging.error("Failed to save cache after refill")
                    return False
            else:
                logging.error("Failed to generate any new prompts")
                return False

        except Exception as e:
            logging.error(f"Error during cache refill: {e}")
            return False

    def mark_prompt_as_used(self, prompt_id: str) -> bool:
        """
        Mark a specific prompt as used

        Args:
            prompt_id: ID of the prompt to mark as used

        Returns:
            True if successful, False otherwise
        """
        try:
            cache = self.load_cache()

            if prompt_id not in cache["used_prompts"]:
                cache["used_prompts"].append(prompt_id)
                cache["metadata"]["total_used"] += 1

                # Update usage count
                for prompt in cache["prompts"]:
                    if prompt["id"] == prompt_id:
                        prompt["usage_count"] += 1
                        break

                return self.save_cache(cache)
            else:
                logging.warning(f"Prompt {prompt_id} already marked as used")
                return True

        except Exception as e:
            logging.error(f"Error marking prompt as used: {e}")
            return False

    def return_prompt_to_pool(self, prompt_id: str) -> bool:
        """
        Return a prompt back to the available pool (unmark as used)

        Args:
            prompt_id: ID of the prompt to return to pool

        Returns:
            True if successful, False otherwise
        """
        try:
            cache = self.load_cache()

            if prompt_id in cache["used_prompts"]:
                cache["used_prompts"].remove(prompt_id)
                cache["metadata"]["total_used"] = max(0, cache["metadata"]["total_used"] - 1)

                # Decrease usage count
                for prompt in cache["prompts"]:
                    if prompt["id"] == prompt_id:
                        prompt["usage_count"] = max(0, prompt["usage_count"] - 1)
                        break

                logging.info(f"Returned prompt {prompt_id} to available pool")
                return self.save_cache(cache)
            else:
                logging.warning(f"Prompt {prompt_id} was not marked as used")
                return True

        except Exception as e:
            logging.error(f"Error returning prompt to pool: {e}")
            return False

    def reset_cache(self) -> bool:
        """
        Reset the cache (clear all used prompts)

        Returns:
            True if successful, False otherwise
        """
        try:
            cache = self.load_cache()
            cache["used_prompts"] = []
            cache["metadata"]["total_used"] = 0

            # Reset usage counts
            for prompt in cache["prompts"]:
                prompt["usage_count"] = 0

            return self.save_cache(cache)

        except Exception as e:
            logging.error(f"Error resetting cache: {e}")
            return False

    def get_dataset_info(self) -> Dict[str, Any]:
        """
        Get information about the CSV dataset

        Returns:
            Dictionary with dataset information
        """
        csv_data = self._load_csv_data()

        return {
            "csv_file": self.csv_file,
            "total_sentences": len(csv_data),
            "used_sentences": len(self._used_csv_indices),
            "remaining_sentences": len(csv_data) - len(self._used_csv_indices),
            "file_exists": os.path.exists(self.csv_file),
            "sample_sentences": csv_data[:5] if csv_data else []
        }