# Skills

Agent skills for Claude Code. Start at [`AGENTS.md`](AGENTS.md).

## Quick Start

```
/recon example.com           # run recon against a target
/recon example.com --fresh   # re-run all phases from scratch
/recon-setup                 # install missing tools and wordlists
```

## Layout

```
AGENTS.md                       ← start here (table of contents)
recon/SKILL.md                  ← architecture, phase graph, output contracts
recon/references/<phase>.md     ← one self-contained guide per phase
recon/scripts/                  ← helper scripts
.claude/commands/recon.md       ← orchestrator entrypoint
results/<target>/               ← output (gitignored)
```

The orchestrator observes existing state, builds a plan, confirms with the user, then dispatches sub-agents. See [`AGENTS.md`](AGENTS.md) for principles.
