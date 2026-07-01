# Contributing to TradingAgentsLab

Thanks for your interest in contributing. This document explains the rules
of the road for getting changes into the project.

## Licensing of Contributions

TradingAgentsLab is dual-natured:

- The **upstream** TradingAgents code (originally by Tauric Research) is
  licensed under the **Apache License 2.0**. See `LICENSE-APACHE`.
- All **new code and modifications** in this repository are licensed under the
  **GNU Affero General Public License v3.0 (AGPL-3.0)**. See `LICENSE`.

When you submit a contribution, you agree that your contribution will be
licensed under AGPL-3.0 (or under Apache 2.0 if the change is to a file that
remains part of the upstream-derived portion).

## Contributor License Agreement (CLA)

Before any pull request can be merged, the contributor (you) must sign the
project's Contributor License Agreement. The CLA is in `CLA.md`.

The CLA accomplishes two things:
1. Confirms that you have the right to contribute the code (you wrote it,
   or you have permission from the rights holder).
2. Grants the project maintainers a copyright license to use, modify, and
   redistribute your contribution — including the right to **dual-license**
   the project in the future (e.g., to offer commercial licenses alongside
   AGPL-3.0).

You retain copyright to your contributions. The CLA is a license, not an
assignment.

### How to sign

For now, signing is done by:
1. Reading `CLA.md` in full.
2. Adding a comment to your first pull request stating:
   > I have read and agree to the TradingAgentsLab Contributor License
   > Agreement (CLA.md) version 1.0.
3. Including your full legal name and email address in that comment.

Future versions of this project may use an automated CLA bot
(e.g., CLA Assistant) to streamline this process.

## Pull Request Process

1. Fork the repository and create a feature branch off `main`.
2. Make your change. Keep PRs focused — one logical change per PR.
3. If you modified a file that originated upstream from TradingAgents,
   add or update a notice at the top of that file indicating it was
   modified (Apache License 2.0 Section 4(b) requirement).
4. Run any existing tests and add new ones for new behavior.
5. Open a PR against `main`. Sign the CLA in your PR comment if you have
   not signed it on a previous PR.

## Reporting Issues

Open a GitHub Issue. Include:
- What you expected to happen
- What actually happened
- Reproduction steps
- Environment details (OS, Python version, LLM provider)

## Code of Conduct

Be respectful, be constructive. Disagreement is fine; personal attacks
are not. Maintainers reserve the right to remove comments and block users
who violate this norm.
