# Heimdall Agent System

## Overview

Heimdall uses specialised Claude Code agents, each with a defined role, toolset, and handoff protocol. Agents are designed to chain — not overlap. Each agent folder contains a `SKILL.md` that defines its responsibilities, boundaries, inputs/outputs, and integration points.

## Agent Roster

| Agent | Folder | Role |
|-------|--------|------|
| TPMO | `tpmo/` | Roadmap, milestones, deadlines, cross-agent orchestration |
| Architect | `architect/` | System design, code structure, architectural decisions |
| Network Security | `network-security/` | Scan configuration, tool chain execution, raw output |
| Finding Interpreter | `finding-interpreter/` | Raw scan → plain-language findings via Claude API |
| Message Composer | `message-composer/` | Findings → channel-formatted messages (Telegram/WhatsApp) |
| Prospecting | `prospecting/` | Lead generation pipeline, CVR data, Layer 1 scanning |
| Legal Compliance (Valdí) | `valdi/` | Scanning consent verification, Layer classification, GDPR checks |
| Grant & Funding | `grant-funding/` | Startup Denmark (SIRI) application, grant drafting, budget tables, consortium materials |
| Client Memory | `client-memory/` | Per-client persistent state, scan history, remediation tracking |
| DevOps | `devops/` | Infrastructure config, Docker, deployment, monitoring |
| Marketing | `marketing/` | Outreach strategy, channel rules, prospect communication |
| Fullstack Guy | `fullstack-guy/` | Real-time FastAPI + frontend patterns, WebSocket, CSS animations |

## Chain Architecture

```
Prospecting → Network Security → Finding Interpreter → Message Composer
     ↓               ↓                    ↓                    ↓
Legal Compliance  Client Memory      Client Memory        Client Memory
     (gate)        (context)          (history)            (delivery log)
```

- **Prospecting** identifies targets (Layer 1 only)
- **Legal Compliance** gates every scan — no Layer 2 without documented consent
- **Network Security** executes scans and produces structured raw output
- **Finding Interpreter** translates raw output into plain-language findings
- **Message Composer** formats and delivers via the client's preferred channel
- **Client Memory** is queried by Interpreter and Composer for personalisation
- **TPMO** monitors the entire pipeline and flags blockers
- **Architect** is consulted before any structural code change
- **Marketing** governs outreach channels and prospect communication
- **Grant & Funding** operates in parallel, pulling from the briefing and business case
- **DevOps** maintains the infrastructure all agents run on

## Conventions

- Each agent's `SKILL.md` is the single source of truth for that agent's behaviour
- Agents communicate via structured files in `data/` directories (JSON, CSV)
- No agent modifies another agent's skill folder
- Legal Compliance has veto authority over Network Security scans
- Client Memory is read-only for all agents except the Client Memory agent itself
- All agents reference `docs/briefing.md` as the master context document
