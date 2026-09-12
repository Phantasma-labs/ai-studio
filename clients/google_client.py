from google import genai
from google.genai import types

class GoogleClient:
    def __init__(self, api_key=None):
        self.client = genai.Client(api_key=api_key) if api_key else genai.Client()

    def generate_content(self, model, prompt, system_instruction=None, temperature=0.7, json_output=False):
        config_kwargs = {"temperature": temperature}
        if json_output:
            config_kwargs["response_mime_type"] = "application/json"

        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            **config_kwargs
        )

        try:
            response = self.client.models.generate_content(
                model=model,
                contents=prompt,
                config=config
            )
            return response.text
        except Exception as e:
            # Fallback if system_instruction is not supported in this exact way
            fallback_prompt = f"SYSTEM INSTRUCTIONS:\n{system_instruction}\n\nUSER INPUT:\n{prompt}"
            response = self.client.models.generate_content(
                model=model,
                contents=fallback_prompt,
                config=types.GenerateContentConfig(**config_kwargs)
            )
            return response.text
