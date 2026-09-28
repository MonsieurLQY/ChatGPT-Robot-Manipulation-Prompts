# import openai  # legacy OpenAI-compatible path, kept commented for rollback
# import base64  # only used by the legacy base64 data-URL image path
import tiktoken
import json
import os
import re
import argparse
import time
import urllib.error
import urllib.request
from pathlib import Path

from google import genai
from google.genai import types
from google.oauth2 import service_account


# Legacy OpenAI-compatible (GigaToken / Azure) configuration, kept commented
# so the previous backend can be revived for comparison.
# DEFAULT_GIGATOKEN_KEY_PATH = (
#     Path.home() / ".config" / "robopara" / "gigatoken-key.txt"
# )
# DEFAULT_GIGATOKEN_BASE_URL = "https://sub2api.gigaapi.cc/v1"
# DEFAULT_VLM_MODEL = "gpt-5.4"

DEFAULT_VERTEX_SERVICE_ACCOUNT_PATH = Path(
    "/home/lqy/.config/robopara/p-150gk23k-718446bc2ebd.json"
)
DEFAULT_VERTEX_PROJECT = "p-150gk23k"
DEFAULT_VERTEX_LOCATION = "global"
DEFAULT_VLM_MODEL = "gemini-3.7-flash"
VERTEX_SCOPES = ("https://www.googleapis.com/auth/cloud-platform",)

SUPPORTED_IMAGE_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}

# RoboPARA one-shot bridge (scripts/serve_desktop_cleanup_chatgpt_prompt.py
# in RoboPARA-2.0): GET the initial frame once, POST the accepted plan once.
ROBOPARA_PROTOCOL = 'robopara.chatgpt_prompt.v1'
ROBOPARA_TIMEOUT_S = 30

enc = tiktoken.get_encoding("cl100k_base")
# Only the (commented) Azure backend reads secrets.json.
# with open('../../secrets.json') as f:
#     credentials = json.load(f)

dir_system = './system'
dir_prompt = './prompt'
dir_query = './query'
prompt_load_order = ['prompt_role',
                     'prompt_function',
                     'prompt_environment',
                     'prompt_output_format',
                     'prompt_example']

# (legacy) azure openai api version: use '2022-12-01' for a 0301 version,
# otherwise '2023-05-15'


