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
