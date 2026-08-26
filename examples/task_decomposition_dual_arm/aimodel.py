import openai
import tiktoken
import base64
import json
import os
import re
import argparse
from pathlib import Path


DEFAULT_GIGATOKEN_KEY_PATH = (
    Path.home() / ".config" / "robopara" / "gigatoken-key.txt"
)
DEFAULT_GIGATOKEN_BASE_URL = "https://sub2api.gigaapi.cc/v1"
DEFAULT_VLM_MODEL = "gpt-5.4"
SUPPORTED_IMAGE_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}

enc = tiktoken.get_encoding("cl100k_base")
with open('../../secrets.json') as f:
    credentials = json.load(f)

dir_system = './system'
dir_prompt = './prompt'
dir_query = './query'
prompt_load_order = ['prompt_role',
                     'prompt_function',
                     'prompt_environment',
                     'prompt_output_format',
                     'prompt_example']

# azure openai api has changed from '2023-05-15' to '2023-05-15'
# if you are using a 0301 version, use '2022-12-01'
# Otherwise, use '2023-05-15'


class ChatGPT:
    VALID_API_VERSIONS = ['2022-12-01', '2023-05-15']

    def __init__(
            self,
            credentials,
            prompt_load_order,
            use_azure=True,
            api_version='2023-05-15',
            gigatoken_api_path=None,
            gigatoken_base_url=None,
            gigatoken_model=None):
        self.use_azure = use_azure
        if self.use_azure:
            openai.api_key = credentials["azureopenai"]["AZURE_OPENAI_KEY"]
            openai.api_base = credentials["azureopenai"]["AZURE_OPENAI_ENDPOINT"]
            openai.api_type = 'azure'
            if api_version not in self.VALID_API_VERSIONS:
                raise ValueError(
                    f'api_version must be one of {self.VALID_API_VERSIONS}')
            openai.api_version = api_version
        else:
            self._configure_gigatoken(
                api_path=gigatoken_api_path,
                base_url=gigatoken_base_url,
                model=gigatoken_model)
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

    def _configure_gigatoken(self, api_path=None, base_url=None, model=None):
        self.model = model or os.getenv("GIGATOKEN_MODEL") or DEFAULT_VLM_MODEL

        configured_base_url = (
            base_url
            or os.getenv("GIGATOKEN_BASE_URL")
            or DEFAULT_GIGATOKEN_BASE_URL
        )
        if not configured_base_url:
            raise ValueError(
                "Gigatoken base URL is required. Pass gigatoken_base_url or "
                "set GIGATOKEN_BASE_URL.")
        self.base_url = configured_base_url.strip().rstrip("/")
        if not self.base_url.startswith(("https://", "http://")):
            raise ValueError(
                "Gigatoken base URL must start with http:// or https://")

        env_api_key = os.getenv("GIGATOKEN_API_KEY", "").strip()
        configured_key_path = (
            api_path
            or os.getenv("GIGATOKEN_API_KEY_PATH")
            or DEFAULT_GIGATOKEN_KEY_PATH
        )
        self.api_key_path = Path(configured_key_path).expanduser()

        if env_api_key:
            self.api_key = env_api_key
        else:
            try:
                self.api_key = self.api_key_path.read_text(
                    encoding="utf-8").strip()
            except FileNotFoundError as exc:
                raise FileNotFoundError(
                    f"Gigatoken API key file not found: {self.api_key_path}. "
                    "Create it or set GIGATOKEN_API_KEY.") from exc
            except OSError as exc:
                raise OSError(
                    "Error reading Gigatoken API key file "
                    f"{self.api_key_path}: {exc}") from exc

        if not self.api_key:
            raise ValueError("Gigatoken API key is empty")

        openai.api_type = "open_ai"
        openai.api_base = self.base_url
        openai.api_key = self.api_key
        openai.organization = None

    # See
    # https://learn.microsoft.com/en-us/azure/cognitive-services/openai/how-to/chatgpt#chatml
    def get_text_content(self, content):
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return ''.join(
                item.get('text', '')
                for item in content
                if isinstance(item, dict) and item.get('type') == 'text')
        return ''

    def create_prompt(self):
        prompt = ""
        if self.use_azure and openai.api_version == '2022-12-01':
            prompt = "<|im_start|>system\n"
            prompt += self.system_message["content"]
            prompt += "\n<|im_end|>\n"
            for message in self.messages:
                prompt += f"\n<|im_start|>{message['sender']}\n{message['text']}\n<|im_end|>"
            prompt += "\n<|im_start|>assistant\n"
            print('prompt length: ' + str(len(enc.encode(prompt))))
            if len(enc.encode(prompt)) > self.max_token_length - \
                    self.max_completion_length:
                print('prompt too long. truncated.')
                # truncate the prompt by removing the oldest two messages
                self.messages = self.messages[2:]
                prompt = self.create_prompt()
        else:
            prompt = []
            prompt.append(self.system_message)
            for message in self.messages:
                prompt.append(
                    {"role": message['sender'], "content": message['text']})
            prompt_content = ""
            for message in prompt:
                prompt_content += self.get_text_content(message["content"])
            print('prompt length: ' + str(len(enc.encode(prompt_content))))
            if len(enc.encode(prompt_content)) > self.max_token_length - \
                    self.max_completion_length:
                print('prompt too long. truncated.')
                # truncate the prompt by removing the oldest two messages
                self.messages = self.messages[2:]
                prompt = self.create_prompt()
        return prompt

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

    def encode_image(self, image_path):
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
        encoded_image = base64.b64encode(image_bytes).decode('ascii')
        return f'data:{mime_type};base64,{encoded_image}'

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
                content = [
                    {'type': 'text', 'text': text_base},
                    {
                        'type': 'image_url',
                        'image_url': {
                            'url': self.encode_image(image_path)
                        }
                    }
                ]
            self.messages.append({'sender': 'user', 'text': content})

        if self.use_azure and openai.api_version == '2022-12-01':
            # Remove unsafe user inputs. May need further refinement in the
            # future.
            if message.find('<|im_start|>') != -1:
                message = message.replace('<|im_start|>', '')
            if message.find('<|im_end|>') != -1:
                message = message.replace('<|im_end|>', '')
            deployment_name = self.credentials["azureopenai"]["AZURE_OPENAI_DEPLOYMENT_NAME_CHATGPT"]
            response = openai.Completion.create(
                engine=deployment_name,
                prompt=self.create_prompt(),
                temperature=0.1,
                max_tokens=self.max_completion_length,
                top_p=0.5,
                frequency_penalty=0.0,
                presence_penalty=0.0,
                stop=["<|im_end|>"])
            text = response['choices'][0]['text']
        elif self.use_azure and openai.api_version == '2023-05-15':
            deployment_name = self.credentials["azureopenai"]["AZURE_OPENAI_DEPLOYMENT_NAME_CHATGPT"]
            response = openai.ChatCompletion.create(
                engine=deployment_name,
                messages=self.create_prompt(),
                temperature=0.1,
                max_tokens=self.max_completion_length,
                top_p=0.5,
                frequency_penalty=0.0,
                presence_penalty=0.0)
            text = response['choices'][0]['message']['content']
        else:
            response = openai.ChatCompletion.create(
                model=self.model,
                messages=self.create_prompt(),
                temperature=0.1,
                max_tokens=self.max_completion_length,
                top_p=0.5,
                frequency_penalty=0.0,
                presence_penalty=0.0)
            text = response['choices'][0]['message']['content']
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
    elif scenario_name == 'office_p':
        environment = None
        image_path = args.image or '../../img/env_office_p2.jpg'
        instructions = [
            '1. Pick up the marker from the desktop. '
            '2. Put the marker into the pen holder. '
            '3. Close the laptop lid. '
            '4. Pick up the trash from the desktop. '
            '5. Put the trash into the trash bin. '
            '6. Pick up the mouse from the desktop. '
            '7. Put the mouse on the laptop. '
            '8. Adjust the position of the cup on the desktop.',
        ]
    else:
        parser.error('Invalid scenario name:' + scenario_name)

    aimodel = ChatGPT(
        credentials,
        prompt_load_order=prompt_load_order,
        use_azure=False)

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
                # update the current environment
                environment = aimodel.environment
                break
        aimodel.dump_json(f'./out/{scenario_name}/{i}')
