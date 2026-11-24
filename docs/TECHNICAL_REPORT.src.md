# Mirsad: early detection of fraudulent links in search results, maps, and new certificates

Technical report, ScamShield AI hackathon (Abu Dhabi Police and 42 Abu Dhabi), November 2026.
Team: Muhammet Yalkapov (team lead), Sulaymon Sadullo, and Ahmed Mohamed Almheiri, Abu Dhabi University.
Academic supervisor: Dr. Moatsum Alawida, Abu Dhabi University.

Every number in this report is generated from the result files in `results/` by `scripts/build_docs.py`; none is typed by hand.

## Abstract

Fraudulent websites reach UAE residents through search results, paid search ads, and map listings, where they imitate fines, tolls, parcels, banks, and government services. Existing UAE protections act when a person meets a link; Mirsad acts earlier, where the scammer places it. Mirsad watches four channels ({{app.search_queries}} UAE service searches in English and Arabic, Google Maps listings around Abu Dhabi, newly issued certificates that imitate {{app.brands}} UAE brands, and public phishing feeds), scores every link with a four-ensemble URL classifier, collects passive evidence for suspicious links, and gives an analyst a ranked queue, a case file, and an evidence package. The classifier follows the DaE2 ensemble design [1], which we re-implemented with a leakage-resistant representation and retrained on 2024 to 2025 data. Our audit of the common public benchmark showed that a one-line rule scores {{pct:e0.scheme_only_rule.accuracy}} on it, so we tested on sites never seen in training and on later months. On later months the deployed model reaches {{pct:e3a.at_validation_threshold.dae2_mean.accuracy}} accuracy at a {{pct2:e3a.at_validation_threshold.dae2_mean.false_positive_rate}} false-positive rate, while a model trained the usual way on the benchmark flags {{pct:e3b.at_validation_threshold.dae2_mean.false_positive_rate}} of legitimate sites. Because fraud is rare in live traffic, a second stage of evidence rules and an officer's confirmation decide what reaches a takedown.

## 1. Introduction

Abu Dhabi Police warned three times in 2026 ({{facts.adp_warnings_2026.0}}, {{facts.adp_warnings_2026.1}}, and {{facts.adp_warnings_2026.2}}) about fake websites that rank near the top of search results or buy search ads for public services. In the two years to October 2025, Abu Dhabi Police handled {{int:facts.adp_online_fraud_cases_two_years}} online fraud cases and recovered AED {{facts.adp_recovered_aed_million_two_years}} million for victims ({{facts.adp_figures_source}}). The UAE already protects individuals at the moment of contact: the RZAM browser extension (Dubai Electronic Security Center) blocks known malicious sites, TDRA's Digital FraudHunter checks a message a person has received, and the Aman service of Abu Dhabi Police takes reports from victims. The challenge asks for a different capability: detecting fraudulent links across the open internet, including search results and maps, early enough for proactive measures.

Mirsad's contributions, built over three days, are the following.

1. An end-to-end watch over four channels (search results and ads, map listings, new certificates, and threat feeds), running on one laptop with an isolated sandbox virtual machine.
2. A detection model that scores a URL in about {{n2:e4.median_ms_single_url}} ms: four ensembles (AdaBoost, Bagging, Stacking, and Voting) after the DaE2 design [1], re-implemented with a canonical URL representation, chi-squared selection, truncated SVD, and {{app.lexical_features}} lexical features.
3. A dataset audit and a leakage-aware evaluation: a random split, a split by registered domain, and a temporal split on recent data, with every threshold fixed on validation data before testing.
4. A second stage of evidence rules (domain age, forms, logos, reputation, and channel context) with a two-signal policy for live channels, so that a URL score alone rarely reaches an analyst.
5. An analyst workflow with plain-language reasons, numbered exhibits, an evidence package, and summaries written by a UAE-built language model under a fact check.
6. A privacy and safety design: websites rather than people as the subject, keyed hashing of victim data, sandboxed page loads, and an append-only audit log.

## 2. System overview

Mirsad works in four stages.

