# Architecture

```
 DISCOVER                  ENRICH (passive)              SCORE                        ACT
 Search monitor     ┐      Canonical URL           ┐     Stage 1: DaE2 on the URL ┐   Analyst queue (risk-ranked)
 Maps check         ├────> Domain age (RDAP / CT)  ├───> Stage 2: evidence rules  ├─> Case file with exhibits
 Certificate watch  │      URLhaus, VirusTotal     │     Allowlist cap            │   Hold to confirm, dismiss
 Threat feeds       │      Sandbox capture (VM)    │     Calibrated risk, reasons │   Evidence package export
 Analyst check      ┘      Phishpedia logo match   ┘     Jais or Falcon summary   ┘   Audit log
```

## Components

| Module | Responsibility |
|---|---|
| `mirsad/collectors/sources.py` | Search results and ads (SerpApi, Serper fallback) for {{app.search_queries}} UAE service queries; Google Places listings around Abu Dhabi; certificates containing or imitating protected brands (crt.sh and the live stream); OpenPhish, URLhaus, and PhishStats feeds |
| `mirsad/enrich/passive.py` | RDAP registration date, first certificate from crt.sh (the only age signal for .ae), URLhaus and VirusTotal lookups; cached and rate-limited |
| `mirsad/features/url.py`, `brands.py` | Robust URL parsing, canonical form, 25 lexical features, the UAE brand list, homoglyph folding, lookalike distance |
| `mirsad/models/dae2.py` | The four DaE2 ensembles (AdaBoost, Bagging, Stacking, Voting) over shared features |
| `mirsad/scoring/engine.py` | The cascade: model probability, then rules that raise the risk, then the official-domain cap; one plain reason per rule |
| `mirsad/sandbox/client.py` and `sandbox_vm/` | Page capture and Phishpedia run in an Ubuntu VM; the host never loads a suspicious page |
| `mirsad/llm/summary.py` | English and Arabic case summaries from Jais (default) or local Falcon; the model writes, never decides |
| `mirsad/store/db.py` | SQLite: candidates, scores, evidence, captures, summaries, decisions, runs, and the append-only audit log |
| `mirsad/pipeline.py` | One run per channel: discover, score, enrich only what is suspicious, capture, re-score, summarize, store |
| `mirsad/api/` | FastAPI service and the dashboard (Watch screen and case file) |

## One case, end to end

1. The search monitor runs "salik recharge" and receives an ad at position 1 that links to `salik-topup-uae.top`.
2. DaE2 scores the URL in milliseconds; the brand rule sees "salik" on a domain that Salik does not own.
3. Because the link is near or above the threshold, Mirsad asks RDAP or crt.sh for its age (four days) and URLhaus for its reputation.
4. The sandbox VM loads the page once, finds a card form that posts to another domain, and Phishpedia matches the toll-service logo on a domain that is not the brand's.
5. The risk rises to the floor of the strongest rule; each rule adds a reason in plain words. Jais writes a two-sentence summary in English and Arabic from those facts.
6. The case enters the queue. An officer opens the case file, reads the exhibits, holds to confirm, and exports the evidence package for the registrar, aeDA, or a police blocking request. Every step is audited.

## Why this shape

Each stage fails without stopping the others: no sandbox means no capture but still a score; no summary model means a template summary. The whole system runs on one laptop and a VM, which is what a 24-hour build and a live demo need. The first stage is cheap enough to screen every link; the expensive stages run only on what it flags.
