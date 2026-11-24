# Privacy design

Mirsad's subject is websites, not people. It looks for fraudulent links where residents meet them (search results, search ads, map listings, newly issued certificates) and hands confirmed cases to the police as evidence. The design applies the principles of the UAE Personal Data Protection Law (Federal Decree-Law No. 45 of 2021) even where the police themselves may be outside its scope, because a private operator or a bank partner running the same system would be inside it.

## Data inventory

| Data | Why it is needed | Where it lives | How long |
|---|---|---|---|
| Candidate link (canonical form) and its domain | The object being judged | SQLite store | Benign links 30 days; confirmed cases for the period the police set |
| Raw link with query string | Evidence for a takedown or blocking request | Evidence package only; list views show a redacted form with each query value replaced by a keyed hash | As above |
| Public registration and certificate dates | Domain age, the main early-warning signal | Evidence table | As above |
| Page capture (screenshot, title, forms) of flagged links | Proof of what the page does | Sandbox VM output, stored as a file per case | Deleted after the event in this prototype |
| Map listing: place ID, category, website domain, coordinates, hashed phone group | Map mismatch checks | SQLite store | Coordinates at most 30 days (Google Places terms) |
| Analyst decisions and an append-only audit log | Accountability | SQLite store | For the life of the case |

Not collected: visitor data, cookies, browsing histories, form inputs, credentials, business names or addresses from maps, and anything behind a login.

## Controls

1. Query-string redaction. Phishing links often carry a victim's email or a token in the query string (PhishStats records do). Mirsad shows those values only as keyed hashes in every list view (the key is random per installation), strips query strings from feed URLs on intake, and on the public demo replaces every value with a plain `[redacted]`, so no one can test guesses against a hash.
2. Personal data seen on a page. A captured page can show victim lists or leaked records; such material is flagged for the police and not kept by Mirsad.
3. Third-party exposure. Sending a link to an outside scanner reveals it to that provider. Mirsad analyzes locally first and calls outside services only for links already flagged, and only for public links. Summaries can run on a local Falcon model inside the sandbox VM, so no case data leaves the machine in that mode; the default Jais mode sends only Mirsad's own derived facts and the page title, never the page text.
4. Human decision. The tool recommends; an officer confirms every escalation through a deliberate hold-to-confirm action with a timed undo. Nothing is blocked automatically.
5. Access and audit. Every case view, decision, export, and on-demand check is written to an append-only audit table. The lab server binds to localhost, answers only to its own host names, and refuses state-changing requests from other sites. The public demo records no visitor address and no checked link, and holds no raw links (see [SECURITY.md](SECURITY.md)).
6. Isolation. Suspicious pages load only inside the sandbox VM, in a fresh browser context with no stored credentials, downloads blocked, every request to a private or local address blocked (so the crawler cannot reach the campus network), and no typing, clicking, or form submission.
7. Secrets. API keys live in a `.env` file outside the repository; `.gitignore` excludes it, commits are scanned for key patterns, and the git history was checked against the real key values on 24 November 2026. On the public demo, keys are Space secrets, and the deploy script refuses to upload any file that holds a key.

## Legal frame

| Law | Consequence for Mirsad |
|---|---|
| Federal Decree-Law No. 34 of 2021 on countering rumors and cybercrimes (English translation hosted by ADGM; the Arabic text is authoritative; amended by Federal Law No. 5 of 2024, not read) | Article 11 (fake websites, heavier when attributed to a government entity), Article 15 (capturing card data), Article 40 (internet fraud), and Article 48 (misleading online advertisements) describe what Mirsad detects. Articles 1 to 4 (unauthorized access, disruption) and 12 (interception) bound how it collects: public pages only, one load per page, rate limits, no logins or form submission, no vulnerability scanning. Articles 62 and 66 (blocking writs and orders) are the powers its evidence package is shaped for. |
| Federal Decree-Law No. 45 of 2021 on personal data protection | Applied by design (purpose limitation, minimization, accuracy, security). Commentary reports that government data and public entities are excluded under Article 2(2); the article numbers for individual rights were not read in the official text and are not cited here. |
| .ae domain policy (aeDA, TDRA) | Complaints go through the sponsoring registrar, then aeDA; the evidence package is shaped for that path. |
