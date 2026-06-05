# Matt Van Horn (@mvanhorn)

## Bio
Co-founded June (self-driving oven, acquired by Weber) and the company that became Lyft. Building again. Currently vibe coding the **last30days** research tool.

## Key Projects

### last30days-skill
- **URL:** https://github.com/mvanhorn/last30days-skill
- **Stars:** 24k+
- **What it does:** AI agent skill that researches any topic across Reddit, X, YouTube, HN, Polymarket, and the web, then synthesizes a grounded brief scored by engagement and real-money bets. Zero config for Reddit/HN/Polymarket/GitHub; X/YouTube/TikTok via ScrapeCreators API.
- **Install:** `/plugin marketplace add mvanhorn/last30days-skill` (Claude Code), `clawhub install last30days-official` (OpenClaw)
- **v3 engine (Apr 2026):** Pre-research brain resolves topics to the right people, communities, and hashtags before searching — not keyword search, topic-understanding search.

### nanoclaw
- **URL:** https://github.com/qwibitai/nanoclaw (fork)
- Lightweight alternative to OpenClaw running in Docker containers. One process, small enough to understand. Agents run in isolated Linux containers with filesystem isolation. Built on Claude Agent SDK.
- Rationale: OpenClaw has ~500k lines, 53 config files, 70+ dependencies. NanoClaw provides same core functionality in a auditable codebase.

### orca
- **URL:** https://github.com/mvanhorn/orca (fork of stablyai/orca)
- Next-gen IDE for building with coding agents. Run Claude Code, Codex, or OpenCode side-by-side across repos in separate worktrees, tracked in one place. Supports Hermes Agent.

## Posting Pattern
Frequently posts about vibe coding workflows, Claude Code tips, multi-agent orchestration, and AI agent research tools. X posts from him are usually sharing new skills, techniques, or insights from his agentic workflow experiments.

## Related
- r/ClaudeCode community — where many of his workflows are discussed and validated
- OpenClaw ecosystem — skills he builds work across OpenClaw, Claude Code, Gemini CLI