class ChatGPT:
    # VALID_API_VERSIONS = ['2022-12-01', '2023-05-15']

    def __init__(
            self,
            prompt_load_order,
            vertex_credentials_path=None,
            vertex_model=None,
            vertex_project=None,
            vertex_location=None,
            credentials=None):
        # Legacy OpenAI-compatible backend selection, kept for rollback:
        # self.use_azure = use_azure
        # if self.use_azure:
        #     openai.api_key = credentials["azureopenai"]["AZURE_OPENAI_KEY"]
        #     openai.api_base = credentials["azureopenai"]["AZURE_OPENAI_ENDPOINT"]
        #     openai.api_type = 'azure'
        #     if api_version not in self.VALID_API_VERSIONS:
        #         raise ValueError(
        #             f'api_version must be one of {self.VALID_API_VERSIONS}')
        #     openai.api_version = api_version
        # else:
        #     self._configure_gigatoken(
        #         api_path=gigatoken_api_path,
        #         base_url=gigatoken_base_url,
        #         model=gigatoken_model)
        self._configure_vertex(
            credentials_path=vertex_credentials_path,
            model=vertex_model,
            project=vertex_project,
            location=vertex_location)
        # Only the commented-out Azure backend reads this.
        self.credentials = credentials
        self.messages = []
        self.max_token_length = 8000
        self.max_completion_length = 2000
        self.last_response = None
        self.query = ''
        self.instruction = ''
        # load prompt file
        fp_system = os.path.join(dir_system, 'system.txt')
        with open(fp_system) as f:
            data = f.read()
        self.system_message = {"role": "system", "content": data}

        # load prompt file
        for prompt_name in prompt_load_order:
            fp_prompt = os.path.join(dir_prompt, prompt_name + '.txt')
            with open(fp_prompt) as f:
                data = f.read()
            data_spilit = re.split(r'\[user\]\n|\[assistant\]\n', data)
            data_spilit = [item for item in data_spilit if len(item) != 0]
            # it start with user and ends with system
            assert len(data_spilit) % 2 == 0
            for i, item in enumerate(data_spilit):
                if i % 2 == 0:
                    self.messages.append({"sender": "user", "text": item})
                else:
                    self.messages.append({"sender": "assistant", "text": item})
        fp_query = os.path.join(dir_query, 'query.txt')
        with open(fp_query) as f:
            self.query = f.read()

    # =====================================================================
    # Legacy GigaToken / OpenAI-compatible credential resolution, kept
    # commented out. The live Vertex AI implementation follows below.
    # =====================================================================
    # def _configure_gigatoken(self, api_path=None, base_url=None, model=None):
    #     self.model = model or os.getenv("GIGATOKEN_MODEL") or DEFAULT_VLM_MODEL
    #
    #     configured_base_url = (
    #         base_url
    #         or os.getenv("GIGATOKEN_BASE_URL")
    #         or DEFAULT_GIGATOKEN_BASE_URL
    #     )
    #     if not configured_base_url:
    #         raise ValueError(
    #             "Gigatoken base URL is required. Pass gigatoken_base_url or "
    #             "set GIGATOKEN_BASE_URL.")
    #     self.base_url = configured_base_url.strip().rstrip("/")
    #     if not self.base_url.startswith(("https://", "http://")):
    #         raise ValueError(
    #             "Gigatoken base URL must start with http:// or https://")
    #
    #     env_api_key = os.getenv("GIGATOKEN_API_KEY", "").strip()
    #     configured_key_path = (
    #         api_path
    #         or os.getenv("GIGATOKEN_API_KEY_PATH")
    #         or DEFAULT_GIGATOKEN_KEY_PATH
    #     )
    #     self.api_key_path = Path(configured_key_path).expanduser()
    #
    #     if env_api_key:
    #         self.api_key = env_api_key
    #     else:
    #         try:
    #             self.api_key = self.api_key_path.read_text(
    #                 encoding="utf-8").strip()
    #         except FileNotFoundError as exc:
    #             raise FileNotFoundError(
    #                 f"Gigatoken API key file not found: {self.api_key_path}. "
    #                 "Create it or set GIGATOKEN_API_KEY.") from exc
    #         except OSError as exc:
    #             raise OSError(
    #                 "Error reading Gigatoken API key file "
    #                 f"{self.api_key_path}: {exc}") from exc
    #
    #     if not self.api_key:
    #         raise ValueError("Gigatoken API key is empty")
    #
    #     openai.api_type = "open_ai"
    #     openai.api_base = self.base_url
    #     openai.api_key = self.api_key
    #     openai.organization = None

    def _configure_vertex(
            self,
            credentials_path=None,
            model=None,
            project=None,
            location=None):
        """Build a service-account Vertex AI Gemini client.

        Explicit arguments override environment variables, which in turn
        override the project defaults.
        """
        self.model = model or os.getenv("VERTEX_MODEL") or DEFAULT_VLM_MODEL
        self.project = (
            project
            or os.getenv("GOOGLE_CLOUD_PROJECT")
            or DEFAULT_VERTEX_PROJECT
        )
        self.location = (
            location
            or os.getenv("GOOGLE_CLOUD_LOCATION")
            or DEFAULT_VERTEX_LOCATION
        )

        configured_credentials_path = (
            credentials_path
            or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
            or DEFAULT_VERTEX_SERVICE_ACCOUNT_PATH
        )
        self.credentials_path = Path(configured_credentials_path).expanduser()

        try:
            vertex_credentials = (
                service_account.Credentials.from_service_account_file(
                    self.credentials_path,
                    scopes=VERTEX_SCOPES))
        except FileNotFoundError as exc:
            raise FileNotFoundError(
                "Vertex AI service-account file not found: "
                f"{self.credentials_path}. Pass vertex_credentials_path or "
                "set GOOGLE_APPLICATION_CREDENTIALS.") from exc
        except (OSError, ValueError) as exc:
            raise ValueError(
                "Unable to load Vertex AI service-account credentials from "
                f"{self.credentials_path}: {exc}") from exc

        self.client = genai.Client(
            vertexai=True,
            project=self.project,
            location=self.location,
            credentials=vertex_credentials)

    def get_text_content(self, content):
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return ''.join(
                item.get('text', '')
                for item in content
                if isinstance(item, dict) and item.get('type') == 'text')
        return ''

    def to_parts(self, content):
        """Turn one stored message body into a list of Gemini parts."""
        if isinstance(content, str):
            return [types.Part.from_text(text=content)]
        parts = []
        for item in content:
            if item.get('type') == 'text':
                parts.append(types.Part.from_text(text=item['text']))
            elif item.get('type') == 'image':
                parts.append(
                    types.Part.from_bytes(
                        data=item['data'],
                        mime_type=item['mime_type']))
        return parts

    def create_prompt(self):
        # Legacy ChatML prompt used by the azure '2022-12-01' backend:
        # if self.use_azure and openai.api_version == '2022-12-01':
        #     prompt = "<|im_start|>system\n"
        #     prompt += self.system_message["content"]
        #     prompt += "\n<|im_end|>\n"
        #     for message in self.messages:
        #         prompt += f"\n<|im_start|>{message['sender']}\n{message['text']}\n<|im_end|>"
        #     prompt += "\n<|im_start|>assistant\n"
        #     ...
        # The system message is no longer part of the turn list; it is passed
        # to Gemini through GenerateContentConfig(system_instruction=...).
        prompt_content = self.system_message["content"]
        for message in self.messages:
            prompt_content += self.get_text_content(message['text'])
        print('prompt length: ' + str(len(enc.encode(prompt_content))))
        if len(enc.encode(prompt_content)) > self.max_token_length - \
                self.max_completion_length:
            print('prompt too long. truncated.')
            # truncate the prompt by removing the oldest two messages
            self.messages = self.messages[2:]
            return self.create_prompt()
        contents = []
        for message in self.messages:
            # Gemini names the assistant role 'model'.
            role = 'model' if message['sender'] == 'assistant' else 'user'
            contents.append(
                types.Content(
                    role=role,
                    parts=self.to_parts(message['text'])))
        return contents

    def extract_json_part(self, text):
        text = text.strip()
        fenced_json = re.search(
            r'```(?:json|python)?\s*(.*?)\s*```',
            text,
            flags=re.DOTALL | re.IGNORECASE)
        if fenced_json:
            return fenced_json.group(1).strip()

        json_start = text.find('{')
        json_end = text.rfind('}')
        if json_start != -1 and json_end > json_start:
            return text[json_start:json_end + 1]
        return text

    # Legacy base64 data-URL encoder for the OpenAI vision format:
    # def encode_image(self, image_path):
    #     ...
    #     encoded_image = base64.b64encode(image_bytes).decode('ascii')
    #     return f'data:{mime_type};base64,{encoded_image}'

    def load_image(self, image_path):
        """Read a scene image as raw bytes for types.Part.from_bytes."""
        image_path = Path(image_path).expanduser()
        if not image_path.is_file():
            raise ValueError(f'Image file not found: {image_path}')
        mime_type = SUPPORTED_IMAGE_TYPES.get(image_path.suffix.lower())
        if mime_type is None:
            raise ValueError('Image must be a PNG, JPEG, or WebP file')
        try:
            image_bytes = image_path.read_bytes()
        except OSError as exc:
            raise ValueError(
                f'Could not read image file {image_path}: {exc}') from exc
        return image_bytes, mime_type

    def generate(
            self,
            message,
            environment,
            is_user_feedback=False,
            image_path=None):
        if is_user_feedback:
            self.messages.append({'sender': 'user',
                                  'text': message + "\n" + self.instruction})
        else:
            text_base = self.query
            if text_base.find('[ENVIRONMENT]') != -1:
                if image_path is not None:
                    environment = 'Refer to the attached image.'
                text_base = text_base.replace(
                    '[ENVIRONMENT]', json.dumps(environment))
            if text_base.find('[INSTRUCTION]') != -1:
                text_base = text_base.replace('[INSTRUCTION]', message)
                self.instruction = text_base
            if image_path is None:
                content = text_base
            else:
                image_bytes, mime_type = self.load_image(image_path)
                content = [
                    {'type': 'text', 'text': text_base},
                    {
                        'type': 'image',
                        'mime_type': mime_type,
                        'data': image_bytes
                    }
                ]
            self.messages.append({'sender': 'user', 'text': content})

        # =================================================================
        # Legacy OpenAI-compatible call sites, kept commented for rollback.
        # =================================================================
        # if self.use_azure and openai.api_version == '2022-12-01':
        #     # Remove unsafe user inputs. May need further refinement in the
        #     # future.
        #     if message.find('<|im_start|>') != -1:
        #         message = message.replace('<|im_start|>', '')
        #     if message.find('<|im_end|>') != -1:
        #         message = message.replace('<|im_end|>', '')
        #     deployment_name = self.credentials["azureopenai"]["AZURE_OPENAI_DEPLOYMENT_NAME_CHATGPT"]
        #     response = openai.Completion.create(
        #         engine=deployment_name,
        #         prompt=self.create_prompt(),
        #         temperature=0.1,
        #         max_tokens=self.max_completion_length,
        #         top_p=0.5,
        #         frequency_penalty=0.0,
        #         presence_penalty=0.0,
        #         stop=["<|im_end|>"])
        #     text = response['choices'][0]['text']
        # elif self.use_azure and openai.api_version == '2023-05-15':
        #     deployment_name = self.credentials["azureopenai"]["AZURE_OPENAI_DEPLOYMENT_NAME_CHATGPT"]
        #     response = openai.ChatCompletion.create(
        #         engine=deployment_name,
        #         messages=self.create_prompt(),
        #         temperature=0.1,
        #         max_tokens=self.max_completion_length,
        #         top_p=0.5,
        #         frequency_penalty=0.0,
        #         presence_penalty=0.0)
        #     text = response['choices'][0]['message']['content']
        # else:
        #     response = openai.ChatCompletion.create(
        #         model=self.model,
        #         messages=self.create_prompt(),
        #         temperature=0.1,
        #         max_tokens=self.max_completion_length,
        #         top_p=0.5,
        #         frequency_penalty=0.0,
        #         presence_penalty=0.0)
        #     text = response['choices'][0]['message']['content']

        # max_output_tokens is deliberately left unset: Gemini counts thinking
        # tokens against it, so a 2000-token cap truncates the task JSON.
        response = self.client.models.generate_content(
            model=self.model,
            contents=self.create_prompt(),
            config=types.GenerateContentConfig(
                system_instruction=self.system_message["content"],
                temperature=0.1,
                top_p=0.5))
        text = response.text
        if text is None:
            raise RuntimeError(
                "Gemini returned no text. "
                f"prompt_feedback={getattr(response, 'prompt_feedback', None)!r}, "
                f"candidates={getattr(response, 'candidates', None)!r}")
        print(text)
        self.last_response = text
        self.last_response = self.extract_json_part(self.last_response)
        self.last_response = self.last_response.replace("'", "\"")
        # dump to a text file
        with open('last_response.txt', 'w') as f:
            f.write(self.last_response)
        try:
            self.json_dict = json.loads(self.last_response, strict=False)
            self.environment = self.json_dict["environment_after"]
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            self.json_dict = None
            raise ValueError(
                "Model response was not valid task JSON. "
                "See last_response.txt for the extracted response.") from exc

        if len(self.messages) > 0 and self.last_response is not None:
            self.messages.append(
                {"sender": "assistant", "text": self.last_response})

        return self.json_dict

    def dump_json(self, dump_name=None):
        if dump_name is not None:
            # dump the dictionary to json file dump 1, 2, ...
            fp = os.path.join(dump_name + '.json')
            with open(fp, 'w') as f:
                json.dump(self.json_dict, f, indent=4)


