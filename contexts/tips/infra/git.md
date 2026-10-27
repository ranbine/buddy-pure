---
title: "Git — Non-interactive Credential & Local Runner"
category: infra
verified_at: 2026-10-22
keywords:
  - infrastructure
  - tooling
  - git
---

# Git — Non-interactive Credential & Local Runner

## HTTPS Credential

**Problem:** Git prompts for username interactively → agent hangs.

**Rules:**
- All git operations must set `GIT_TERMINAL_PROMPT=0` (fail fast, never hang)
- Put the username in the remote URL (`https://<user>@host/...`) or use SSH remotes
- Tokens live in `~/.netrc` or a credential helper — never in the repo

## SSH (preferred for public forges)

```bash
ssh -T git@github.com            # verify key is registered
git remote add github git@github.com:<user>/<repo>.git
```

## Local CI Runner (user-mode, optional)

When shared runners are stale, run a user-mode runner via systemd:

```bash
systemctl --user status  <runner>
systemctl --user restart <runner>
journalctl --user -u <runner> -f
```
