# Security Policy

## Supported Versions

Security fixes are handled on the latest public release and the default branch.

## Reporting a Vulnerability

Please report security issues privately instead of opening a public issue.

If GitHub private vulnerability reporting is enabled for this repository, use
that channel. Otherwise, contact the repository maintainers through the project
owner's preferred private channel.

Include:

- Affected version or commit
- Steps to reproduce
- Impact assessment
- Any relevant logs, stack traces, or proof-of-concept details

## Security Model

JLCParts MCP is designed to keep broad component research local. Cached search
and comparison tools read from the local SQLite index and should not make remote
network calls. Exact website detail lookup may contact the public JLCPCB/LCSC
website for one specific LCSC code.

Do not run the MCP HTTP transport on an untrusted network without adding an
appropriate access-control layer in front of it.
