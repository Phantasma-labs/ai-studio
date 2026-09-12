import os
import json
from clients.google_client import GoogleClient
from clients.ollama_client import OllamaClient
from clients.comfy_client import ComfyClient

def call_llm(system_prompt, user_prompt, engine_mode="Cloud", model_name="gemini-3.5-flash", temperature=0.7, json_output=False, api_key=None):
    if engine_mode == "Cloud":
        client = GoogleClient(api_key)
        return client.generate_content(model_name, user_prompt, system_prompt, temperature, json_output)
    else:
        client = OllamaClient()
        return client.chat(model_name, system_prompt, user_prompt, temperature, json_output)

def unload_ollama_model(model_name: str):
    """
    Evicts the given Ollama model from VRAM.
    """
    client = OllamaClient()
    client.unload_model(model_name)

def load_prompt(filename):
    path = os.path.join(os.path.dirname(__file__), "knowledge", filename)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

def describe_image(image_bytes, engine_mode="Local", api_key=None, mime_type="image/jpeg", prompt="Describe this image in detail to use as a creative concept. Output ONLY the raw descriptive caption. Do not include titles, labels, meta-commentary, or notes like 'Ideal for a storyboard'.", model_name="qwen3-vl:8b"):
    if engine_mode == "Cloud":
        from google.genai import types
        client = GoogleClient(api_key)
        try:
            response = client.client.models.generate_content(
                model='gemini-3.5-flash',
                contents=[
                    types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                    prompt
                ]
            )
            return response.text
        except Exception as e:
            print(f"Gemini Image Describing Error: {e}")
            raise e
    else:
        try:
            client = OllamaClient()
            messages = [
                {"role": "user", "content": prompt, "images": [image_bytes]}
            ]
            response = client.client.chat(model=model_name, messages=messages)
            return response['message']['content']
        except Exception as e:
            print(f"Ollama Image Describing Error: {e}")
            raise e

def run_phase_1(concept, engine_mode="Cloud", model_name="gemini-3.5-flash", api_key=None):
    system_rules = load_prompt("story_frameworks.md")
    prompt = (
        f"Analyze this user concept: {concept}\n\n"
        "If the concept is vague or minimalist, act as a 'Creative Engine' and invent a narrative. "
        "If specific, preserving details. Output format: sh 01, sh 02, etc. (NOT panel 01)."
    )
    story_arc = call_llm(system_rules, prompt, engine_mode, model_name, 0.8, api_key=api_key)

    screenplay_rules = load_prompt("screenplay_standards.md")
    screenplay = call_llm(screenplay_rules, f"Convert the following story arc into a screenplay, use sh 01, sh 02 sequence formatting:\n{story_arc}", engine_mode, model_name, 0.8, api_key=api_key)

    art_rules = load_prompt("art_consultant.md")
    art_prompt = f"Review this screenplay:\n{screenplay}\n\nProvide Art Direction suggestions (3 options)."
    art_suggestions = call_llm(art_rules, art_prompt, engine_mode, model_name, 0.8, api_key=api_key)

    return story_arc, screenplay, art_suggestions

def run_phase_1_5(screenplay, art_prefs, engine_mode="Cloud", model_name="gemini-3.5-flash", api_key=None):
    cam_rules = load_prompt("camera_consultant.md")
    art_instructions = f"Chosen Art Direction: {art_prefs}" if art_prefs else "Chosen Art Direction: None provided."
    cam_prompt = f"Review this screenplay:\n{screenplay}\n\n{art_instructions}\nProvide Cinematography suggestions."
    return call_llm(cam_rules, cam_prompt, engine_mode, model_name, 0.8, api_key=api_key)

