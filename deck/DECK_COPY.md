<!-- Generated from DECK_COPY.src.md by scripts/build_docs.py. Edit the source. -->
# Mirsad deck copy (first draft)

The slide text and speaker notes now live in `Mirsad_Deck.src.html`, which builds the HTML deck, the PDF, and the PPTX. This file is the first copy draft, kept for reference; edit the deck source, not this file.

Slide text and speaker notes for the ScamShield AI presentation. Numbers come from `results/*.json` through `scripts/build_docs.py` (placeholders in double braces). The design direction is chosen separately; this copy fits every direction. Target: 12 main slides for about 5 minutes, plus an appendix for questions. The terms require slides on architecture, model choices, and privacy design (slides 6, 7, and 10).

## 1. Cover
- مرصاد Mirsad
- Finding fraudulent links in search results and maps before victims do
- ScamShield AI hackathon, Abu Dhabi Police and 42 Abu Dhabi, November 2026
- Detection engine: DaE2 (Omolara and Alawida, Computers & Security, 2025). Academic mentor: Dr. Moatsum Alawida, Abu Dhabi University
- Team: Muhammet Yalkapov (lead), Sulaymon Sadullo, and Ahmed Mohamed Almheiri, Abu Dhabi University

Notes: Mirsad means the watchtower. It watches the places where people in the UAE meet fraudulent links, and it hands the police evidence before victims report.

## 2. Fraud finds people where they search
- Abu Dhabi Police warned three times in 2026 about fake sites in search results and search ads: 17 April, 7 June, and 13 June.
- Targets: traffic fines, tolls, parcels, consumer protection, visas, and bank support lines.
- 15,642 online fraud cases handled and AED 140 million recovered by Abu Dhabi Police in the two years to October 2025 (The National, 22 October 2025).

Notes: The money figure is recovered, not lost; no sourced loss total exists, so we do not quote one.

## 3. Today, protection starts at the moment of contact
- RZAM (Dubai Electronic Security Center) blocks known malicious sites in a person's browser.
- Digital FraudHunter (TDRA) checks a message a person already received.
- Aman (Abu Dhabi Police) takes reports from victims.
- Missing: watching where scammers place their links, early, and turning what is found into evidence.

## 4. Mirsad watches upstream
- Search results and paid ads for 23 UAE service queries, in English and Arabic
- Map listings around Abu Dhabi: websites and phone numbers that do not fit the business
- New certificates that imitate 31 UAE brands, often before the link circulates
- Public threat feeds for fresh labels
- One queue for an analyst, one case file per site, one evidence package per decision

## 5. The working product
- Screenshot of the Watch screen with live data from the event (map, queue, case panel)
- Caption: live data collected on 2026-11-22T23:59:27+00:00; 337 links screened, 5 flagged at the frozen threshold.

## 6. How Mirsad works (architecture)
- Discover: search results and ads, map listings, new certificates, threat feeds
- Enrich, passive only: domain age (RDAP, first certificate), reputation (URLhaus, VirusTotal), sandbox capture in an isolated VM, Phishpedia logo match
- Score: stage 1 DaE2 on every URL; stage 2 evidence rules that only raise risk; official-domain cap; plain reasons
- Act: risk-ranked queue, case file with numbered exhibits, hold to confirm, evidence package for a registrar, aeDA, or a police blocking request
- The host never loads a suspicious page. Jais (or a local Falcon) writes summaries and never decides.

## 7. Model choices: DaE2, reproduced first
- DaE2 combines four ensembles (AdaBoost, Bagging, Stacking, Voting) over URL features; published by Omolara and Alawida (2025), with Dr. Alawida as our mentor.
- Why an ensemble: fast on a laptop CPU (114.73 ms per URL, 2,060 URLs a second in batches), explainable (four votes per link), robust where single models are not.
- We reproduced the paper's setting first, then changed only what the data audit showed was wrong: canonical URLs, a split by domain, retraining on 2024 to 2025 data, a threshold fixed at a 1% false-positive rate.

## 8. We tested DaE2 where it is hardest
- Paper's setting, random split: 95.5%
- Same split, source artifacts removed: 88.9%
- Split by domain, never-seen sites: 84.1%
- Retrained on 2024 to 2025, tested on later months: 92.0% (false-positive rate 1.17%)
- The paper's model on those later months: 50.9% (false-positive rate 88.6%)
- Callout: one rule, "malicious if the URL starts with http", already scores 83.8% on the paper's dataset.

Notes: This is the slide that earns trust. The paper's dataset rewards recognizing which list a URL came from. On real 2025 traffic, a model trained that way flags most legitimate sites. Our deployed model keeps false alarms near 1% on months it never saw.

## 9. Beyond the URL: evidence an officer can read
- Domain age, a card or password form, a form posting to another domain, a logo on the wrong domain, a paid ad for a brand query, a phone number shared across listings
- Each rule can only raise the risk, and each adds a plain reason ("Domain first seen 4 days ago")
- At realistic prevalence (1% of links fraudulent) even a strong model would be right about 41.9% of its flags, so the queue ranks cases and an officer confirms each one.

## 10. Privacy design
- Subject is websites, not people; no visitor data, cookies, or form inputs
- Query strings that carry victim data are stored only as keyed hashes
- Suspicious pages load only in an isolated VM; private addresses blocked; no form ever submitted
- Summaries from Mirsad's own facts, never the attacker's page text; a zero-egress Falcon mode
- Every view, decision, and export audited; an officer decides; nothing is blocked automatically
- Legal frame: Federal Decree-Law No. 34 of 2021 (Articles 11, 15, 40, and 48 describe what we detect; Articles 1 to 4 and 12 bound how we collect; Articles 62 and 66 are the powers our evidence feeds); PDPL principles applied by design

## 11. What Mirsad found during the event
- 337 links screened across four channels; 5 flagged
- Flags by channel and the brands most imitated, from the live run
- One case walked through end to end (from the queue to the evidence package)

## 12. Next: a 90-day pilot with the Cybercrime unit
- Weeks 1 to 4: run Mirsad on the unit's own query list and brand list; officers label cases
- Weeks 5 to 8: learn the second stage from officer decisions; connect registrar and aeDA abuse channels
- Weeks 9 to 12: measure time from first certificate to takedown against today's baseline
- Ask: a pilot partner in Abu Dhabi Police, and introductions to two UAE banks and the .ae registry

## 13. Team and credits
- Team: Muhammet Yalkapov (lead), Sulaymon Sadullo, and Ahmed Mohamed Almheiri, Abu Dhabi University
- Academic mentor: Dr. Moatsum Alawida, Abu Dhabi University
- Detection method: DaE2, Omolara and Alawida, Computers & Security 148 (2025)
- All code written by the team; open data and services credited in docs/DATA.md

## Appendix
- A1 Data sources and terms (docs/DATA.md)
- A2 Legal articles (docs/PRIVACY.md)
- A3 Full results tables E1 to E4 (docs/MODEL.md)
- A4 Limits: samples of up to 200,000 rows; 31 brands, 2 verified; free tiers non-commercial; rules are hand-set floors
