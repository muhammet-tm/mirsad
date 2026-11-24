---
title: Mirsad
colorFrom: blue
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
license: other
short_description: Finds fraudulent links that imitate UAE brands
---

# Mirsad (مرصاد)

Public demo of Mirsad, the ScamShield AI hackathon entry from Abu Dhabi University (42 Abu Dhabi and Abu Dhabi Police, November 2026). Mirsad watches search results and ads, map listings, new website certificates, and public phishing feeds for links that imitate UAE brands, scores each link with a four-ensemble URL model, and gives a police analyst a ranked queue with evidence and downloadable reports in English and Arabic.

What this demo holds: real cases from the team's lab runs and from public phishing feeds, with victim details removed from every link, and five invented demo links on the reserved `.example` domain. This server never opens a suspect page; page capture runs only in an isolated sandbox VM in the lab.

Source code, documentation, and the technical report: https://github.com/muhammet-tm/mirsad