def fetch_robopara_frame(server_url, out_dir):
    """Download the simulator's initial frame; return its local path."""
    server_url = server_url.rstrip('/')
    try:
        with urllib.request.urlopen(
                server_url + '/v1/chatgpt/info',
                timeout=ROBOPARA_TIMEOUT_S) as response:
            info = json.loads(response.read())
        with urllib.request.urlopen(
                server_url + '/v1/chatgpt/frame',
                timeout=ROBOPARA_TIMEOUT_S) as response:
            frame = response.read()
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f'Cannot reach RoboPARA server {server_url}: {exc}') from exc
    if info.get('protocol_version') != ROBOPARA_PROTOCOL:
        raise RuntimeError(
            'RoboPARA protocol mismatch: '
            f'{info.get("protocol_version")!r} != {ROBOPARA_PROTOCOL!r}')
    os.makedirs(out_dir, exist_ok=True)
    frame_path = os.path.join(out_dir, f'frame_seed{info["seed"]}.jpg')
    with open(frame_path, 'wb') as f:
        f.write(frame)
    print(f'RoboPARA task={info["task_id"]} seed={info["seed"]} '
          f'frame={frame_path}')
    return frame_path


def submit_robopara_plan(server_url, json_dict, report_dir=None):
    """POST one accepted plan; return True once the server accepts it.

    With report_dir, RoboPARA writes report.json and terminal.txt there
    after the simulation finishes (both processes share this machine).
    """
    body = {'protocol_version': ROBOPARA_PROTOCOL, 'plan': json_dict}
    if report_dir is not None:
        body['report_dir'] = os.path.abspath(report_dir)
    request = urllib.request.Request(
        server_url.rstrip('/') + '/v1/chatgpt/plan',
        data=json.dumps(body).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
        method='POST')
    try:
        with urllib.request.urlopen(
                request, timeout=ROBOPARA_TIMEOUT_S) as response:
            reply = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        try:
            reply = json.loads(exc.read())
        except ValueError:
            reply = {}
        print(f'RoboPARA rejected the plan (HTTP {exc.code}): '
              f'{reply.get("error", exc.reason)}')
        if reply.get('validation'):
            print(json.dumps(reply['validation'], indent=2))
        return False
    except urllib.error.URLError as exc:
        print(f'Cannot reach RoboPARA server: {exc}')
        return False
    print(f'RoboPARA accepted plan {reply["plan_id"]} '
          f'({reply["node_count"]} nodes); simulation is running there.')
    for node in reply['nodes']:
        print(f'  {node["node_id"]}: {node["agents"]} {node["args"]}')
    if reply.get('report_dir'):
        print(f'Simulation report will be written to {reply["report_dir"]} '
              '(report.json, terminal.txt) when RoboPARA finishes.')
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--scenario',
        type=str,
        required=True,
        help='scenario name (see the code for details)')
    parser.add_argument(
        '--image',
        type=str,
        help='optional image override for an image-based scenario')
    parser.add_argument(
        '--server-url',
        type=str,
        help='RoboPARA ChatGPT prompt server (e.g. http://127.0.0.1:8020): '
             'plan from its initial frame and send the accepted plan back')
    args = parser.parse_args()
    scenario_name = args.scenario
    # Dual arm manipulation
    # 1. example of manipulation in front of fridge
    if scenario_name == 'fridge':
        environment = {
            "assets": [
                "<fridge>",
                "<floor>"],
            "asset_states": {
                "<fridge>": "on_something(<floor>)"},
            "objects": [
                "<fridge_handle>",
                "<juice>"],
            "object_states": {
                "<fridge_handle>": "closed()",
                "<juice>": "inside_something(<fridge>)"}}
        instructions = [
            'Open the fridge with the right arm, take the juice and put it on the floor with the left arm, and close the fridge',
        ]
        image_path = None
        if args.image is not None:
            parser.error('--image is not used by the fridge scenario')
        if args.server_url is not None:
            parser.error('--server-url is only used by the office_p scenario')
    elif scenario_name == 'office_p':
        environment = None
        if args.server_url is not None:
            if args.image is not None:
                parser.error('--image and --server-url are mutually exclusive')
            image_path = fetch_robopara_frame(
                args.server_url, './out/' + scenario_name)
        else:
            image_path = args.image or '../../img/env_office_p4.png'
            instructions = [
                '1. flap_close("laptop") (Single arm, 8.5 seconds) '
                '2. pick("desktop_surface", "marker") (Single arm, 4 seconds) '
                '3. place("marker", "pen_holder") (Single arm, 4.5 seconds) '
                '4. pick("desktop_surface", "flat_newspaper_trash") (Single arm, 4 seconds) '
                '5. handover("flat_newspaper_trash", "", target_region)'
                '6. place("flat_newspaper_trash", "trash_bin") (Single arm, 4 seconds) '
                '7. pick("desktop_surface", "mouse") (Single arm, 4 seconds) '
                '8. place("mouse", "laptop") (Single arm, 4 seconds) '
                '9. adjust("red_tipped_cup", "upright") (Single arm, 7 seconds)',
            ]
    else:
        parser.error('Invalid scenario name:' + scenario_name)

    aimodel = ChatGPT(prompt_load_order=prompt_load_order)

    if not os.path.exists('./out/' + scenario_name):
        os.makedirs('./out/' + scenario_name)
    for i, instruction in enumerate(instructions):
        if image_path is None:
            print(json.dumps(environment))
        else:
            print(f'environment image: {image_path}')
        text = aimodel.generate(
            instruction,
            environment,
            is_user_feedback=False,
            image_path=image_path)
        while True:
            user_feedback = input(
                'user feedback (return empty if satisfied): ')
            if user_feedback == 'q':
                exit()
            if user_feedback != '':
                text = aimodel.generate(
                    user_feedback, environment, is_user_feedback=True)
            else:
                if args.server_url is not None:
                    aimodel.dump_json(f'./out/{scenario_name}/{i}')
                    report_dir = os.path.join(
                        './out', scenario_name, 'sim_reports',
                        time.strftime('%Y%m%dT%H%M%S'))
                    if not submit_robopara_plan(
                            args.server_url, aimodel.json_dict,
                            report_dir=report_dir):
                        print('Enter feedback to regenerate the plan, '
                              'return empty to resend, or q to quit.')
                        continue
                # update the current environment
                environment = aimodel.environment
                break
        aimodel.dump_json(f'./out/{scenario_name}/{i}')
