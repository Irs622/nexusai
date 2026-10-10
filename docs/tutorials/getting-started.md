---
status: stable
audience:
  - end-users
owner:
  - core-team
applies_to:
  - getting-started
review_cycle: quarterly
last_reviewed: 2026-08-03
---

# 🚀 Getting Started with NexusAI

This tutorial guides you through installing NexusAI and launching your first interactive session.

---

## Step 1: Install & Set Up Environment

```bash
git clone https://github.com/Irs622/nexusai.git
cd nexusai
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### Optional extras & platform prerequisites

| Extra | Install | Native prerequisite |
|---|---|---|
| `audio` (microphone input for `--voice`) | `pip install -e ".[audio]"` | **macOS:** `brew install portaudio` · **Debian/Ubuntu:** `sudo apt-get install portaudio19-dev libasound2-dev` · **Windows:** prebuilt PyAudio wheels, no extra step |
| `workflow` (LangGraph agent graph) | `pip install -e ".[workflow]"` | none |
| `postgres` | `pip install -e ".[postgres]"` | none |
| `qdrant` | `pip install -e ".[qdrant]"` | none |

All extras are optional. NexusAI starts and runs normally without them. If PyAudio/PortAudio is missing, `--voice` logs a warning with the install hint and falls back to text input.

---

## Step 2: Set API Key

```bash
cp .env.example .env
```
Edit `.env` and set `OPENROUTER_API_KEY` or `OPENAI_API_KEY`.

---

## Step 3: Launch Interactive CLI

```bash
nexusai chat
```
Type your first prompt, e.g.: *"Show system status and active window"*.
