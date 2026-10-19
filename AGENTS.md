# AGENTS.md

Standing rules for any AI agent (Grok, ChatGPT, Gemini, Claude, Copilot) working in my shared workspace.

1. **Read before writing.** Check STATE.md and HANDOFF.md first so you know what the last agent did.
2. **Update STATE.md** at the end of every session: status, last touched by (platform and model), next steps.
3. **Append to HANDOFF.md** with decisions, blockers, file paths and commands that worked.
4. **Never commit secrets.** No keys, tokens, passwords or personal data. Reference vault items by name only.
5. **Nothing destructive or outbound without the owner's yes.** No force-pushes, deletions, sends or posts.
6. **Score decisions.** Record a verdict and confidence for every ranking, routing or go/skip call.
7. **Pace API calls.** Respect rate limits and honour Retry-After on 429s.
8. **Keep the working repo private.** It is the one place the owner can audit and delete.
