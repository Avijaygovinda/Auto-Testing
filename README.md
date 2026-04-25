# FlowTest AI

AI-powered automated testing tool for Flutter apps.

> **Status:** Phase 1 — Building first prototype.
> See `CLAUDE.md` for full project context and roadmap.

---

## Quick start with Claude Code

### Step 1: Set up the project locally

1. Copy this entire `flowtest-ai/` folder to your machine.
2. Open a terminal in the `flowtest-ai/` folder.

### Step 2: Get your free Gemini API key

1. Go to https://aistudio.google.com/apikey
2. Sign in with Google
3. Click "Create API Key" → copy it

### Step 3: Configure environment

```bash
cp .env.example .env
```

Then open `.env` and paste your Gemini key after `GEMINI_API_KEY=`.

### Step 4: Install Python dependencies

```bash
cd backend
pip install -r requirements.txt
```

### Step 5: Run the prototype (validate everything works)

```bash
python step1_prototype.py ../docs/sample-doc.md ../sample-flutter-app/lib/login_screen.dart
```

You should see Gemini generate test cases for the sample login screen.

### Step 6: Start Claude Code

In the `flowtest-ai/` folder, run:

```bash
claude
```

Then say to Claude Code:

> Read CLAUDE.md to understand the project. We just finished setting up Phase 1. Help me improve the prototype based on the output we got from running it.

Claude Code will read `CLAUDE.md` automatically and have full context of the project.

---

## Folder structure

```
flowtest-ai/
├── CLAUDE.md                # Project context (Claude Code reads this)
├── README.md                # This file
├── .env.example             # Template for API keys
├── backend/
│   ├── step1_prototype.py   # Phase 1 prototype
│   ├── requirements.txt
│   ├── prompts/             # All prompts (separate from code)
│   └── utils/
├── sample-flutter-app/      # Test target
└── docs/                    # Sample project documentation
```

## Phase progression

- ✅ Phase 1: Single-file test case generation (current)
- ⏳ Phase 2: Full project analysis
- ⏳ Phase 3: Visual UI testing with screenshots
- ⏳ Phase 4: Functional flow execution (Patrol)
- ⏳ Phase 5: Human-in-the-loop questions
- ⏳ Phase 6: VS Code extension

See `CLAUDE.md` for full details on each phase.
