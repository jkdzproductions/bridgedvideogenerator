"""Instructions for the one subagent that reads the printed numbers off one graph image."""


def build_reading_prompt(image_path: str, italic_text: str) -> str:
    return f"""You are reading the numbers printed on one graph image for a documentary video. \
The script phrase this graph belongs to is: "{italic_text}".

Use your Read tool to view the image at this absolute path: {image_path}
Do not invoke any skill, and do not open any other file or web page.

Report ONLY what is legibly printed on the image:
- Every data value that is printed as a number next to its label (a bar's value, a point's \
value, a country's or region's value on a map, a printed average or total). Use the label \
exactly as printed (keep abbreviations such as "DOM" or "PRY" as they are).
- "display" is the value exactly as printed (e.g. "$8K"); "value" is that same number as a \
plain number in the unit the graph uses (e.g. 8000 for "$8K", 3.5 for "3.5%").
- If a printed value is small, blurry, cut off or ambiguous and you are not sure of every \
character, still list it, with your best reading in "display", "value": null and \
"readable": false. Never fill in a value that is not printed; never estimate a value from a \
bar's length, a line's position or a colour.
- Axis tick labels and colour-legend endpoints are scale markings, not data values: leave them \
out of "values" (mention a legend's range in "notes" if it helps).
- "source_line" is the printed source credit exactly as printed (e.g. "Source: IMF October \
2024 World Economic Outlook"), not the name or logo of whoever published the image; null if \
no source is printed.
- If the image looks rotated or mirrored, read it anyway and say so in "notes".

Report numbers only: no opinions, no interpretation of what the numbers mean, and nothing \
about the image's colours, fonts or layout beyond what "graph_kind" needs.

Respond with ONLY a JSON object, no other text, with exactly these keys:
{{
  "title": "<printed title, or null>",
  "subtitle": "<printed subtitle, or null>",
  "graph_kind": "<one short phrase, e.g. bar chart, line chart, choropleth map, table>",
  "unit": "<what the numbers measure and their unit, e.g. GDP per capita, US dollars>",
  "source_line": "<printed source credit, or null>",
  "values": [
    {{"label": "<label as printed>", "display": "<value as printed>", "value": <number or null>, "readable": <true or false>}}
  ],
  "notes": "<anything a fact-checker should know, or null>"
}}
"""
