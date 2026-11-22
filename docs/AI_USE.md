# Use of AI tools

Draft for the team's review; the team decides the final wording.

The team chose the challenge, the approach (building on the DaE2 ensemble with the paper's corresponding author as academic mentor), the scope, the data sources, the design direction, and every product decision. Claude (Anthropic), used through Claude Code, helped research the paper, datasets, data sources, and UAE fraud context; wrote and tested the code under the team's direction; ran the experiments; and drafted the documents and the presentation. The team reviewed the results and is responsible for the submission.

Inside the product, a language model writes the plain-language case summary: Jais 3 (MBZUAI Institute of Foundation Models, built in the UAE) by default, or Falcon (Technology Innovation Institute) running locally in the sandbox VM. The summary model receives only facts that Mirsad has already established and never decides whether a link is fraudulent.
