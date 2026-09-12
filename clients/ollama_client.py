import ollama

class OllamaClient:
    def __init__(self, host='http://127.0.0.1:11434'):
        self.client = ollama.Client(host=host)

    def chat(self, model, system_prompt, user_prompt, temperature=0.7, json_output=False):
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        kwargs = {"model": model, "messages": messages, "options": {"temperature": temperature}}
        if json_output:
            kwargs["format"] = "json"

        response = self.client.chat(**kwargs)
        return response['message']['content']

    def unload_model(self, model_name):
        """Evicts the given Ollama model from VRAM."""
        try:
            self.client.chat(model=model_name, messages=[], keep_alive=0)
        except Exception:
            pass
