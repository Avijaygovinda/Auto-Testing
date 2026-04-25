# FlowTest AI — Project Context

## What this project is

FlowTest AI is an AI-powered automated testing tool for Flutter applications. The goal is to let a developer point this tool at their Flutter project + documentation, and have AI autonomously test the entire app — UI, functionality, validations, and end-to-end flows — across multiple device resolutions, generating a complete bug report.

## Core vision

The tool should:
1. Read the project documentation to understand what the app does
2. Analyze the Flutter codebase to understand the implementation
3. Generate comprehensive test cases (positive + negative + edge cases)
4. Execute UI testing across multiple device resolutions
5. Run end-to-end functional flow testing
6. Stress-test all forms with valid/invalid/edge inputs
7. **Ask the developer questions when unsure** (human-in-the-loop)
8. Generate a clear bug report with screenshots, severity, and suggested fixes

## Final product (long-term goal)

A VS Code extension where:
- Dev opens Flutter project → clicks "Start AI Testing"
- Tool autonomously tests everything
- Mid-flow, AI asks doubts ("Should cart persist after logout?") via VS Code notifications
- Report appears in VS Code panel when done

## Tech stack (decided)

### AI / LLM
- **Primary model: Google Gemini 2.0 Flash** (free tier — 1M tokens/day, has vision built-in)
- **Fallback: Groq Llama 3.3 70B** (free, fast, used when Gemini rate-limited)
- **Premium tier (later): Claude API** for hard reasoning tasks
- **NEVER train custom models** — modern LLMs + good prompting beats fine-tuning for this use case

### Backend
- **Python 3.10+**
- **google-generativeai** — Gemini API
- **groq** — Groq API (later)
- **pydantic** — structured output validation
- **python-dotenv** — env management
- **FastAPI + websockets** (added in Phase 4, not now)
- **LangGraph** (added in Phase 5 for human-in-loop, not now)

### Flutter testing layer (added in Phase 3+)
- **Patrol** — modern Flutter testing framework
- **flutter_driver / integration_test** — fallback
- Android emulator via Android Studio AVD

### VS Code extension (Phase 6+, far later)
- TypeScript + VS Code Extension API
- Webview for UI

### Storage / Reporting
- SQLite (local, no setup)
- Jinja2 + WeasyPrint for HTML/PDF reports

## Cost philosophy

- **Phase 1-3 must cost ₹0** — Gemini free tier only
- Use model routing: cheap models for simple tasks, premium only when needed
- Self-hosted models (Ollama + Llama 3.3) considered later for enterprise on-premise version

## Phased build plan

### Phase 1: Proof of concept (Week 1) ← START HERE
**Goal:** Validate that Gemini can generate useful test cases from real Flutter code.

Build ONE Python script that:
1. Reads a markdown documentation file (`docs/sample-doc.md`)
2. Reads ONE Flutter `.dart` file
3. Sends both to Gemini with a structured prompt
4. Outputs a list of test cases (positive, negative, edge cases) in JSON

**Success criteria:** Gemini gives at least 5 genuinely useful, specific test cases for real Flutter code. Not generic advice.

### Phase 2: Multi-file analysis (Week 2)
- Read entire Flutter `lib/` folder
- Build mental model of app structure
- Generate complete test plan covering all flows
- Output structured JSON test plan

### Phase 3: Visual UI testing (Week 3)
- Capture screenshots of Flutter app on different resolutions
- Send screenshots to Gemini Vision
- Identify: cut-off text, overlapping elements, broken layouts, contrast issues
- Generate UI bug report

### Phase 4: Functional flow execution (Week 4-6)
- Integrate Patrol for actual app interaction
- AI agent navigates the app based on test plan
- Captures failures, crashes, broken flows

### Phase 5: Human-in-the-loop (Week 7-8)
- Add LangGraph
- When AI is unsure, pause and ask developer
- Resume after answer

### Phase 6: VS Code extension (Week 9+)
- Wrap CLI tool in VS Code extension
- Real-time progress UI
- Inline bug reports

## Coding principles

1. **Start small. Validate. Then expand.** No phase skipping.
2. **Log every API call and response** to `logs/api_calls.log` with timestamps. Critical for prompt iteration.
3. **Use structured output (JSON mode)** wherever possible. Don't parse free text.
4. **One feature per file.** Don't build a god-class.
5. **Test on a small Flutter app first** (login + 2 screens). Scale up only after small works.
6. **Save prompts in `backend/prompts/` as separate `.txt` files** — never hardcode prompts in Python.
7. **Add `time.sleep(4)` between Gemini calls** to avoid free tier rate limits.

## Folder structure

```
flowtest-ai/
├── CLAUDE.md                    # This file
├── README.md                    # Public-facing readme
├── .env                         # API keys (gitignored)
├── .env.example                 # Template
├── .gitignore
├── backend/
│   ├── requirements.txt
│   ├── step1_prototype.py       # Phase 1 starter
│   ├── prompts/
│   │   └── test_case_generator.txt
│   ├── agents/                  # Added in Phase 2+
│   ├── utils/
│   │   └── logger.py
│   └── logs/
│       └── api_calls.log
├── sample-flutter-app/          # Test target
│   └── lib/
│       └── (sample dart files)
└── docs/
    └── sample-doc.md            # Sample documentation to test against
```

## Definition of MVP success

The MVP is successful if it can find at least 5 real bugs in a real Flutter project that the developer missed during manual review.

## Current status

**Phase 1, Day 1.** Just starting. Building the first prototype script.

## How to work with me (Claude Code)

When the developer says "let's start", begin with Phase 1 ONLY. Do not generate code for Phase 2+ until Phase 1 is validated and working. Build incrementally. Ask before adding dependencies. Log decisions in this file as we make them.
