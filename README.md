# InkHub Module Builder

A **local, no-code web platform** that lets anyone create a new [InkHub](https://github.com/FrancescoDefulgentiis/inkHub)
module by chatting with an AI, without writing a single line of Python.

You describe what you want your e-ink screen to show, the platform builds
the module for you, tests it in a sandbox, and hands you a **self-contained
folder that you drag into `inkHub/src/modules/`**. Then you restart InkHub
and your new module is on the launcher.

---

## Highlights

- **Bring your own AI** — pick from OpenAI (GPT), Anthropic (Claude), or Google (Gemini). You paste the API key once.
- **No coding required** — a guided wizard asks plain-English questions.
- **Drop-in output** — every generated module ships with its own `config.json`, so it works the moment you drag the folder into `src/modules/`.
- **Safety net** — before it hands you the folder, the platform imports and renders your module in a sandboxed subprocess, and iterates with the AI if anything fails.
- **Runs anywhere** — pure Python + Flask, no build step for the frontend.

---

## Quick start

```bash
cd inkhub-module-builder
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python run.py
```

Then open <http://localhost:5001> in your browser.

On first launch you'll be asked for:

1. **AI provider** (OpenAI / Anthropic / Gemini)
2. **API key** (stored locally in `config.json`, never leaves your machine except to call the AI)
3. **Model** (a sensible default is preselected)
4. **Drop-in target folder** (defaults to `../src/modules` — where InkHub picks up modules)

---

## Project layout

```
inkhub-module-builder/
├── run.py                          # entry point (python run.py)
├── requirements.txt
├── .gitignore
├── README.md
├── config.json                     # user settings (gitignored; auto-created on first run)
├── backend/
│   ├── server.py                   # Flask app
│   ├── settings.py                 # config.json read/write
│   ├── llm/                        # provider abstraction (openai/anthropic/gemini)
│   ├── wizard/                     # question schema + prompt composition
│   ├── generator/                  # writes generated module folder
│   └── validator/                  # sandboxed subprocess dry-run
├── frontend/
│   ├── templates/                  # HTML pages
│   └── static/                     # CSS + JS (vanilla, no build step)
├── reference/
│   ├── module_abc.py               # copy of the InkHub Module contract
│   └── example_module/             # canonical minimal example the AI must mimic
└── workspace/                      # generated modules land here first
```

---

## How the AI is used

1. Your wizard answers are turned into a natural-language *specification*.
2. The specification is combined with:
    - The `Module` ABC contract (copied verbatim from InkHub)
    - A canonical example module (the "hello world")
    - A strict output format (one `__init__.py`, one `config.json`)
3. The chosen provider is called with that prompt.
4. The response is parsed into files, written to `workspace/<slug>/`.
5. A subprocess spawns, imports the module, calls `render()` once with a
   dummy display size, and asserts a valid PIL image comes back.
6. On failure, the traceback is fed back to the AI, up to 3 retry attempts.
7. On success, a preview of the rendered image is shown and you get a
   "Copy to inkHub" button (or you can just drag the folder yourself).

---

## Standalone

This project is intentionally decoupled from InkHub itself — it doesn't
import any InkHub code at runtime and only writes to the target folder you
configure. It will eventually be moved into its own repository.