| Stage | What happens | Main code |
|---|---|---|
| Discover | Collectors pull candidate links from the four channels | `mirsad/collectors/sources.py`, `certstream_local.py` |
| Enrich | Passive evidence for suspicious links: registration date, first certificate, reputation lists, sandbox capture, logo check | `mirsad/enrich/passive.py`, `mirsad/sandbox/client.py`, `sandbox_vm/` |
| Score | The four-ensemble model on every URL, then evidence rules that can only raise the risk, and an official-domain cap | `mirsad/models/dae2.py`, `mirsad/scoring/engine.py` |
| Act | Ranked queue, case file, hold-to-confirm decision, evidence package, audit log | `mirsad/api/`, `web/`, `mirsad/store/db.py` |

A FastAPI service on the laptop runs the collectors, the model, and a SQLite store, and serves the dashboard. The sandbox is an Ubuntu virtual machine reached through VirtualBox port forwards: port 8601 for page capture and Phishpedia, and port 8602 for a local Falcon model. The laptop never loads a suspicious page itself.

## 3. Data collection

Search results and ads. Mirsad runs {{app.search_queries}} UAE service searches in English and Arabic (for example "salik recharge", "pay traffic fine abu dhabi", and "تتبع شحنة بريد الإمارات") through SerpApi, with Serper as a fallback, and keeps every organic result and paid ad. When a search names a brand, each result is compared with that brand's official domains, so an ad for a Salik search that points elsewhere carries that fact into scoring.

Map listings. Mirsad runs {{app.maps_queries}} searches through Google Places around Abu Dhabi and checks three things: a website unrelated to the business, a brand name on a domain the brand does not own, and one phone number shared across listings with different websites. Under Google's terms Mirsad keeps only the place ID, category, website domain, coordinates for at most 30 days, and a hashed phone group.

New certificates. A scam site needs a certificate before the browser shows a padlock, and every certificate is published in Certificate Transparency logs within minutes. Mirsad starts certstream-server-go on the laptop, bound to 127.0.0.1, only for the minutes of a certificate run, and reads its feed of newly certified names; it also queries crt.sh for recent certificates that contain a protected brand. The stream carries thousands of names a second, so its brand check is stricter than elsewhere: a brand token of seven letters or more, or a near-miss spelling of one, counts on its own, while shorter or ordinary-word tokens count only beside UAE context (.ae, "dubai", "uae") or a scam word ("pay", "fines", "track").

Threat feeds. OpenPhish, URLhaus, and PhishStats supply links that others have already reported. Query strings are stripped on intake, because feed records can carry victims' details.

## 4. The detection model

### 4.1 Task

