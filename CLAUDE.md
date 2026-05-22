# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Environment

- **OS**: Windows 11 Home (10.0.26200)
- **Shell**: bash (Git Bash)
- **Node.js**: v24.15.0
- **npm**: 11.12.1
- **IDE**: VSCode (Claude Code extension)
- **Plugin root**: `C:/Users/공동환/Desktop/agent/Claude`
- **Preferred language**: Korean (한국어) for user-facing responses

## Project Overview

This is a **Claude Code plugin** - a collection of production-ready agents, skills, hooks, commands, rules, and MCP configurations. The project provides battle-tested workflows for software development using Claude Code.

## Running Tests

```bash
# Run all tests
node tests/run-all.js

# Run individual test files
node tests/lib/utils.test.js
node tests/lib/package-manager.test.js
node tests/hooks/hooks.test.js
```

## Architecture

The project is organized into several core components:

- **agents/** - Specialized subagents for delegation (planner, code-reviewer, tdd-guide, etc.)
- **skills/** - Workflow definitions and domain knowledge (coding standards, patterns, testing)
- **commands/** - Slash commands invoked by users (/tdd, /plan, /e2e, etc.)
- **hooks/** - Trigger-based automations (session persistence, pre/post-tool hooks)
- **rules/** - Always-follow guidelines (security, coding style, testing requirements)
- **mcp-configs/** - MCP server configurations for external integrations
- **scripts/** - Cross-platform Node.js utilities for hooks and setup
- **tests/** - Test suite for scripts and utilities

## Key Commands

- `/tdd` - Test-driven development workflow
- `/plan` - Implementation planning
- `/e2e` - Generate and run E2E tests
- `/code-review` - Quality review
- `/build-fix` - Fix build errors
- `/learn` - Extract patterns from sessions
- `/skill-create` - Generate skills from git history

## Windows-Specific Notes

- Use forward slashes (`/`) in paths where possible; Node.js handles both
- Bash scripts (`.sh`) require Git Bash — ensure Git Bash is in `PATH`
- `CLAUDE_PLUGIN_ROOT` is set to `C:/Users/공동환/Desktop/agent/Claude` in both `~/.claude/settings.json` and `.claude/settings.json`
- The two `shell`-based continuous-learning hooks (`pre:observe`, `post:observe`) require Git Bash to execute `.sh` scripts; they are async/non-blocking so failures won't interrupt workflow
- For Windows-native commands use `cmd /c` or `PowerShell -Command` prefix when needed
- Package manager: **npm** (default); override via `CLAUDE_CODE_PACKAGE_MANAGER` env var

## MCP Servers (.mcp.json)

Configured servers (require `npx` + internet access on first run):

| Server | Purpose | Auth needed |
|--------|---------|-------------|
| `github` | GitHub API access | `GITHUB_TOKEN` env var |
| `context7` | Up-to-date library docs | None |
| `exa` | AI-powered web search | `EXA_API_KEY` env var (optional) |
| `memory` | Persistent memory store | None |
| `playwright` | Browser automation | None |
| `sequential-thinking` | Structured reasoning | None |

Set tokens in environment or add to `.claude/settings.json` under `"env"`.

## Hook Profile

Active profile: **standard** (`CLAUDE_PLUGIN_MODE=standard`)

Hooks enabled at `standard` level:
- Pre-Bash dispatcher (quality, GateGuard checks)
- Config file protection
- Post-edit quality gate + console.log warnings
- Session start/end lifecycle
- Cost & activity tracking

## Development Notes

- Package manager detection: npm, pnpm, yarn, bun (configurable via `CLAUDE_CODE_PACKAGE_MANAGER` env var)
- Cross-platform: Windows, macOS, Linux support via Node.js scripts
- Agent format: Markdown with YAML frontmatter (name, description, tools, model)
- Skill format: Markdown with clear sections for when to use, how it works, examples
- Skill placement: Curated in `skills/`; generated/imported under `~/.claude/skills/`
- Hook format: JSON with matcher conditions and command/notification hooks

## Contributing

Follow the formats in CONTRIBUTING.md:
- Agents: Markdown with frontmatter (name, description, tools, model)
- Skills: Clear sections (When to Use, How It Works, Examples)
- Commands: Markdown with description frontmatter
- Hooks: JSON with matcher and hooks array

File naming: lowercase with hyphens (e.g., `python-reviewer.md`, `tdd-workflow.md`)

## 토큰 절감 지침

- 불필요한 설명 금지 — 결과 위주, 설명은 한 줄 이내
- 이전 실행 결과는 diff만 제공 (변경된 부분만 출력)
- 코드 리뷰는 요약된 결과 파일 참조 (전체 코드 재출력 금지)

## Skills

Use the following skills when working on related files:

| File(s) | Skill |
|---------|-------|
| `README.md` | `/readme` |
| `.github/workflows/*.yml` | `/ci-workflow` |
| `agents/acf-*.md`, `skills/acf-*.md` | `/acf-bonding-prediction` |

When spawning subagents, always pass conventions from the respective skill into the agent's prompt.