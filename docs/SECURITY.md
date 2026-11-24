# Security

Mirsad handles links that attackers write, so its own security matters in two directions: an attacker must not be able to make a fraud link look official, and the system must not leak the victim data that fraud links often carry.

## What an attacker could try

- Make a fraud link pass as an official site, so it never reaches the analyst queue.
- Use a visitor's or analyst's browser to act on the server (cross-site requests, DNS rebinding).
- Read victim data out of stored links, the audit log, or the public seed database.
- Steer the language model that writes case summaries through text on the attacker's own page.
- Spend the paid search, maps, and model quotas, or tie up the server.
- Tamper with the model files that the sandbox VM downloads.

## Controls

1. Mirsad reads links the way a browser does. It drops tabs and newlines and, in http(s) links, treats a backslash before the query as a slash, so it scores the host a victim reaches. A host with characters no real hostname has is never official, and a backslash or a name before an @ in the host part counts as evidence of a disguised link.
2. The lab server answers only to its own names (127.0.0.1 and localhost), which stops DNS rebinding. It refuses state-changing requests from other sites, and request bodies must be JSON and at most 4 MB.
3. Runs, saved checks, single checks, and PDF reports have budgets in every mode, so neither a stranger on the public site nor a forged request can drain the API quotas.
4. Query values in links are replaced before display: by a keyed hash in the lab (the key is random per installation, never a value in the source) and by a plain `[redacted]` on the public site and in links echoed back to their sender, so no one can test guesses against a hash.
5. Pages are served with a Content Security Policy that allows scripts only from the site itself; every value written into a page is escaped. A headless Chromium renders PDF reports with JavaScript off and every network request blocked.
6. The summary model receives Mirsad's own facts and the link's host name, never the page's text or title or a map listing's name. Mirsad discards any summary that names an unknown number or brand, or that calls a flagged site official, genuine, safe, or not fraudulent, and uses a template instead.
7. Secrets live in `.env` outside git, and on the public site as Space secrets entered by the account owner. The deploy script uploads an allow-list of files and refuses to upload if any file holds a secret pattern or a value from `.env`, or if the seed database holds a query value in any link, summary, evidence line, or note.
8. Suspect pages open only inside the sandbox VM, which blocks private addresses and never submits a form. The VM service accepts requests only for its own host name, only as JSON, and with a shared token when one is set. It reads Phishpedia's brand map with an unpickler that cannot run code, checks the model files against a SHA-256 record made at the first install, and refuses a Falcon model whose checksum differs from the pinned one.

## The public demo

The public demo runs with `MIRSAD_PUBLIC=1`. By the team's choice, it is fully open: anyone with the link can view every case, check links, confirm or dismiss cases, start runs within the budgets, and download reports. Because of that, it holds no raw links and no audit of who looked at what, it never opens a suspect page (there is no sandbox on the server), and every restart returns it to the published seed. An operational police deployment would add sign-in for analysts and keep the server on a police network.

## Audit of 24 November 2026

Before the demo went live, the repository was checked four ways.

| Check | Result |
|---|---|
| Claude Security full-repository scan (145 tracked files, six components, 19 researchers, every candidate judged by a three-member verification panel) | 14 findings: 3 medium and 11 low, none critical or high. All 14 are fixed (commit b17bca2). |
| pip-audit on every pinned dependency | 18 advisories in 5 packages (Starlette, python-dotenv, dnspython, pyarrow, pytest). Fixed by upgrading; the re-run finds no known vulnerability. |
| Every file in the git history, on every branch, checked against secret patterns and the real `.env` values | No API key was ever committed. |
| Review of the fixes against a pre-deployment checklist | Five more gaps closed: length limits on decision fields, a budget on single checks, a lock around key creation, HSTS on the public site, and a wider seed check. |

The findings and their fixes:

| Finding | Severity | Fix |
|---|---|---|
| A backslash in a link's host part made a fraud host pass as an official domain (two findings, one cause) | Medium | Browser-style parsing, hostname validation before the official-domain cap, and the disguised-host rule |
| Cross-site requests could drive the lab server | Medium | Origin check, JSON-only bodies, budgets in every mode |
| The public seed kept query values in two columns | Low | Every link column rewritten; the deploy step checks all text |
| A negative limit returned the whole audit log | Low | Bounded parameters |
| Redaction fell back to a key in the public source | Low | Random per-install key; placeholders on the public site |
| The sandbox VM service accepted requests from any web page | Low | Host, JSON, and token checks |
| DNS rebinding could read the lab server | Low | Host check |
| Phishpedia model files had no integrity check | Low | SHA-256 record checked on every later run |
| The public audit log showed other visitors' checked links | Low | The public site records that a check happened, not the link |
| The Falcon model's pinned checksum was only a warning | Low | A mismatch stops the install |
| The batch endpoint returned keyed hashes of caller input | Low | Echoed links carry plain placeholders |
| The brand map was unpickled without restriction | Low | Restricted unpickler |
| Page titles reached the summary model | Low | Titles and listing names removed; clearing text rejected |

Regression tests for these fixes are in `tests/test_security.py`. On 5,000 later-month PhreshPhish URLs scored before and after the parsing change, one verdict changed: a phishing link that used the @ disguise is now caught. The false-positive rate did not change.

## Known limits

- The public demo has no sign-in, by design for judging; its budgets are kept in memory per server process.
- The style policy still allows inline styles, which the dashboard's layout uses; scripts are strict.
- The sandbox VM changes take effect only after the updated files are copied into the VM and its service is restarted, and the Phishpedia file record trusts the files present at the first install.
- The summary check catches clearing statements by wording, so a summary can still be unhelpful; the risk score, votes, and evidence never depend on the model.