The model receives a URL string and returns the probability that it is malicious. It sees only the string; everything a string cannot show (a domain's age, a card form, a logo) belongs to the second stage in Section 5.

### 4.2 Design: diverse ensembles

The model follows the DaE2 design [1]: train several different base learners and combine them through four ensemble schemes. The reasoning is that single models fail in different ways on URL data. A linear model over character patterns misses interactions between features; a deep decision tree overfits to frequent hosts; a nearest-neighbor model depends on how dense the training data is near a query. Ensembles reduce these errors in two ways: averaging many models trained on resampled data lowers variance, and combining models with different inductive biases lowers the chance that all of them fail on the same input.

The four schemes combine learners differently.

- AdaBoost trains weak learners one after another. After each round it raises the weight of the training examples the current ensemble gets wrong, so the next learner concentrates on them, and each learner's vote is weighted by how accurate it was. With weighted error e_m in round m, the learner's weight is a_m = r * ln((1 - e_m) / e_m), where r is the learning rate, and misclassified examples have their weights multiplied by exp(a_m).
- Bagging trains many learners in parallel, each on a random sample of the training data, and averages their predicted probabilities. It mainly reduces variance, which suits deep decision trees.
- Stacking trains several base learners and then a meta-learner that takes their predicted probabilities as input and learns how much to trust each one. The meta-learner is trained on out-of-fold predictions, so it never sees a base learner's prediction on that learner's own training rows.
- Voting averages the probabilities of a few strong but different learners (soft voting). It is the simplest combination and is robust when no single learner dominates.

Mirsad keeps all four and scores each link with the mean of their probabilities:

p(u) = (p_AdaBoost(u) + p_Bagging(u) + p_Stacking(u) + p_Voting(u)) / 4.

Keeping all four, instead of selecting one, has a practical benefit beyond accuracy: the four votes are shown to the analyst, and a case where all four agree reads differently from one where a single ensemble fires.

### 4.3 Representation

Our representation is designed so that the model cannot learn which source list a URL came from, a shortcut Section 6.2 measures.

1. Canonical form. Each URL is reduced to its host (lowercased, without the scheme, "www.", default port, or trailing slash), path, and query. The benchmark's malicious rows usually carry a scheme and its benign rows usually do not, so leaving the scheme in lets a model learn the list, not the fraud.
2. Character n-grams. The canonical string is split into overlapping character sequences of three to five characters, hashed into 2^19 columns, and weighted by TF-IDF with sublinear term frequency: w(t, u) = (1 + ln tf(t, u)) * idf(t), with idf(t) = ln((1 + N) / (1 + df(t))) + 1, followed by L2 normalization. Character n-grams capture lookalike spellings, digit substitutions, and suspicious word pieces that whole-word tokens miss.
3. Selection and reduction. A chi-squared test keeps the 20,000 hashed columns most associated with the label, and a truncated singular value decomposition reduces them to 100 components. Truncated SVD is principal component analysis for sparse matrices (without centering); selecting first keeps the stored projection small and the scoring fast.
4. Lexical features. {{app.lexical_features}} handcrafted features describe the URL's structure: the lengths of the URL, host, path, and query; dots, hyphens, and digits in the host; subdomain count; slashes, parameters, "@" and "%" signs; digit ratio and host entropy; whether the host is an IP address, uses punycode or non-ASCII characters, has a port, is a known shortener, or uses a cheap top-level domain; lure words; brand mentions, brand-off-domain, and lookalike distance to the nearest protected brand; and a phone number in the query.
5. Two blocks. The sparse TF-IDF block feeds the linear and naive Bayes learners; the dense block (100 SVD components plus the lexical features, standardized) feeds trees and nearest neighbors. One featurizer serves all four ensembles, so a link is vectorized once and scored four times.

A second representation, word-level TF-IDF of the raw URL string, is kept only for the benchmark comparison in Section 6 (E1a and E2p).

### 4.4 The four ensembles as implemented

| Ensemble | Base learners | Input block | Main settings |
|---|---|---|---|
| AdaBoost | Decision trees of depth 3 | Dense | 150 rounds, learning rate 0.5 |
| Bagging | Decision trees of depth 22, at least 2 rows per leaf | Dense | 30 trees, each on a sample of half the rows drawn with replacement |
| Stacking | Logistic regression, complement naive Bayes, calibrated linear SVM (sparse); random forest of 60 trees and a decision tree of depth 18 (dense) | Both | Logistic-regression meta-learner on 3-fold out-of-fold probabilities |
| Voting | K-nearest neighbors (k = 15, distance-weighted, fitted on a 50,000-row sample), logistic regression, calibrated linear SVM | Both | Soft voting (mean probability) |

Two implementation decisions changed during the build. Boosting logistic regression on the hashed TF-IDF block collapsed to a constant output, so AdaBoost boosts shallow trees on the dense block. Exact nearest neighbors over half a million rows was too slow for live scoring, so the KNN member is fitted on a stratified sample. The linear SVM is wrapped in sigmoid calibration, because stacking and voting need probabilities, not margins.

### 4.5 Threshold

Thresholds are never tuned on the test set. Each experiment holds out 10% of its training rows as a validation slice; after fitting, the threshold is set to the lowest score at which the validation false-positive rate is at most 1%, and it is frozen before the test rows are scored. The deployed threshold is {{n2:e3a.at_validation_threshold.dae2_mean.threshold}}. A police queue full of false alarms would be ignored, so the false-positive rate is the constraint and recall is what the model achieves under it.

### 4.6 Engineering for live scoring

Training uses all processor cores; live scoring switches every estimator to one thread, because starting a worker pool costs more than one prediction. The deployed model file is {{e4.model_file_mb}} MB after xz compression and loads in {{e4.model_load_seconds}} s. On the development laptop it scores one URL in a median of {{n2:e4.median_ms_single_url}} ms (95th percentile {{n2:e4.p95_ms_single_url}} ms) and about {{int:e4.urls_per_second_batch}} URLs a second in batches ({{e4.machine}}).

## 5. The second stage: evidence and decision

### 5.1 Passive enrichment

For links near or above the threshold, Mirsad collects evidence by looking only: the registration date from RDAP, the first certificate from crt.sh (which stands in for .ae domains, whose registry hides dates), URLhaus and VirusTotal verdicts, and, when the sandbox is running, one page load. It never logs in, submits a form, or probes a server. Sites on shared hosting platforms (framer.app, github.io, and others in the Public Suffix List's private section) are marked as such, because the platform's registration date says nothing about the site.

### 5.2 Sandbox capture and logo check

The sandbox service loads the page once in a fresh Playwright Chromium context and returns a screenshot, the redirect chain, and every form with its fields and target domain. A route handler and an internal SOCKS proxy resolve each request's host and refuse private, loopback, link-local, and other non-global addresses, which closes the DNS-rebinding gap between two lookups. Navigations other than GET and HEAD are aborted, so a page cannot submit a form by itself. Phishpedia then looks for a known brand's logo in the screenshot and checks whether the page's registered domain belongs to that brand; Mirsad counts a match only on the brand's exact domains, stricter than Phishpedia's default.

### 5.3 Evidence rules

Each rule sets a minimum risk when it fires and adds one sentence to the case. Rules can only raise the risk; the one exception is the official-domain cap, which keeps a brand's own domains (and any .gov.ae host) out of the queue.

| Rule | Fires when |
|---|---|
| Brand off domain | The name imitates a protected brand on a domain the brand does not own |
| Card form, password form | The captured page asks for a card number or a password |
| Form to another domain | A form on the page posts to a different registered domain |
| Logo mismatch | Phishpedia finds a brand's logo on a domain that brand does not use |
| Ad for a brand query | The link was bought as an ad for a search that names a brand |
| Ranks for a brand query | The link ranks in organic results for a brand search without being official |
| Listing checks | A map listing's website is unrelated to the business, a brand appears on a non-official domain (flagging only when that domain is young or on a cheap top-level domain), or one phone number appears on three or more listings |
| Reputation | URLhaus or OpenPhish lists the link, or at least two VirusTotal engines flag it |
| Injected phone number | An official brand page is linked with a phone number in its query string, a trick that shows a fake support number on a real site |
| Young domain | The domain was first seen within 90 days (a reason, and a stronger brand rule when within 30) |

### 5.4 Two signals on live channels

The validation results imply that a URL score alone cannot carry a live queue. If 1% of screened links were fraudulent, precision would be P = (TPR * b) / (TPR * b + FPR * (1 - b)) with b = 0.01; for the deployed model this gives about {{pct:e3a.at_validation_threshold.dae2_mean.precision_at_1pct_prevalence}}. Our first live run confirmed it: ordinary business websites from map listings crossed the threshold on their address alone. On the search, maps, and certificate channels a link therefore enters the queue only with a model score of at least {{n2:app.model_alone}}, or with at least one solid rule that agrees. Weak rules (a young domain on its own, an unrelated listing website, an organic result for a brand query) do not count as that second signal. Links that miss the bar stay just under the threshold, on watch.

## 6. Evaluation

### 6.1 Data

Two public datasets were used. malicious_phish (Kaggle) is the common benchmark for URL classification: {{int:e0.rows}} URLs labeled benign, defacement, phishing, or malware, pooled from several older sources. PhreshPhish (Hugging Face, CC BY 4.0) holds phishing and benign pages from July 2024 to December 2025 with a strictly later test split; Mirsad reads only its URL, label, and date columns. Each experiment trains on a stratified sample of up to 200,000 rows, a limit set by the build time; the exact counts are in the result files.

### 6.2 Dataset audit (E0)

Before any training, `scripts/audit_dataset.py` measured what the benchmark rewards.

- The rule "malicious if the URL starts with a scheme" is {{pct:e0.scheme_only_rule.accuracy}} accurate, because {{pct:e0.scheme_only_rule.share_malicious_with_scheme}} of malicious rows carry a scheme against {{pct:e0.scheme_only_rule.share_benign_with_scheme}} of benign rows.
- Under a random 80/20 split, {{pct:e0.random_split.share_test_rows_domain_seen_in_train}} of test rows share their registered domain with training rows, so a model can pass by remembering sites.
- The defacement class has {{int:e0.per_class.defacement.rows}} rows from only {{int:e0.per_class.defacement.unique_registered_domains}} registered domains.
- There are {{int:e0.exact_duplicates}} exact duplicate URLs and {{int:e0.canonical_urls_with_conflicting_labels}} canonical URLs with two different labels.

These findings motivated the canonical representation and the two harder test settings below.

### 6.3 Protocol and metrics

All experiments are binary (benign against malicious). Thresholds come from the validation slice as described in Section 4.5. Reported metrics are accuracy; precision, recall, and F1 for the fraud class; the false-positive rate; ROC AUC; and precision at a 1% prevalence. The tables show the four ensembles and their mean at each one's own validation threshold.

### 6.4 E1: public benchmark, random split

Random, stratified 80/20 split of the benchmark sample ({{int:e1a.train_rows}} training rows, {{int:e1a.validation_rows}} validation rows, {{int:e1a.test_rows}} test rows).

E1a, raw URL with word TF-IDF (the conventional setting):

{{table:e1a}}

E1b, our canonical representation on the same split:

{{table:e1b}}

Removing the scheme and "www." costs the ensemble mean about {{n2:delta.e1.accuracy_points}} accuracy points: the share of the conventional score that came from recognizing source lists rather than fraud.

### 6.5 E2: sites never seen in training

Duplicates and conflicting labels removed; the split is grouped by registered domain, so no domain appears on both sides ({{int:e2o.domains_shared_between_train_and_test}} shared domains).

With the raw representation:

{{table:e2p}}

With ours:

{{table:e2o}}

### 6.6 E3: recent threats, later months

Trained on PhreshPhish URLs from {{e3a.train_date_range.0}} to {{e3a.train_date_range.1}} ({{int:e3a.train_rows}} training rows) and tested on {{int:e3a.test_rows}} URLs from {{e3a.test_date_range.0}} to {{e3a.test_date_range.1}}, a strictly later period. This is the deployed model.

{{table:e3a}}

E3b scores the same later test set with the E1a model, trained the conventional way on the benchmark:

{{table:e3b}}

### 6.7 Discussion

The benchmark score in the conventional setting is mostly a measure of the dataset, not of fraud detection: one rule about the scheme reaches {{pct:e0.scheme_only_rule.accuracy}}, and accuracy falls to {{pct:e2o.at_validation_threshold.dae2_mean.accuracy}} once sites cannot be shared between training and test. The temporal test is the one that matters for a police deployment, and it separates the two training choices sharply. The benchmark-trained model flags {{pct:e3b.at_validation_threshold.dae2_mean.false_positive_rate}} of legitimate later URLs, while the model retrained on recent data holds a {{pct2:e3a.at_validation_threshold.dae2_mean.false_positive_rate}} false-positive rate with {{pct:e3a.at_validation_threshold.dae2_mean.fraud_class.recall}} recall. Even so, at realistic prevalence about {{pct:e3a.at_validation_threshold.dae2_mean.precision_at_1pct_prevalence}} of model-only flags would be right, which is why Section 5 exists.

## 7. Analyst workflow

The Watch screen shows the ranked queue, a stylized map of Abu Dhabi with map-check results, flags per hour, and the selected case. The case page shows the four ensemble votes, the final risk against the threshold, a timeline, a graph of how the evidence connects, numbered exhibits with their sources, and the reasons in plain words. An analyst confirms a case by holding a button, which prevents accidental decisions; the evidence package then exports the redacted link, exhibits, timeline, and a request shaped for the registrar, aeDA, or a police blocking request.

Case summaries in English and Arabic are written by Jais 3 (MBZUAI Institute of Foundation Models) or, in a zero-egress mode, by a local Falcon in the sandbox. The model receives only facts Mirsad has established, never page text, because a page can carry instructions aimed at a language model (prompt injection). A fact check rejects any summary with a number, a protected brand, or an imitation claim that the facts do not support, and summaries may not say a site is live; a template is written instead. Summaries are rewritten whenever cases are rescored.

## 8. Privacy, security, and legal design

The subject of Mirsad is websites, not people. It collects no visitor data, cookies, or form inputs. Query values in stored links, which can carry a victim's email or token, appear in every list view only as keyed HMAC-SHA-256 hashes, and feed URLs lose their query strings on intake. Suspicious pages load only in the sandbox, with private addresses blocked and no form submission. The server binds to localhost, and every case view, decision, export, and on-demand check is written to an append-only audit table. No case is blocked automatically; an officer decides.

The legal frame is Federal Decree-Law No. 34 of 2021 on countering rumors and cybercrimes. Articles 11, 15, 40, and 48 describe the offenses Mirsad detects (fake websites, card-data capture, internet fraud, and misleading online advertisements); Articles 1 to 4 and 12 bound how it collects (public pages only, one load per page, rate limits, no logins or form submission, no vulnerability scanning); Articles 62 and 66 provide the blocking powers its evidence package serves. Mirsad also applies the principles of the Personal Data Protection Law (Federal Decree-Law No. 45 of 2021): purpose limitation, minimization, accuracy, and security. Details are in `docs/PRIVACY.md`.

## 9. Live results

In live runs on {{counts.run_window}}, Mirsad screened {{int:counts.screened_total}} links across the four channels and flagged {{int:counts.flagged_total}}: {{counts.flagged_by_channel.feeds}} from the threat feeds and {{counts.flagged_by_channel.certificates}} from the certificate stream (emirates-airlines.battery.cam, which places the Emirates airline name on an unrelated domain). The search and map channels produced candidates but no flags under the two-signal policy. Testing exposed and fixed five problems:

- address-only flags on ordinary business sites, fixed by the two-signal policy and host-only brand matching;
- stale summaries that named brands a case no longer had, fixed by the fact check and rewriting on rescore;
- the certificate stream saturating VirtualBox's network when it ran in the sandbox, fixed by running it on the host during a run only;
- short brand tokens matching ordinary words in thousands of certificates, fixed by the stricter certificate check;
- long retry loops while crt.sh was down, fixed by stopping after two failed queries.

## 10. Limitations and future work

Training used samples of up to 200,000 rows per experiment. The evidence rules are hand-set floors; with a few hundred analyst decisions they should be learned and calibrated. Of the {{app.brands}} protected brands, only {{app.brands_verified}} have official domains verified from a source, and a deployment needs each brand to confirm its domains and phone numbers. Search ads vary by time and location, so a deployment should query from UAE locations on a schedule and add the Google Ads Transparency Center. Free service tiers (OpenPhish community, VirusTotal public) are non-commercial. With more time, the next steps are learning the second stage from officer decisions, Arabic-script and punycode lookalikes at scale, registrar abuse APIs, and a 90-day pilot with the Cybercrime unit that measures the time from a new certificate to a takedown.

## 11. Use of AI tools

The team chose the challenge, the approach, the scope, the data sources, the design direction, and every product decision. Anthropic's Claude Code helped with research about datasets and UAE fraud context; implemented the prototype and experiments. The team reviewed the results and is responsible for the submission.

## References

[1] Omolara, A.E. and Alawida, M. (2025). DaE2: Unmasking malicious URLs by leveraging diverse and efficient ensemble machine learning for online security. Computers & Security 148, 104170. https://doi.org/10.1016/j.cose.2024.104170

[2] Lin, Y., Liu, R., Divakaran, D.M., Ng, J.Y., Chan, Q.Z., Lu, Y., Si, Y., Zhang, F., and Dong, J.S. (2021). Phishpedia: A hybrid deep learning based approach to visually identify phishing webpages. USENIX Security Symposium. Code: https://github.com/lindsey98/Phishpedia

[3] PhreshPhish dataset. Hugging Face, phreshphish/phreshphish, CC BY 4.0.

[4] malicious_phish dataset. Kaggle, sid321axn, "Malicious URLs dataset", CC0.

[5] certstream-server-go, version 1.10.1. https://github.com/d-Rickyy-b/certstream-server-go (MIT).

[6] Federal Decree-Law No. 34 of 2021 on Countering Rumours and Cybercrimes, United Arab Emirates (English translation hosted by ADGM; the Arabic text is authoritative).

[7] Federal Decree-Law No. 45 of 2021 on the Protection of Personal Data, United Arab Emirates.
