import os
import json
import urllib.request
import urllib.error
import urllib.parse
import time
import random

class ComfyClient:
    def __init__(self, server_address="127.0.0.1:8188"):
        self.server_address = server_address

    def check_server(self):
        try:
            req = urllib.request.Request(f"http://{self.server_address}/system_stats")
            with urllib.request.urlopen(req) as response:
                return True
        except urllib.error.URLError:
            return False

    def generate_image(self, prompt, workflow_filename="ZimageRender.json"):
        if not self.check_server():
            raise ConnectionError("ComfyUI is not running. Please start ComfyUI manually and try again.")

        workflow_path = os.path.join(os.path.dirname(__file__), "..", "comfyui", workflow_filename)
        with open(workflow_path, "r", encoding="utf-8") as f:
            workflow = json.load(f)

        if "5" in workflow and "inputs" in workflow["5"]:
            workflow["5"]["inputs"]["text"] = prompt

        if "4" in workflow and "inputs" in workflow["4"]:
            workflow["4"]["inputs"]["seed"] = random.randint(1, 999999999999999)

        data = json.dumps({"prompt": workflow}).encode('utf-8')
        req = urllib.request.Request(f"http://{self.server_address}/prompt", data=data)
        req.add_header("Content-Type", "application/json")

        try:
            with urllib.request.urlopen(req) as response:
                result = json.loads(response.read())
                prompt_id = result.get('prompt_id')
        except Exception as e:
            raise Exception(f"Failed to queue prompt in ComfyUI: {e}")

        max_retries = 600
        for _ in range(max_retries):
            time.sleep(1)
            try:
                hist_req = urllib.request.Request(f"http://{self.server_address}/history/{prompt_id}")
                with urllib.request.urlopen(hist_req) as hist_resp:
                    history = json.loads(hist_resp.read())
                    if prompt_id in history:
                        node_outputs = history[prompt_id].get('outputs', {})
                        for node_id, output in node_outputs.items():
                            if 'images' in output:
                                image_info = output['images'][0]
                                filename = image_info['filename']
                                subfolder = image_info['subfolder']
                                folder_type = image_info['type']
                                view_url = f"http://{self.server_address}/view?filename={urllib.parse.quote(filename)}&subfolder={urllib.parse.quote(subfolder)}&type={folder_type}"
                                img_req = urllib.request.Request(view_url)
                                with urllib.request.urlopen(img_req) as img_resp:
                                    return img_resp.read()
            except Exception:
                pass

        raise TimeoutError("ComfyUI took too long to generate the image.")
