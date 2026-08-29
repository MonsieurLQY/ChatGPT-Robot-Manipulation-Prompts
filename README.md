# ChatGPT-Robot-Manipulation-Prompts

This repository provides a set of prompts that can be used with OpenAI's ChatGPT to enable natural language communication between humans and robots for executing tasks. The prompts are designed to allow ChatGPT to convert natural language instructions into a sequence of executable robot actions, with a focus on robot manipulation tasks. The prompts are easy to customize and integrate with existing robot control and visual recognition systems.
For more information, please see our [blog post](https://www.microsoft.com/en-us/research/group/applied-robotics-research/articles/gpt-models-meet-robotic-applications-long-step-robot-control-in-various-environments/) and our paper, [ChatGPT Empowered Long-Step Robot Control in Various Environments: A Case Application](https://ieeexplore.ieee.org/document/10235949).


![overview](./img/overview.jpg)
## How to use
> 🚀 **New Feature Alert**: The examples support Azure OpenAI and the OpenAI-compatible GigaToken/Sub2API gateway.
1. Fill in [secrets.json](./secrets.json) when using [Azure OpenAI](https://learn.microsoft.com/en-us/azure/cognitive-services/openai/overview). GigaToken credentials are loaded separately from environment variables or a key file as described below. Even if you do not have a subscription, you can try it out by copying and pasting the prompts into the [OpenAI interface](https://chat.openai.com/).

2. If you have access to Azure OpenAI or GigaToken/Sub2API, install the required Python packages by running the following command in a terminal session (note: we have confirmed that the sample codes work with Python 3.9.16):
```bash
> pip install -r requirements.txt
```
Then, go to a subfolder in [examples/](./examples) (for example, [examples/task_decomposition](./examples/task_decomposition)), run the following command to run the sample code:
```bash
python aimodel.py --scenario <scenario_name>
```
Replace `<scenario_name>` with the name of the scenario you want to run. Specific scenario names can be found in the `aimodel.py`.

### GigaToken / Sub2API

The non-Azure examples — except `task_decomposition_dual_arm`, which uses
Vertex AI Gemini (see below) — use an OpenAI-compatible GigaToken endpoint with
these defaults:

- Base URL: `https://sub2api.gigaapi.cc/v1`
- Model: `gpt-5.4`
- API key file: `~/.config/robopara/gigatoken-key.txt`

Store the API key outside this repository:

```bash
mkdir -p ~/.config/robopara
read -rsp "GigaToken API Key: " GIGATOKEN_API_KEY
echo
printf '%s' "$GIGATOKEN_API_KEY" > ~/.config/robopara/gigatoken-key.txt
chmod 600 ~/.config/robopara/gigatoken-key.txt
unset GIGATOKEN_API_KEY
```

The constructor arguments `gigatoken_api_path`, `gigatoken_base_url`, and
`gigatoken_model` can override these defaults. The corresponding environment
variables are `GIGATOKEN_API_KEY_PATH`, `GIGATOKEN_BASE_URL`, and
`GIGATOKEN_MODEL`. `GIGATOKEN_API_KEY` can be used instead of a key file.

Run a sample from its directory:

```bash
cd examples/task_decomposition
python aimodel.py --scenario shelf
```

## Dual-arm example: the `office_p` scenario

[examples/task_decomposition_dual_arm](./examples/task_decomposition_dual_arm)
runs on **Vertex AI Gemini** instead of the GigaToken endpoint. `office_p` is an
image-grounded scenario: the environment dictionary is replaced by a scene photo
and the model is asked to infer the objects and their states from the image.

### Credentials

Authentication uses a Google Cloud service-account JSON key, which must be kept
outside this repository:

```bash
mkdir -p ~/.config/robopara
# copy your service-account key there, then:
chmod 600 ~/.config/robopara/<your-service-account>.json
```

Defaults: service-account key `~/.config/robopara/p-150gk23k-718446bc2ebd.json`,
project `p-150gk23k`, location `global`, model `gemini-3.7-flash`.

Override them with the constructor arguments `vertex_credentials_path`,
`vertex_project`, `vertex_location`, and `vertex_model`, or with the environment
variables `GOOGLE_APPLICATION_CREDENTIALS`, `GOOGLE_CLOUD_PROJECT`,
`GOOGLE_CLOUD_LOCATION`, and `VERTEX_MODEL`:

```bash
export GOOGLE_APPLICATION_CREDENTIALS=~/.config/robopara/<your-service-account>.json
export VERTEX_MODEL=gemini-3.7-flash
```

This example additionally needs `google-genai` and `google-auth`, both of which
are in [requirements.txt](./requirements.txt).

### Running it

Scripts must be run from inside their own example directory — every path in them
is relative:

```bash
cd examples/task_decomposition_dual_arm

# image-grounded scenario (default image: ../../img/env_office_p2.jpg)
python aimodel.py --scenario office_p

# use a different scene photo (PNG, JPEG, or WebP)
python aimodel.py --scenario office_p --image ../../img/your_scene.png

# text-only dual-arm scenario, no image
python aimodel.py --scenario fridge
```

After each response the script waits for input:

- press **Enter** to accept the plan, advance the environment, and move on;
- type any other text to send it back as feedback and regenerate;
- type **`q`** to quit.

Accepted plans are written to `./out/<scenario>/<i>.json`, for example
`out/office_p/0.json`. The raw model reply of the most recent call is always
dumped to `last_response.txt`, which is where to look if the JSON fails to parse.

### Converting a plan into a schedule

[to_schedule.py](./examples/task_decomposition_dual_arm/to_schedule.py) turns an
accepted plan into the `schedule` block consumed by the scheduling project. It is
offline — it makes no API calls — and reads the `task_sequence` /
`step_instructions` pair produced above:

```bash
cd examples/task_decomposition_dual_arm

# write the schedule to a file
python to_schedule.py --input out/office_p/0.json --output out/office_p/0_schedule.json

# or print it to stdout
python to_schedule.py --input out/office_p/0.json
```

`--input` is required; omitting `--output` prints the JSON instead of writing it.

Only the `schedule` field is generated. The `evaluation`, `solver`, and `chains`
blocks are outputs of the CP-SAT solve, and the per-action `region` field depends
on the physical layout of the scene, so none of them are fabricated here.

The converter accepts only the skills `pick`, `place`, `flap_close`, and
`adjust`. A plan generated from a different ROBOT ACTION LIST is refused with
`conversion failed: unknown skill ...` rather than silently mangled.

## Bibliography
```
@article{10235949,
  author={Wake, Naoki and Kanehira, Atsushi and Sasabuchi, Kazuhiro and Takamatsu, Jun and Ikeuchi, Katsushi},
  journal={IEEE Access}, 
  title={ChatGPT Empowered Long-Step Robot Control in Various Environments: A Case Application}, 
  year={2023},
  volume={},
  number={},
  pages={1-1},
  doi={10.1109/ACCESS.2023.3310935}}
@article{wake2023gpt,
  title={GPT-4V (ision) for Robotics: Multimodal Task Planning from Human Demonstration},
  author={Wake, Naoki and Kanehira, Atsushi and Sasabuchi, Kazuhiro and Takamatsu, Jun and Ikeuchi, Katsushi},
  journal={arXiv preprint arXiv:2311.12015},
  year={2023}
}
```

## Contributing

This project welcomes contributions and suggestions.  Most contributions require you to agree to a
Contributor License Agreement (CLA) declaring that you have the right to, and actually do, grant us
the rights to use your contribution. For details, visit https://cla.opensource.microsoft.com.

When you submit a pull request, a CLA bot will automatically determine whether you need to provide
a CLA and decorate the PR appropriately (e.g., status check, comment). Simply follow the instructions
provided by the bot. You will only need to do this once across all repos using our CLA.

This project has adopted the [Microsoft Open Source Code of Conduct](https://opensource.microsoft.com/codeofconduct/).
For more information see the [Code of Conduct FAQ](https://opensource.microsoft.com/codeofconduct/faq/) or
contact [opencode@microsoft.com](mailto:opencode@microsoft.com) with any additional questions or comments.

## Trademarks

This project may contain trademarks or logos for projects, products, or services. Authorized use of Microsoft 
trademarks or logos is subject to and must follow 
[Microsoft's Trademark & Brand Guidelines](https://www.microsoft.com/en-us/legal/intellectualproperty/trademarks/usage/general).
Use of Microsoft trademarks or logos in modified versions of this project must not cause confusion or imply Microsoft sponsorship.
Any use of third-party trademarks or logos are subject to those third-party's policies.
