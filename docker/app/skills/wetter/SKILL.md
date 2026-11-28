---
name: wetter
description: "Weather questions (weather, temperature outside, rain, snow, wind, frost, forecast, official warnings) ALWAYS answered with the tool mcp__wetter__wetter, never guessed, never via web search. Wetterfragen IMMER mit mcp__wetter__wetter beantworten."
version: 1.0.0
metadata:
  hermes:
    tags: [weather, wetter, forecast, dwd, nuorb]
    category: nuorb
---

# Weather / Wetter

## When to Use
Any question about the weather at the user's place: "How is the weather?", "Is it cold outside?", "Will it rain
tomorrow?", "Do I need a jacket at the weekend?", "Are there any weather warnings?".
Jede Frage zum Wetter am Ort des Nutzers: "Wie ist das Wetter?", "Regnet es morgen?", "Gibt es Unwetterwarnungen?".

## Procedure
1. Call `mcp__wetter__wetter` without any text before it. `zeitraum`:
   - `jetzt`: right now (default)
   - `heute`: rest of today
   - `morgen`: tomorrow
   - `woche`: next days, weekend, a weekday
   - `warnungen`: official warnings
2. The result is a finished sentence with numbers written out. Speak it almost word for word, keep the source it
   names (for example "German Weather Service" or "Open-Meteo"), do not convert or round numbers, add nothing.
3. For a yes/no question ("Will it rain?") a short "Yes" or "No" first is fine, then the sentence.

## Pitfalls
- Official warnings are quoted unchanged. Do not rephrase or shorten them.
- If the tool says weather is not set up or not reachable, say so honestly and do not invent values.
