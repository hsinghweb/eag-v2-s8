import os
import json
import yaml
import requests
import asyncio
import time
from pathlib import Path
from google import genai
from google.api_core import exceptions as google_exceptions
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).parent.parent
MODELS_JSON = ROOT / "config" / "models.json"
PROFILE_YAML = ROOT / "config" / "profiles.yaml"

class ModelManager:
    def __init__(self):
        self.config = json.loads(MODELS_JSON.read_text())
        self.profile = yaml.safe_load(PROFILE_YAML.read_text())

        self.text_model_key = self.profile["llm"]["text_generation"]
        self.model_info = self.config["models"][self.text_model_key]
        self.model_type = self.model_info["type"]

        # ✅ Gemini initialization (your style)
        if self.model_type == "gemini":
            api_key = os.getenv("GEMINI_API_KEY")
            self.client = genai.Client(api_key=api_key)

    async def generate_text(self, prompt: str, max_retries: int = 3) -> str:
        if self.model_type == "gemini":
            return await self._gemini_generate_with_retry(prompt, max_retries)

        elif self.model_type == "ollama":
            return self._ollama_generate(prompt)

        raise NotImplementedError(f"Unsupported model type: {self.model_type}")

    async def _gemini_generate_with_retry(self, prompt: str, max_retries: int = 3) -> str:
        """Generate text with retry logic for rate limits"""
        for attempt in range(max_retries):
            try:
                return self._gemini_generate(prompt)
            except Exception as e:
                error_str = str(e)
                error_repr = repr(e)
                
                # Check if it's a 429 rate limit error (check both str and repr)
                is_rate_limit = (
                    "429" in error_str or "429" in error_repr or
                    "RESOURCE_EXHAUSTED" in error_str or "RESOURCE_EXHAUSTED" in error_repr or
                    "quota" in error_str.lower() or "quota" in error_repr.lower()
                )
                
                if is_rate_limit:
                    # Try to extract retry delay from error
                    retry_delay = 60  # Default 60 seconds
                    try:
                        # Parse error to find retry delay (check both str and repr)
                        combined_error = error_str + " " + error_repr
                        if "Please retry in" in combined_error or "retryDelay" in combined_error:
                            import re
                            # Try to find delay in format "Please retry in Xs" or "retryDelay": "Xs"
                            delay_match = re.search(r'(?:Please retry in|retryDelay["\']?\s*:\s*["\']?)([\d.]+)s?', combined_error, re.IGNORECASE)
                            if delay_match:
                                retry_delay = float(delay_match.group(1)) + 10  # Add 10 seconds buffer
                            else:
                                # Try to find in error details dict format
                                delay_match = re.search(r'"retryDelay"\s*:\s*"?([\d.]+)s?', combined_error, re.IGNORECASE)
                                if delay_match:
                                    retry_delay = float(delay_match.group(1)) + 10
                    except Exception as parse_error:
                        print(f"[model] ⚠️ Could not parse retry delay, using default {retry_delay}s")
                    
                    if attempt < max_retries - 1:
                        print(f"[model] ⚠️ Rate limit hit (429). Waiting {retry_delay:.1f}s before retry {attempt + 2}/{max_retries}...")
                        await asyncio.sleep(retry_delay)
                        continue
                    else:
                        raise Exception(f"Rate limit exceeded after {max_retries} attempts. Please wait and try again later. Free tier limit: 200 requests/day. Error: {error_str[:200]}")
                
                # For other errors, raise immediately
                raise

    def _gemini_generate(self, prompt: str) -> str:
        try:
            response = self.client.models.generate_content(
                model=self.model_info["model"],
                contents=prompt
            )

            # ✅ Safely extract response text
            try:
                return response.text.strip()
            except AttributeError:
                try:
                    return response.candidates[0].content.parts[0].text.strip()
                except Exception:
                    return str(response)
        except Exception as e:
            # Check if error contains rate limit info (sometimes in nested dict)
            error_str = str(e)
            error_repr = repr(e)
            
            # If error is a dict-like structure, check for rate limit indicators
            if isinstance(e, dict) or (hasattr(e, '__dict__') and hasattr(e, 'error')):
                try:
                    error_dict = e if isinstance(e, dict) else e.__dict__
                    if 'error' in error_dict:
                        error_info = error_dict['error']
                        if isinstance(error_info, dict):
                            if error_info.get('code') == 429 or 'RESOURCE_EXHAUSTED' in str(error_info.get('status', '')):
                                # Extract retry delay from error details if available
                                details = error_info.get('details', [])
                                retry_delay = None
                                for detail in details:
                                    if isinstance(detail, dict) and 'retryDelay' in detail:
                                        retry_delay = detail.get('retryDelay')
                                        break
                                raise Exception(f"429 RESOURCE_EXHAUSTED: {error_info.get('message', 'Rate limit exceeded')}. Retry delay: {retry_delay if retry_delay else 'unknown'}")
                except:
                    pass
            
            # Re-raise with full error info
            raise Exception(f"Gemini API error: {error_str}")

    def _ollama_generate(self, prompt: str) -> str:
        response = requests.post(
            self.model_info["url"]["generate"],
            json={"model": self.model_info["model"], "prompt": prompt, "stream": False}
        )
        response.raise_for_status()
        return response.json()["response"].strip()