def run_phase_2(screenplay, art_prefs, camera_prefs, engine_mode="Cloud", model_name="gemini-3.5-flash", api_key=None):
    fallback_instruction = "Choose the most cinematic and professional path."
    art_instructions = f"User Art Preferences: {art_prefs}" if art_prefs else f"User Art Preferences: {fallback_instruction}"
    camera_instructions = f"User Camera Preferences: {camera_prefs}" if camera_prefs else f"User Camera Preferences: {fallback_instruction}"

    art_directed = call_llm(load_prompt("art_direction.md"), f"Screenplay:\n{screenplay}\n\n{art_instructions}", engine_mode, model_name, 0.8, api_key=api_key)
    camera_directed = call_llm(load_prompt("camera_motion.md"), f"Art Directed Screenplay:\n{art_directed}\n\n{camera_instructions}", engine_mode, model_name, 0.8, api_key=api_key)

    render_rules = load_prompt("render_artist_style.md")
    render_prompt = (
        f"You have received the enriched screenplay data below. Act as a Render Artist and produce the final prompts.\n\n"
        f"ENRICHED SCREENPLAY:\n{camera_directed}\n\n"
        f"INSTRUCTIONS: Using your guide, produce one output block per scene (sh 01 through sh 06). "
        f"Output as a JSON array of objects with 'scene_label', 't2i', and 'i2v' keys."
    )
    final_prompts = call_llm(render_rules, render_prompt, engine_mode, model_name, 0.7, api_key=api_key, json_output=True)

    storyboard_system = (
        "You are a storyboard prompt engineer. Your only job is to convert 6 scene descriptions "
        "into a single Text-to-Image prompt that renders a 6-panel storyboard grid.\n\n"
        "ABSOLUTE RULES:\n"
        "1. The output image MUST be a 3-column × 2-row grid (3 panels top row, 3 panels bottom row).\n"
        "2. There MUST be exactly 6 panels. Never fewer, never more.\n"
        "3. Each panel MUST correspond to exactly one scene in sequence: "
        "Panel 1 = sh 01, Panel 2 = sh 02, Panel 3 = sh 03, Panel 4 = sh 04, Panel 5 = sh 05, Panel 6 = sh 06.\n"
        "4. Each panel must be visually distinct — different subject position, lighting, or framing from the others.\n"
        "5. Output ONLY the raw prompt text. No titles, no labels, no explanations, no JSON."
    )
    storyboard_user = (
        f"Convert the 6 scenes below into ONE storyboard prompt.\n\n"
        f"STEP 1 — Extract the core visual essence of each scene in one sentence each:\n"
        f"Panel 1 (sh 01): <essence>\n"
        f"Panel 2 (sh 02): <essence>\n"
        f"Panel 3 (sh 03): <essence>\n"
        f"Panel 4 (sh 04): <essence>\n"
        f"Panel 5 (sh 05): <essence>\n"
        f"Panel 6 (sh 06): <essence>\n\n"
        f"STEP 2 — Write ONE unified Text-to-Image prompt that renders all 6 panels in a "
        f"3-column × 2-row grid layout at 16:9 aspect ratio. "
        f"The prompt must explicitly reference each of the 6 panels in order, "
        f"describe their visual content, and establish the grid layout. "
        f"Include cinematic quality enhancers. Output ONLY the final prompt text.\n\n"
        f"SCENES:\n{final_prompts}"
    )
    storyboard_prompt = call_llm(
        storyboard_system, storyboard_user,
        engine_mode, model_name, 0.1, api_key=api_key
    )

    return final_prompts, storyboard_prompt

def run_product_shot_mode(concept, engine_mode="Cloud", model_name="gemini-3.5-flash", api_key=None):
    system_rules = load_prompt("product_shot_rules.md")
    prompt = (
        f"Process this product shot concept: {concept}\n\n"
        f"Run your full 4-stage synthesis pipeline, then output the final result "
        f"as a JSON array containing one object with 'scene_label', 't2i', and 'i2v' keys. "
        f"No JSON preamble. Output only the JSON."
    )
    return call_llm(system_rules, prompt, engine_mode, model_name, temperature=0.6, api_key=api_key, json_output=True)

def generate_image_comfyui(prompt):
    client = ComfyClient()
    return client.generate_image(prompt)
