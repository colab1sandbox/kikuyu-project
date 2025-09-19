import json
import os
import logging
from datetime import datetime, date
from typing import Optional, Dict, List, Any
from flask import current_app
from app.services.openrouter import OpenRouterClient

class PromptCacheManager:
    """Manages the local prompt cache using prompts.json"""

    def __init__(self):
        self.cache_file = current_app.config.get('PROMPT_CACHE_FILE', 'instance/prompts.json')
        self.min_cache_size = current_app.config.get('MIN_CACHE_SIZE', 10)
        self.batch_size = current_app.config.get('PROMPT_BATCH_SIZE', 20)

    def _ensure_cache_directory(self):
        """Ensure the cache directory exists"""
        cache_dir = os.path.dirname(self.cache_file)
        if cache_dir and not os.path.exists(cache_dir):
            os.makedirs(cache_dir, exist_ok=True)

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
                        "api_calls_today": 0,
                        "api_calls_date": None
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
        return {
            "prompts": [],
            "used_prompts": [],
            "metadata": {
                "last_updated": datetime.utcnow().isoformat(),
                "last_refill": None,
                "total_generated": 0,
                "total_used": 0,
                "api_calls_today": 0,
                "api_calls_date": date.today().isoformat()
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

            # Update last_updated timestamp
            cache_data["metadata"]["last_updated"] = datetime.utcnow().isoformat()

            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, indent=2, ensure_ascii=False)

            logging.info(f"Cache saved successfully to {self.cache_file}")
            return True

        except Exception as e:
            logging.error(f"Error saving cache: {e}")
            return False

    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the cache

        Returns:
            Dictionary with cache statistics
        """
        cache = self.load_cache()

        total_prompts = len(cache["prompts"])
        used_count = len(cache["used_prompts"])
        available_count = total_prompts - used_count

        return {
            "total_prompts": total_prompts,
            "used_prompts": used_count,
            "available_prompts": available_count,
            "cache_health": "healthy" if available_count >= self.min_cache_size else "low",
            "last_updated": cache["metadata"]["last_updated"],
            "last_refill": cache["metadata"]["last_refill"],
            "api_calls_today": cache["metadata"]["api_calls_today"],
            "api_calls_date": cache["metadata"]["api_calls_date"]
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
            logging.info(f"Cache low ({len(available_prompts)} prompts), triggering refill")
            if self.refill_cache():
                cache = self.load_cache()
                available_prompts = [p for p in cache["prompts"] if p["id"] not in cache["used_prompts"]]

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
        Refill the cache with new prompts from OpenRouter

        Args:
            force: Force refill even if cache seems adequate

        Returns:
            True if successful, False otherwise
        """
        try:
            cache = self.load_cache()

            # Check if we need to refill
            available_count = len(cache["prompts"]) - len(cache["used_prompts"])

            if not force and available_count >= self.min_cache_size:
                logging.info(f"Cache refill not needed ({available_count} prompts available)")
                return True

            # Check daily API limit
            today = date.today().isoformat()
            if cache["metadata"]["api_calls_date"] != today:
                cache["metadata"]["api_calls_today"] = 0
                cache["metadata"]["api_calls_date"] = today

            daily_limit = current_app.config.get('OPENROUTER_DAILY_LIMIT', 50)
            if cache["metadata"]["api_calls_today"] >= daily_limit:
                logging.warning(f"Daily API limit reached ({daily_limit} calls)")
                return False

            # Calculate how many prompts to generate
            prompts_needed = max(self.batch_size, self.min_cache_size - available_count)
            prompts_to_generate = min(prompts_needed, daily_limit - cache["metadata"]["api_calls_today"])

            if prompts_to_generate <= 0:
                logging.warning("Cannot generate prompts due to API limits")
                return False

            logging.info(f"Generating {prompts_to_generate} new prompts")

            # Generate new prompts
            openrouter = OpenRouterClient()
            new_prompts = openrouter.generate_multiple_prompts(prompts_to_generate)

            if new_prompts:
                # Add new prompts to cache
                cache["prompts"].extend(new_prompts)
                cache["metadata"]["last_refill"] = datetime.utcnow().isoformat()
                cache["metadata"]["total_generated"] += len(new_prompts)
                cache["metadata"]["api_calls_today"] += len(new_prompts)

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

    def cleanup_cache(self, max_age_days: int = 30) -> bool:
        """
        Clean up old prompts from the cache

        Args:
            max_age_days: Maximum age of prompts to keep

        Returns:
            True if successful, False otherwise
        """
        try:
            cache = self.load_cache()
            cutoff_date = datetime.utcnow().timestamp() - (max_age_days * 24 * 60 * 60)

            initial_count = len(cache["prompts"])

            # Filter out old prompts
            cache["prompts"] = [
                p for p in cache["prompts"]
                if datetime.fromisoformat(p["date_generated"]).timestamp() > cutoff_date
            ]

            # Update used_prompts list to remove references to deleted prompts
            prompt_ids = {p["id"] for p in cache["prompts"]}
            cache["used_prompts"] = [uid for uid in cache["used_prompts"] if uid in prompt_ids]

            removed_count = initial_count - len(cache["prompts"])

            if removed_count > 0:
                logging.info(f"Cleaned up {removed_count} old prompts from cache")
                return self.save_cache(cache)
            else:
                logging.info("No old prompts to clean up")
                return True

        except Exception as e:
            logging.error(f"Error during cache cleanup: {e}")
            return False