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

This Space hosts the public demo of Mirsad, the Abu Dhabi University team's entry in the ScamShield AI hackathon (Abu Dhabi Police and 42 Abu Dhabi, November 2026). Mirsad watches search results and ads, map listings, new website certificates, and public phishing feeds for links that imitate UAE brands, scores each link with a four-ensemble URL model, and gives a police analyst a ranked queue with evidence and downloadable reports in English and Arabic.

The demo holds real cases from the team's lab runs and from public phishing feeds, with victim details removed from every link, and five invented demo links on the reserved `.example` domain. This server never opens a suspect page; page capture runs only in an isolated sandbox VM in the lab.

The team is Muhammet Yalkapov (team lead), Sulaymon Sadullo, and Ahmed Mohamed Almheiri, all of Abu Dhabi University. Dr. Moatsum Alawida of Abu Dhabi University is the academic supervisor. The detection model follows the DaE2 ensemble design (Omolara and Alawida, Computers & Security 148, 2025, https://doi.org/10.1016/j.cose.2024.104170).

The source code, documentation, and technical report are on GitHub: https://github.com/muhammet-tm/mirsad
