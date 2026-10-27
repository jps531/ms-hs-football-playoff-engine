# Security policy

This repository runs [mshsfootball.com](https://mshsfootball.com). Its source
is public on purpose (source-available, not open source: see `LICENSE`), and
nothing about the site's security depends on the code being secret.

## Reporting a vulnerability

Please report security issues privately, through GitHub's
**[Report a vulnerability](../../security/advisories/new)** form (the
Security tab of this repository), not in a public issue or pull request.
Include what you found, how to reproduce it, and what it lets someone do.

You can expect an acknowledgement within a few days. Please give a
reasonable amount of time for a fix before disclosing anything publicly.

## Scope

In scope: the site at mshsfootball.com and the code in this repository (the
API, the pipelines, the nginx configuration, and the frontend).

Out of scope: denial of service by volume, automated scanner output without a
demonstrated impact, missing best-practice headers with no exploit, and
anything requiring access to the server or an owner's account.

Please don't run automated scanners against the live site, access other
people's data, or submit junk into the moderation queue while testing.
