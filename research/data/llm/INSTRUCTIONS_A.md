You are a forecaster in a controlled experiment. You were given a BATCH number and a MODEL tag.

Read the JSON file /Users/takakhoo/Dev/prediction-market-research-agent/research/data/llm/questions/batch{BATCH}_A.json. It holds binary prediction-market questions. For each item, "today" is the date you are forecasting on. Estimate the probability that the question resolves YES under its resolution rules.

Strict rules: after this instruction file, use NO tools except one Read of that question file and one Write of your answers. Do not search the web, fetch pages, run shell commands, or open any other file. Use only your own knowledge and reasoning (base rates, time remaining until scheduled_end, the exact resolution rules).

Write a JSON list to /Users/takakhoo/Dev/prediction-market-research-agent/research/data/llm/forecasts/batch{BATCH}_A_{MODEL}.json with one object per question: {"qid": "...", "p": <probability of YES between 0.01 and 0.99>}. Include every qid exactly once. Then reply with the single word: done
