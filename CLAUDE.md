# Bridged Video Generator — Shot List Generation Workflow

Run this from a Claude Code session in this project directory. Inputs: a script file and its
voiceover audio file. The script is either a Word `.docx` — graphic moments in *italic*; an
italic phrase that is also a hyperlink either points at a graph image, whose printed numbers
become that graphic, or at a web page with a `#:~:text=` highlight, which becomes a page
highlight; a hyperlink on **non-italic** text that points straight at an image file (PNG, JPEG, GIF
or WebP) shows that image exactly as it is, full frame, for exactly the time the phrase is spoken
(a blurred, darkened copy of the image fills any leftover space; no redrawing, no caption, no
number reading); **bold** text marks a talking-head placeholder (the final video shows a silent black
screen for exactly the time it is spoken) — or a `.txt`/`.md` file with `*...*` around each
graphic span and `**...**` around each talking-head span.

**What the linked-graph feature does and does not guarantee.**

- Only `.docx`, `.txt` and `.md` scripts are supported (not PDF). Only an italic phrase that is
  also a hyperlink becomes a linked graph or a page highlight (a non-italic link to an image file
  is a show-as-is image: see the Show-as-is images bullet). An image link (the link points
  directly at a PNG, JPEG, GIF or WebP file, not a PDF, not a picture pasted into the Word file)
  is a graph; a web-page link ending in `#:~:text=` is a page highlight; a web-page link without
  a highlight is skipped (its phrase then becomes an ordinary graphic built from its own text).
  A hyperlink edge is a span edge: italic text with a link and italic text without a link (or
  with a different link) next to each other are two separate spans, so only the linked one
  becomes a linked graph or page highlight and the other stays an ordinary graphic. A link that
  starts or ends in the middle of a word stops Step 1a (start and end a link at a word boundary).
  A link on text that is not italic is ignored and reported in Step 7, unless it points straight
  at an image file (see Show-as-is images); a link that runs past the italic text it started on
  (the rest of the same hyperlink, on non-italic text) is still ignored and reported. A phrase that is both bold
  and italic stops the run with an error, and any italics used for emphasis will become graphics,
  so italicize only real graphic moments.
- `italic_index` (in `graph_links.json`, the reading prompts and responses) is the index among the
  italic (graphic) spans.
- **A linked graph must be recreated in full.** The reading step copies only numbers printed on the image and drops axis
  ticks as scale markings, so a line or bar chart with few printed numbers would come out nearly empty (one dot, no line).
  After Step 1b-iii, compare the readings with what the image shows. If the image has a line or bars with many points, or
  axis ticks, and the reader returned only a few values, STOP and tell Josh before Step 3, then recreate the whole chart:
  trace the points from the image (calibrate against its axis tick labels, round to about 1,000, keep any printed figure
  exact), put the axis ticks and gridlines in the director's data, and say in the data note that the other points are
  traced from the line and not printed figures. Never ship a graph that shows less than the linked image, and never one
  that shows MORE: recreate only what the image shows, with no labels, titles or text of your own (for example no value
  label beside an end dot and no axis title unless the original has them). Before approving, compare the finished
  graphic with the original image element by element.
- The numbers come from a subagent reading the image, so they are unverified drafts. Step 7
  flags every one as "read from an image — verify against the source before publishing" and
  lists the unreadable ones (which are left out of the graphic); Josh should check them.
- That the director builds a linked graphic from ONLY the provided values (no extra, invented
  or rounded-away numbers) is enforced by the director prompt's instructions, not verified by
  code. The only code check is `check_linked_graphic_data` in Step 6: a linked graphic's `data`
  must contain something besides a note or a source. Do not describe the values as verified.
- The director is held to the graph's values by its instructions only. The one code check is
  that a linked graphic's data has something beyond a note or a source; it does not verify the
  numbers.
- Step 1b-i downloads any http/https image URL the script contains, including local or
  private-network addresses. That is fine for Josh's own scripts; do not run scripts from
  untrusted sources.
- **Page highlights.** An italic phrase that is also a hyperlink to a web page whose URL ends in
  `#:~:text=...` (Chrome's "Copy link to highlight") becomes a page highlight: Step 1c opens the
  page in a real browser, finds the highlighted words, hides popups, blurs the page (images much
  more than text) and paints the passage sharp with a green highlight, saving two stills per link
  in `page_stills/`. Stage 4 turns them into a clip (highlight fade-in, slow push-in) for exactly
  the spoken time; Stage 3 and the design system are not involved. An italic link to a web page
  WITHOUT a highlight is skipped and listed in Step 7, but its italic phrase stays a graphic span,
  so it is still built as an ordinary graphic from its own text unless the link is replaced with
  a "Copy link to highlight" URL.
  Step 1c STOPs, listing the link and reason, if the page cannot load, is paywalled or blocked,
  has no readable text, or the highlighted words are not found. Popups are hidden by heuristics,
  so Step 7 prints each still's path and anything it could not clear: open the stills and look.
  Needs the `page` extra and Chromium: `.venv/bin/pip install -e ".[dev,align,youtube,envato,docx,page]"`
  and `.venv/bin/playwright install chromium`. Like image downloads, page loads do not block
  private-network addresses: Josh's own scripts only.
- **Show-as-is images.** A hyperlink on text that is NOT italic and NOT bold, whose URL path ends
  in `.png`, `.jpg`, `.jpeg`, `.gif` or `.webp`, shows that image exactly as it is for exactly the
  time the phrase is spoken. A non-italic link to anything else, a bold link and a link on
  whitespace only stay ignored and are reported in Step 7. Step 1d downloads each image with the
  same checks as graph images (at most 15 MB, at most 8000 pixels per side, real image bytes) and
  STOPs naming the phrase and the URL if one fails. An image phrase must be separated from any
  other italic, bold or linked-image phrase by a space, or Step 1a stops with an error. There is
  no Step 7 section for these images (only the beat count). Like image downloads, Step 1d does not
  block private-network addresses: Josh's own scripts only. `.txt`/`.md` scripts have no links, so
  they cannot carry one.

Every command below takes its file paths as trailing `sys.argv` arguments — substitute the
real paths for `<script_path>` / `<audio_path>` at the end of the command; do not edit the
Python inside the quotes. From Step 1a on, every Stage 1 command reads `script_marked.txt`
(written by Step 1a), never the original script file.

## Steps

1. Read the script file path and the audio file path from the user's message.

1a. Turn the script into `script_marked.txt` (the text, with `*...*` around every graphic span
   and `**...**` around every talking-head span, that every later step reads), `graph_links.json`
   (the italic phrases that link to a graph image), `page_links.json` (the italic phrases whose
   link has a `#:~:text=` highlight), `image_links.json` (the non-italic phrases that link to an
   image file, shown as-is) and `ignored_links.json` (other links on text that is not italic — not graphics, but reported
   in Step 7). A `.txt`/`.md` script is copied unchanged with no links:

   ```bash
   .venv/bin/python -c "
   import sys
   from script_input.prepare import prepare_script_input
   from shot_list.markup import parse_markup
   result = prepare_script_input(sys.argv[1])
   parsed = parse_markup(result.marked_text)
   print('script_marked.txt written:', len(parsed.graphic_spans), 'graphic spans,',
         len(parsed.talking_head_spans), 'talking-head spans,', len(result.links), 'linked graphs,',
         len(result.page_links), 'page highlights,', len(result.image_links), 'show-as-is images,',
         len(result.ignored_links), 'links on non-italic text (ignored)')
   " <script_path>
   ```

   A `.docx` needs the `docx` extra (`.venv/bin/pip install -e ".[dev,align,youtube,envato,docx]"`);
   without it this STOPs with `ModuleNotFoundError: No module named 'docx'` — install it; never
   convert the file by hand. If this raises `DocxScriptError` (a phrase that is both bold and italic, a literal `*`
   in the text, a linked image phrase touching another marked phrase, a link that starts or ends in the middle of an italic word, an italic link that is not http(s)
   such as `mailto:`, an italic link whose `#:~:text=` highlight is malformed, a table, an empty document, or a file that is not really a `.docx`) or
   `ValueError` (an unbalanced `*` or `**` in a text script, an italic or bold that starts in the
   middle of a word such as after a quote or `$` — italicize the WHOLE word, including a leading
   quote or `$` — or an unsupported file type such as a PDF),
   STOP and report the exact message — it names the text to fix in the script.

1b. Linked-graph intake. Always run 1b-i; it clears the previous video's graph files.

   i. Download every linked graph image and write one reading prompt per graph:

      ```bash
      .venv/bin/python -c "
      import json
      from graph_intake.build import prepare_graph_readings
      manifest = prepare_graph_readings(json.load(open('graph_links.json')))
      for m in manifest:
          print('graphic span', m['italic_index'], repr(m['italic_text']), '->', m['image_path'],
                '(%dx%d)' % (m['width'], m['height']), '- prompt: graph_reading_prompt_%d.txt' % m['italic_index'])
      print(len(manifest), 'linked graphs downloaded')
      import json; print(len(json.load(open('skipped_page_links.json'))), 'web-page links without a highlight skipped (listed in Step 7; their phrases still become ordinary graphics)')
      "
      ```

      Always run 1b-i right after 1a (it rewrites `graph_links.json` and `skipped_page_links.json`;
      re-running it alone would lose the skipped-link list). To redo it, re-run 1a first.

      If it prints `0 linked graphs downloaded`, go straight to Step 1c (it has already written
      an empty `graph_readings.json`). If it raises `GraphDownloadError`, STOP and report the
      exact message (it names the italic phrase and the URL): an image link must point directly at a
      PNG, JPEG, GIF or WebP image file (not a PDF), at most 15 MB and at most
      8000 pixels per side. A link that turns out to be a web page (the server sends HTML) is NOT
      an error: it is skipped, written to `skipped_page_links.json`, and removed from
      `graph_links.json` (its italic phrase still becomes an ordinary graphic).

   ii. For EACH `graphic span <italic_index>` line printed above, spawn ONE subagent (Agent tool,
      `model: "opus"`) with `graph_reading_prompt_<italic_index>.txt`'s content as its full
      instructions. It must have Read tool access (it views the image itself). Save its raw
      text response to `graph_reading_response_<italic_index>.txt`. Do not view the image
      yourself, edit the response, or fill in any value.

   iii. Validate every reading and write `graph_readings.json`:

      ```bash
      .venv/bin/python -c "
      from graph_intake.build import collect_graph_readings
      readings = collect_graph_readings()
      print(len(readings), 'graph readings validated; graph_readings.json written')
      "
      ```

      If this raises `GraphReadingError`, STOP and report the exact message (it names the italic
      phrase) — do not hand-patch the response, quietly re-run the subagent, or supply values
      yourself. "zero readable values" means no number on the image was legible: tell the user
      so they can fix the link.

1c. Page-highlight intake. Always run this (never skip it, even with no page links: Steps 3 and 7
   read `page_readings.json`); Step 1a clears the previous video's `page_readings.json` and stills.

   ```bash
   .venv/bin/python -c "
   import json
   from page_intake.build import prepare_page_readings
   readings = prepare_page_readings(json.load(open('page_links.json')))
   for i, r in sorted(readings.items()):
       print('graphic span', i, repr(r['italic_text']), '->', r['still_path'], '| passage:', r['passage'])
       if r['uncovered']:
           print('   could not clear:', ', '.join(r['uncovered']))
   print(len(readings), 'page highlights captured')
   "
   ```

   If it prints `0 page highlights captured`, go to Step 2. If it raises `PageCaptureError`, STOP and
   report the exact message (it names the italic phrase, the URL and the reason: could not load,
   HTTP error, highlighted words not found). Do not retry with a different approach, edit the
   URL, or fill in a still by hand. If it raises `ModuleNotFoundError: No module named
   'playwright'` (or `PIL`), install the `page` extra as shown above; never skip the step.

1d. Show-as-is image intake. Always run this (never skip it, even with no image links: Steps 3 and 6 read `image_readings.json`); Step 1a clears the previous video's `image_readings.json` and `image_stills/`.

   ```bash
   .venv/bin/python -c "
   import json
   from image_intake.build import prepare_image_readings
   readings = prepare_image_readings(json.load(open('image_links.json')))
   for i, r in sorted(readings.items()):
       print('graphic span', i, repr(r['italic_text']), '->', r['still_path'], '(%dx%d)' % (r['width'], r['height']))
   print(len(readings), 'show-as-is images fetched')
   "
   ```

   If it raises `ImageIntakeError`, STOP and report the exact message (it names the phrase and the
   URL: HTTP error, Cloudflare block, not an image, too big). Do not retry another way, swap the
   URL or fill the image in by hand. A site that blocks scripts needs the image saved from the
   browser and linked from a host that allows direct downloads.

2. Run alignment against the **markup-stripped** script text — the audio has no spoken
   asterisks, so aligning against the raw file (still containing `*`/`**`) corrupts every word
   next to a marked span (this can take a while for a full script — it's a real Whisper model run).
   This also records the audio file's **real duration** (not the last word's end — there is
   usually trailing silence), which Step 6 uses as the shot list's total length:

   ```bash
   .venv/bin/python -c "
   from shot_list.align import align_words
   from shot_list.markup import parse_markup
   import json, sys, dataclasses
   script_text = open(sys.argv[1]).read()
   parsed = parse_markup(script_text)
   alignment = align_words(sys.argv[2], parsed.plain_text)
   json.dump({'audio_duration': alignment.audio_duration,
              'words': [dataclasses.asdict(t) for t in alignment.words]},
             open('word_timings.json', 'w'))
   " script_marked.txt <audio_path>
   ```

   If this raises `ValueError: alignment quality too low...` or `ValueError: alignment
   mismatch...`, STOP and report it to the user — the audio doesn't match the script
   (wrong file, truncated recording, or script edited after recording). Do not proceed with
   a shot list built on bad alignment (Global Constraint: fail loudly).

3. Parse markup and build the director prompt (graphic segments that link to a graph get a
   PROVIDED DATA block with the values read in Step 1b; other segments are prompted as before):

   ```bash
   .venv/bin/python -c "
   from shot_list.markup import parse_markup
   from shot_list.build import prepare_director_input
   from graph_intake.build import load_graph_readings
   from page_intake.build import load_page_readings
   from image_intake.build import load_image_readings
   import json, sys
   script_text = open(sys.argv[1]).read()
   parsed = parse_markup(script_text)
   graph_readings = load_graph_readings('graph_readings.json', 'graph_links.json')
   page_readings = load_page_readings('page_readings.json', 'page_links.json')
   image_readings = load_image_readings('image_readings.json', 'image_links.json')
   segments, prompt = prepare_director_input(parsed.plain_text, parsed.graphic_spans, graph_readings,
                                              parsed.talking_head_spans, page_readings, image_readings)
   json.dump({'plain_text': parsed.plain_text, 'prompt': prompt,
              'segments': [{'kind': s.kind, 'text': s.text} for s in segments]},
             open('director_input.json', 'w'))
   " script_marked.txt
   ```

   If this raises (e.g. an italic or bold span that contains no whole word), STOP and report it — fix
   the markup before spending a director call on it. A `ValueError` saying the graph readings
   are "from another script" / "left over from another script" means `graph_readings.json`
   does not belong to this `script_marked.txt`: re-run Stage 1 from Step 1a. A `ValueError` saying
   `page_readings.json` is "left over from another script" means the same: re-run Stage 1 from
   Step 1a. So does a `ValueError` saying `image_readings.json` is "left over from another script".

4. Read `director_input.json`. Spawn ONE subagent (Agent tool, `model: "opus"`) with the
   `prompt` field as its full instructions. The subagent will Read the design-system rules
   snapshot (`design_system/bridged-design-system.md`, by absolute path) itself as its
   first step (the prompt tells it to) — it invokes no skill, and you do not pre-load anything
   for it. Talking-head segments (`**...**`) are listed for context only; the director gives them
   a marker-only entry (`{"index": i, "type": "talking_head"}`) with no footage or graphic.
   Page-highlight segments (`page_highlight`) are listed for context only; the director answers
   them with `{"index": i, "type": "page_highlight"}`. Image segments (`image`) are listed for
   context only; the director answers them with `{"index": i, "type": "image"}`.

5. Save the subagent's raw text response (should be pure JSON) to `director_response.json`
   for the next step to read.

6. Validate the subagent's response and assemble the shot list:

   ```bash
   .venv/bin/python -c "
   from shot_list.markup import parse_markup
   from shot_list.build import prepare_director_input, assemble_shot_list
   from shot_list.director_output import parse_director_output, check_linked_graphic_data
   from shot_list.models import validate_shot_list
   from shot_list.align import WordTiming
   from graph_intake.build import load_graph_readings
   from page_intake.build import load_page_readings
   from image_intake.build import load_image_readings
   import json, sys, dataclasses

   script_text = open(sys.argv[1]).read()
   parsed = parse_markup(script_text)
   graph_readings = load_graph_readings('graph_readings.json', 'graph_links.json')
   page_readings = load_page_readings('page_readings.json', 'page_links.json')
   image_readings = load_image_readings('image_readings.json', 'image_links.json')
   segments, _ = prepare_director_input(parsed.plain_text, parsed.graphic_spans, graph_readings,
                                              parsed.talking_head_spans, page_readings, image_readings)

   alignment = json.load(open('word_timings.json'))
   word_timings = [WordTiming(**t) for t in alignment['words']]
   total_duration = alignment['audio_duration']  # real audio length from Step 2

   raw_director_output = open('director_response.json').read()  # subagent's raw response
   specs = parse_director_output(raw_director_output, segments)
   check_linked_graphic_data(segments, specs, graph_readings)

   shot_list = assemble_shot_list(segments, parsed.plain_text, word_timings, specs, total_duration)
   validate_shot_list(shot_list)

   json.dump(dataclasses.asdict(shot_list), open('shot_list.json', 'w'), indent=2)
   print(f'shot_list.json written: {len(shot_list.beats)} beats, {total_duration:.1f}s')
   " script_marked.txt
   ```

   If `parse_director_output`, `check_linked_graphic_data`, `assemble_shot_list`, or
   `validate_shot_list` raises: STOP, report the exact error (it names the offending segment
   index, marked phrase or coverage gap) — do not hand-patch the JSON and continue silently
   (Global Constraint: fail loudly). An error saying the word timings don't match the script
   means `script_marked.txt` changed after Step 2 (Step 1a was re-run, perhaps on an edited
   script) — re-run from Step 2.

6b. Per-cut footage planning. The director wrote ONE footage idea per plain segment, but a segment
   is cut into shots of at most 6 seconds that would all inherit it. This step gives every
   footage cut its own search, based on the words spoken during that cut. Run it after Step 6
   has written `shot_list.json`:

   i. Build the planner prompt:

      ```bash
      .venv/bin/python -c "
      import json
      from shot_list.align import WordTiming
      from shot_list.cut_planner import build_cut_planner_prompt, footage_cuts, load_shot_list

      shot_list = load_shot_list('shot_list.json')
      word_timings = [WordTiming(**t) for t in json.load(open('word_timings.json'))['words']]
      cuts = footage_cuts(shot_list, word_timings)
      open('cut_planner_prompt.txt', 'w').write(build_cut_planner_prompt(cuts))
      print(len(cuts), 'footage cuts to plan')
      "
      ```

      If it prints `0 footage cuts to plan`, skip the rest of Step 6b.

   ii. Spawn ONE subagent (Agent tool, `model: "opus"`) with `cut_planner_prompt.txt`'s content
      as its full instructions. Save its raw text response to `cut_planner_response.json`. It
      needs no tools.

   iii. Validate the response and update `shot_list.json` (written only after every check passes):

      ```bash
      .venv/bin/python -c "
      import dataclasses, json
      from shot_list.align import WordTiming
      from shot_list.cut_planner import apply_cut_plans, footage_cuts, load_shot_list, parse_cut_planner_output

      shot_list = load_shot_list('shot_list.json')
      word_timings = [WordTiming(**t) for t in json.load(open('word_timings.json'))['words']]
      cuts = footage_cuts(shot_list, word_timings)
      plans = parse_cut_planner_output(open('cut_planner_response.json').read(), cuts)
      updated = apply_cut_plans(shot_list, cuts, plans)
      json.dump(dataclasses.asdict(updated), open('shot_list.json', 'w'), indent=2)
      for cut, plan in zip(cuts, plans):
          era = plan['era'] if plan['era'] is not None else 'modern'
          print(f'{cut.start:.1f}-{cut.end:.1f}s \"{cut.words}\" -> {plan[\"query\"]!r} | era: {era}'
                + (f' | archival: {plan[\"archival_query\"]!r}' if plan['archival_query'] else ''))
      "
      ```

      If this raises `CutPlannerOutputError`, STOP and report the exact message — do not
      hand-patch the response or quietly re-run the subagent. `shot_list.json` is unchanged when
      it raises. Show the printed cut-by-cut plan in the Step 7 report.

   The planner also tags every cut with an `era` (the year the words are about, or `modern`); a cut about a year before 1960 gets `archival_query` and `archival_broad_query` and is sourced from archives in Stage 2 instead of stock sites (except before 1839, where the judge may also pick stock). Cuts about a year before 1900 are **mixed** beats (they also get archival queries): before 1839 the judge chooses between real historical artwork (Met open access, Library of Congress prints) and the ordinary stock footage (stock only when nothing in it contradicts the period); from 1839 to 1899 it chooses among photographs and artwork (no stock); cuts from 1900 to 1959 keep the film-then-photos flow. A hand-colored lithograph of a battle counts as artwork. In Step 7, tell Josh how many cuts are archival.

7. Report to the user: total beats, how many are footage vs. graphic, how many are page highlights, how many are show-as-is images, how many are talking-head
   (black screen) beats, the per-cut footage plan printed by Step 6b, and the path to
   `shot_list.json`, followed by the linked-graph section printed by:

   ```bash
   .venv/bin/python -c "
   import json
   from graph_intake.build import load_graph_readings
   from graph_intake.report import build_linked_graphs_report
   print(build_linked_graphs_report(load_graph_readings('graph_readings.json', 'graph_links.json'),
                                    json.load(open('ignored_links.json'))))
   "
   ```

   Show that section to the user as printed — every value read from an image, the unreadable
   ones, and the flag "read from an image — verify against the source before publishing" —
   plus the links on non-italic text that were ignored. Then print the page-highlights section:

   ```bash
   .venv/bin/python -c "
   import json
   from page_intake.build import load_page_readings
   from page_intake.report import build_page_highlights_report
   print(build_page_highlights_report(load_page_readings('page_readings.json', 'page_links.json'),
                                      json.load(open('skipped_page_links.json'))))
   "
   ```

   Show that section as printed. Tell Josh to open each still (the path is printed) before the
   run continues, and to say if a popup, a graphic photo or anything else needs fixing.
   There is no approval pause: the run
   continues to Stage 2/3. `shot_list.json` is the deliverable for this stage — footage
   sourcing and motion graphics consume this file.

---

# Stage 2 (Combined) — Footage Sourcing

Run this after Stage 1 has produced `shot_list.json`. Requires `PEXELS_API_KEY` and
`YOUTUBE_API_KEY` in `.env` (loaded via `python-dotenv`), plus the one-time Envato profile setup
below. Every footage beat now searches Pexels, YouTube, and Envato Elements in parallel and lets
one subagent pick the best clip across all three sources — this replaces the old separate
Pexels-only and YouTube-only stages.

**Before the first run — Envato one-time setup.** Unlike Pexels/YouTube, Envato sourcing needs no
API key (none exists for the Elements stock-video catalog — Envato Market has one, but that's a
different product) and no quota tracking (downloads are unlimited under Josh's subscription; see
`docs/superpowers/specs/2026-09-28-envato-footage-sourcing-design.md`'s "What's verified live"
section for the confirmed finding — do not build an Envato analog of `footage/quota.py` for a
problem that doesn't exist here). It does need the `envato` extra installed
(`.venv/bin/pip install -e ".[dev,align,youtube,envato]"` then
`.venv/bin/playwright install chromium`) — without it every beat STOPs immediately with
`ModuleNotFoundError: No module named 'playwright'`, deliberately: a missing dependency is a setup
bug to fix, never something to quietly treat as "0 Envato candidates." It also needs
`ENVATO_PROFILE_DIR` in `.env` (default:
`.envato_automation_profile`), pointing at a Playwright persistent-context profile directory that
has already been logged into Envato once, out-of-band, by running
`.venv/bin/python tests/fixtures/envato_automation_spike.py` and logging in manually when it
pauses and waits — Stage 2 itself never triggers that login, the same way Stage 3 never triggers
`/design-sync`. Log in with email/password, not "Sign in with Google" — Google's own bot-detection
blocks its own OAuth flow inside an automated Playwright browser (confirmed live during this
feature's build; the block is on Google's end, unrelated to Envato).

**Stage 2 remains fully unattended, Envato included.** Unlike Stage 3 (which requires an
interactive `claude-in-chrome` session for its subjective design review — if you just read that
note, it does NOT carry over here), Envato sourcing is driven by a Python-launched Playwright
browser exactly like every other piece of Stage 2, so this whole stage still runs as an unattended
background job, the same as it always has. This was confirmed live in Task 1's spike: no
bot-detection wall blocks a non-interactive, Python-driven browser against Envato, unlike the
Cloudflare wall on claude.ai that forced Stage 3 to become interactive-only. See
`docs/superpowers/specs/2026-09-28-envato-footage-sourcing-design.md` for the full finding.

**Accepted risk, not re-litigated here:** general YouTube videos are copyrighted to their
uploader, and downloading via `yt-dlp` is separately against YouTube's own Terms of Service.
Josh explicitly confirmed he wants YouTube sourced automatically on every beat, with the channel
exclude-list below as the guardrail — that list must be applied correctly every run.

**Archival cuts (about a period before 1960).** `shot_list.json` footage beats whose `era` is a year before 1960
never run the stock-API search (Pexels, YouTube, Envato) in the photo flow, with one exception: `"artwork_or_stock"` beats (Step 2M) do run it. Step 1 lists them in `archival_beats.json` (each with a `medium`); Step 2A sources the
`"photo"` beats (1900 to 1959): archival film from the Internet Archive when it exists and the judge accepts it (film keeps attention
best), otherwise 1 to 3 real photos from the Library of Congress and Wikimedia Commons (photos always exist; a search that finds
nothing, or a failing archive, STOPs with an `ArchivalSearchError` naming the queries). Step 2M sources the **mixed** beats (era before 1900,
no film search): `"artwork_or_stock"` (before 1839) lets the judge choose between real historical artwork and the ordinary stock footage (accepted
only when nothing in it contradicts the period), and `"photo_or_artwork"` (1839 to 1899) lets it choose among photographs and artwork (no stock).
A hand-colored lithograph of a battle counts as artwork. Artwork comes ONLY from the Met open-access collection and the Library of Congress
(never Wikimedia Commons), so no AI-generated ARTWORK can enter from the artwork sources (they are catalogued collections). Commons photos are
screened heuristically (AI-specific markers in their metadata, and every year in the date field 1960 or earlier) and the judge is told to reject
anything that looks AI-generated; pre-1839 stock footage is checked by the judge only; images Josh supplies himself are his responsibility. If the judge finds nothing acceptable the stage STOPs and Josh supplies a real image (Step 2A-e). Only
public-domain or no-known-restrictions items are used. The result is an ordinary `footage_output/beat_<n>.mp4`, so Stage 4 is unchanged.
Archival cuts in the photo flow use no stock APIs and no YouTube quota, but `"artwork_or_stock"` beats DO run the stock search and spend YouTube quota
(the pre-flight counts them). Nothing waits for Josh: Step 3 writes
`archival_review.html` (every pick with source, year, license and kind artwork/photo/mixed/stock, plus the judge's rejections) for him to open if he wants; to swap a pick or supply your own photos, re-render that one beat with Step 2A-e and re-run Stage 4.
Archive film is mostly 4:3 and low resolution; Stage 4 pads it with black bars like any footage.

Only landscape videos are ever used (the final video is 16:9): YouTube search drops
portrait/square results before scoring and every downloaded YouTube clip is re-checked with
`ffprobe` as a backstop; Pexels searches are landscape-only via its own API parameter already;
Envato's search URL has NO orientation filter, so `_envato_candidates` drops portrait/square items
before scoring using the real width/height `fetch_envato_details` scrapes from each item's detail
page, and every downloaded Envato clip is re-checked with `ffprobe` too (same backstop pattern,
never trusting scraped metadata alone).

**Clip quality currently tops out around 360p for YouTube-sourced clips**, for the same reason
documented before: this venv's Python 3.9 pins an older yt-dlp that needs the lower-quality
`android` client to work around YouTube's SABR-streaming enforcement. Would lift with Python
3.10+ or a PO-token provider.

**YouTube channel size rule.** YouTube candidates from a channel with more than 1,000,000
subscribers are dropped before scoring (exactly 1,000,000 stays), and so are channels that hide
their subscriber count. They count as "excluded channels"; nothing reports them separately.

**YouTube look.** Every YouTube clip that wins a beat is mirrored left-to-right, zoomed in 3%,
given a light film grain and a half-strength vignette (`footage/youtube_look.py`: `ZOOM`,
`GRAIN_STRENGTH`, `VIGNETTE_STRENGTH`) inside
`resolve_combined_winner`, so the saved `footage_output/beat_<n>.mp4` already has it; Pexels and
Envato clips are used as they are. Because of the mirroring, the scoring prompt rejects any YouTube
candidate with readable text in its thumbnail, even small background text. The judge only sees the
thumbnail, so text that appears later in a clip is NOT checked. If the effect fails, the clip is
deleted and Stage 2 stops on that beat, like any other failed download.

**YouTube daily quota.** Each footage beat now always costs ~102 units of quota (100 for the
search, 1 for the channel-size lookup, 1 for the duration/dimension lookup), plus ~8 units once per video for channel
resolution — YouTube runs on every beat, not just when a separate stage was deliberately chosen.
The default daily cap is 10,000 units (resets at midnight Pacific), overridable via
`YOUTUBE_DAILY_QUOTA_UNITS` in `.env`. Before spending anything, Step 1 below checks today's
already-recorded spend (tracked in `youtube_quota_usage.json` at the project root) plus this
video's projected need against that cap, and refuses to start if it won't fit — the raised
error's message gives the exact shortfall.

If a run stops partway through because of quota exhaustion (either `check_preflight` raising
before anything started, or a live 403/`quotaExceeded` from the YouTube API mid-run), do NOT
re-run Step 1 — it resets `used_footage_ids.json` (so later beats could reuse candidates earlier
beats already used), also wipes `archival_work/` and `archival_picks.json`, and re-spends the
channel-resolution quota. Instead, continue Step 2 at the first modern beat in `footage_beats.json`
whose `footage_output/beat_<beat_index>.mp4` doesn't exist yet, and Step 2A at the first archival
beat in `archival_beats.json` whose `footage_output/beat_<n>.mp4` doesn't exist yet (mixed beats resume from Step 2M, the rest from 2A). Before resuming,
check that `used_footage_ids.json` matches the clips already in `footage_output/`: one entry per
modern clip, one `["archive", ...]` entry per archival film beat, one to three per archival photo
beat, one to three `["archive", ...]` entries per mixed beat won by stills (artwork or photos) and one `["<source>", "<id>"]` entry per mixed beat won by stock; if not, tell the user rather than guessing.

## Steps

1. Load `shot_list.json`, extract every footage beat, run the pre-flight quota check, resolve the
   fixed excluded-channel list to real channel IDs (once per video), and reset the per-video
   used-candidate tracker:

   ```bash
   .venv/bin/python -c "
   import json, os, shutil
   from dotenv import load_dotenv
   from shot_list.models import ShotList, beat_from_dict
   from footage.shotlist_integration import archival_beats, footage_beats
   from footage.archival_build import reset_archival_state
   from footage.youtube_channels import EXCLUDED_CHANNEL_URLS, resolve_channel_ids
   from footage.quota import CHANNEL_RESOLUTION_UNITS, DEFAULT_DAILY_QUOTA_UNITS, check_preflight, record_spend

   load_dotenv()
   youtube_api_key = os.environ['YOUTUBE_API_KEY']
   daily_quota = int(os.environ.get('YOUTUBE_DAILY_QUOTA_UNITS', DEFAULT_DAILY_QUOTA_UNITS))

   raw = json.load(open('shot_list.json'))
   beats = [beat_from_dict(b) for b in raw['beats']]
   shot_list = ShotList(beats=beats, duration=raw['duration'])
   pairs = footage_beats(shot_list)
   json.dump(pairs, open('footage_beats.json', 'w'))

   archival = archival_beats(shot_list)
   json.dump(archival, open('archival_beats.json', 'w'))
   durations = {i: beats[i].end - beats[i].start for i, _, _ in pairs}
   durations.update({a['beat_index']: a['end'] - a['start'] for a in archival})
   json.dump(durations, open('beat_durations.json', 'w'))

   # Raises QuotaExceededError with the exact shortfall if this video won't fit in what's left
   # of today's YouTube quota — stops here, before any real API calls or downloads happen.
   stock_mixed = [a for a in archival if a['medium'] == 'artwork_or_stock']
   check_preflight(len(pairs) + len(stock_mixed), 'youtube_quota_usage.json', daily_quota)

   excluded_ids = resolve_channel_ids(EXCLUDED_CHANNEL_URLS, youtube_api_key)
   record_spend(CHANNEL_RESOLUTION_UNITS, 'youtube_quota_usage.json')
   json.dump(list(excluded_ids), open('excluded_channel_ids.json', 'w'))

   # Fresh start for a new video — never re-run this step mid-resume (see above), so this
   # never wipes in-progress work. Placed after shot-list parsing, check_preflight, and
   # resolve_channel_ids all succeed, so a failure at any of those points leaves the previous
   # video's footage_output/ and thumbnails/ untouched.
   shutil.rmtree('footage_output', ignore_errors=True)
   shutil.rmtree('thumbnails', ignore_errors=True)
   reset_archival_state()

   json.dump([], open('used_footage_ids.json', 'w'))
   print(f'{len(pairs)} modern footage beats and {len(archival)} archival beats to source ({len(stock_mixed)} mixed beats also search stock); {len(excluded_ids)} channels excluded')
   "
   ```

   `footage_beats` now returns modern beats only, so `pairs` and the printed count exclude archival beats. The YouTube pre-flight
   counts `len(pairs)` plus only the `"artwork_or_stock"` archival beats (`stock_mixed`, the only archival beats that run the stock search), which is what saves the quota. If the shot list has zero
   modern beats the Step 2 loop is simply empty; `check_preflight(len(pairs) + len(stock_mixed), ...)` is fine with 0.

   A `TypeError` from `beat_from_dict` (a `GraphicSpec`/`FootageSpec`/`PageSpec` argument) means an older-format shot_list.json (from before the
   7-archetype set): STOP and regenerate it with Stage 1.

   If this raises `FileNotFoundError`, `json.JSONDecodeError`, `KeyError`, `TypeError`, or
   `ChannelResolutionError`, STOP and report it — same fail-loud handling as before. If it
   raises `QuotaExceededError`, STOP and report the exact message (units already spent today,
   units this video needs, how many beats would fit) — do not proceed with a partial run or
   silently drop to Pexels-only; tell the user so they can trim beats, wait for tomorrow's
   quota reset, or request a quota increase.

2. Read `footage_beats.json`. For EACH `(beat_index, query, subject)` tuple, in order
   (substitute the real values as trailing `sys.argv` arguments — `query`/`subject` need
   double-quoting since they contain spaces and apostrophes, e.g. the trailing arguments for
   beat 3 look like `" 3 "tokyo subway platform" "Tokyo's subway system"`. Double quotes, not
   single. If a value contains `"`, `$`, or a backtick, escape it with a backslash):

   a. Prepare the combined scoring input (real Pexels + YouTube + Envato search, excluding both
      the fixed channels and any candidate already used earlier in this run), and record the real
      quota this beat's YouTube search just spent. Every beat now searches all three sources in
      parallel for up to 10 total candidates (`PEXELS_SPLIT=4` + `YOUTUBE_SPLIT=3` +
      `ENVATO_SPLIT=3`) — Envato only ever searches its Stock Footage category, never Motion
      Graphics (Global Constraint), and a query that returns zero Envato results (including a
      login/session hiccup or a Playwright error on Envato's side) does not stop the beat; it just
      means fewer than 10 candidates that round, same as any other source coming up short. An
      Envato failure (as opposed to a genuinely empty search) prints a line starting
      `WARNING: Envato contributed 0 candidates ...` naming the real cause — note any you see
      for the Step 3 report:

      ```bash
      .venv/bin/python -c "
      import dataclasses, json, os, sys
      from dotenv import load_dotenv
      from footage.combined_build import prepare_combined_scoring
      from footage.quota import PER_BEAT_UNITS, record_spend

      beat_index, query, subject = sys.argv[1], sys.argv[2], sys.argv[3]
      load_dotenv()
      pexels_api_key = os.environ['PEXELS_API_KEY']
      youtube_api_key = os.environ['YOUTUBE_API_KEY']
      envato_profile_dir = os.environ.get('ENVATO_PROFILE_DIR', '.envato_automation_profile')
      excluded_channel_ids = frozenset(json.load(open('excluded_channel_ids.json')))
      used_ids = frozenset(tuple(pair) for pair in json.load(open('used_footage_ids.json')))

      candidates, prompt = prepare_combined_scoring(
          query=query, subject=subject,
          pexels_api_key=pexels_api_key, youtube_api_key=youtube_api_key,
          excluded_channel_ids=excluded_channel_ids,
          thumbnails_dir=f'thumbnails/beat_{beat_index}',
          envato_profile_dir=envato_profile_dir,
          exclude_ids=used_ids,
      )
      record_spend(PER_BEAT_UNITS, 'youtube_quota_usage.json')

      json.dump(
          [{'source': c.source, 'display_id': c.display_id, 'thumbnail_path': c.thumbnail_path,
            'payload': dataclasses.asdict(c.payload)} for c in candidates],
          open(f'candidates_{beat_index}.json', 'w'),
      )
      open(f'scoring_prompt_{beat_index}.txt', 'w').write(prompt)
      " <beat_index> "<query>" "<subject>"
      ```

      If this raises `ValueError: no candidates found...`, `PexelsError`, or `YouTubeError`,
      STOP and report it — do not skip the beat or substitute a generic query without telling
      the user. (Envato failures never reach here — `prepare_combined_scoring` treats Envato as a
      purely additive source and contributes zero Envato candidates for the beat, with a printed
      `WARNING`, instead of raising; see the note above.) A `YouTubeError` mentioning 403 / `quotaExceeded` means the
      daily quota ran out despite the pre-flight estimate (estimate and live usage can drift): run

      ```bash
      .venv/bin/python -c "
      from dotenv import load_dotenv
      from footage.quota import DEFAULT_DAILY_QUOTA_UNITS, mark_exhausted_today
      import os

      load_dotenv()
      daily_quota = int(os.environ.get('YOUTUBE_DAILY_QUOTA_UNITS', DEFAULT_DAILY_QUOTA_UNITS))
      mark_exhausted_today('youtube_quota_usage.json', daily_quota)
      "
      ```

      (same `.env` / `YOUTUBE_DAILY_QUOTA_UNITS` convention as Step 1 — marking today exhausted
      against the wrong cap would silently defeat a real quota override) so tomorrow's
      pre-flight check reflects reality, then STOP and report which beat to resume from once
      quota resets. Fewer than 10 total candidates (but at least one, from any of the three
      sources) is fine; continue normally.

   b. Spawn ONE subagent (Agent tool) with `scoring_prompt_<beat_index>.txt`'s content as its
      full instructions. The subagent must have Read tool access (to view the thumbnails) — a
      normal Claude Code subagent, no special model requirement.

   c. Save the subagent's raw text response to `scoring_response_<beat_index>.txt`.

   d. Take the subagent's response and validate + download the (duration-clamped, if YouTube or
      Envato) winning clip:

      ```bash
      .venv/bin/python -c "
      import json, os, sys
      from dotenv import load_dotenv
      from footage.combined_build import CombinedCandidate, resolve_combined_winner
      from footage.envato import EnvatoCandidate
      from footage.pexels import PexelsCandidate, VideoFile
      from footage.youtube import YouTubeCandidate
      from footage.scoring_output import NoAcceptableCandidateError, parse_scoring_output

      beat_index = sys.argv[1]
      load_dotenv()
      envato_profile_dir = os.environ.get('ENVATO_PROFILE_DIR', '.envato_automation_profile')
      candidates_data = json.load(open(f'candidates_{beat_index}.json'))
      candidates = []
      for c in candidates_data:
          if c['source'] == 'pexels':
              p = c['payload']
              payload = PexelsCandidate(
                  id=p['id'], url=p['url'], thumbnail_url=p['thumbnail_url'], duration=p['duration'],
                  width=p['width'], height=p['height'],
                  video_files=[VideoFile(**vf) for vf in p['video_files']],
              )
          elif c['source'] == 'envato':
              payload = EnvatoCandidate(**c['payload'])
          else:
              payload = YouTubeCandidate(**c['payload'])
          candidates.append(CombinedCandidate(c['source'], c['display_id'], c['thumbnail_path'], payload))

      raw_response = open(f'scoring_response_{beat_index}.txt').read()
      target_duration = json.load(open('beat_durations.json'))[beat_index]

      try:
          winner_index = parse_scoring_output(raw_response, num_candidates=len(candidates))
      except NoAcceptableCandidateError as e:
          print(f'NO ACCEPTABLE FOOTAGE for beat {beat_index}: {e.reasoning or \"(no reason given)\"}')
          sys.exit(2)

      path = resolve_combined_winner(
          candidates, winner_index, f'footage_output/beat_{beat_index}.mp4', target_duration,
          envato_profile_dir=envato_profile_dir,
      )

      used_ids = json.load(open('used_footage_ids.json'))
      winner = candidates[winner_index]
      used_ids.append([winner.source, winner.display_id])
      json.dump(used_ids, open('used_footage_ids.json', 'w'))
      print(f'beat {beat_index}: downloaded {path} (source={winner.source})')
      " <beat_index>
      ```

      If this exits with status 2 (`NO ACCEPTABLE FOOTAGE`), STOP and flag that specific beat
      to the user (its index, query, subject, and the reasoning printed) — do not re-run the
      scorer yourself or pick a candidate on your own judgment. If `parse_scoring_output` raises
      a `ScoringOutputError` (malformed output, not a considered "none acceptable" verdict),
      STOP and report the exact error. If this raises `YouTubeDownloadError`/`PortraitVideoError`
      (a YouTube or Envato winner — Envato reuses the same landscape backstop probe),
      `EnvatoDownloadError` (an Envato winner), or a Pexels-side download failure, STOP and report
      it with the beat's index, query, subject, and the winning candidate's source/id — do NOT
      silently substitute the next-ranked candidate. No clip file is left behind for that beat,
      and its id is not added to `used_footage_ids.json`.

2A. Read `archival_beats.json`. For EACH beat (a dict with `beat_index`, `start`, `end`, `era`, `subject`, `medium`, `query`,
   `archival_query`, `archival_broad_query`) whose `medium` is `"photo"`, in order, run a-d (beats with another medium go to 2M). Substitute the real `beat_index` as the trailing
   argument.

   a. Search film and write the judging prompt (prints `film candidates: yes` or `no`):

      ```bash
      .venv/bin/python -c "
      import json, sys
      from footage.archival_build import prepare_film
      beat = next(b for b in json.load(open('archival_beats.json')) if b['beat_index'] == int(sys.argv[1]))
      used = json.load(open('used_footage_ids.json'))
      print('film candidates:', 'yes' if prepare_film(beat, used) else 'no')
      " <beat_index>
      ```

      Run this command with a long Bash timeout (`timeout: 600000`): it reads still frames from archive.org
      (up to 5 candidates, 3 frames each, at most 30 s per frame) and prints one progress line per candidate.

      An `ArchiveError`, `ArchivalSearchError`, `ArchivalRenderError` (for example ffmpeg missing) or `ValueError` raised by `prepare_film` (or by `prepare_photos` in c)
      STOPs the stage with the beat index. A transient 5xx, 429 or timeout may be retried once by re-running that
      step; do not skip the beat.

   b. Only when it printed `film candidates: yes`: spawn ONE subagent (Agent tool, `model: "opus"`, because the
      archival judging reads thumbnails and applies the era and graphic rules) with
      `archival_work/film_prompt_<beat_index>.txt`'s content as its full instructions (it needs Read access for the
      thumbnail frames of film, or the thumbnails of photos). Save its raw response to `archival_work/film_response_<beat_index>.txt`, then:

      ```bash
      .venv/bin/python -c "
      import json, sys
      from footage.archival_build import finish_film
      beat = next(b for b in json.load(open('archival_beats.json')) if b['beat_index'] == int(sys.argv[1]))
      raw = open(f'archival_work/film_response_{sys.argv[1]}.txt').read()
      print('film used' if finish_film(beat, raw) else 'no acceptable film')
      " <beat_index>
      ```

      If it prints `film used`, this beat is done; go to the next beat. If a `ScoringOutputError`, `ArchivalRenderError`
      or `ArchiveError` is raised, STOP and report it with the beat index. Do not pick on your own.

   c. If there was no film or none was acceptable, search photos and write the judging prompt (an
      `ArchivalSearchError` here means nothing was found even after broadening: STOP and report it):

      ```bash
      .venv/bin/python -c "
      import json, sys
      from footage.archival_build import prepare_photos
      beat = next(b for b in json.load(open('archival_beats.json')) if b['beat_index'] == int(sys.argv[1]))
      prepare_photos(beat, json.load(open('used_footage_ids.json')))
      print('photo candidates ready')
      " <beat_index>
      ```

   d. Spawn ONE subagent (Agent tool, `model: "opus"`, for the same reason as in b) with `archival_work/photo_prompt_<beat_index>.txt`'s content as
      its full instructions. Save its raw response to `archival_work/photo_response_<beat_index>.txt`, then:

      ```bash
      .venv/bin/python -c "
      import json, sys
      from footage.archival_build import finish_photos
      beat = next(b for b in json.load(open('archival_beats.json')) if b['beat_index'] == int(sys.argv[1]))
      finish_photos(beat, open(f'archival_work/photo_response_{sys.argv[1]}.txt').read())
      print('photos used for beat', sys.argv[1])
      " <beat_index>
      ```

      A `ScoringOutputError` (for example the judge returned no photo at all: photos must always be picked), an
      `ArchiveError` or a render error STOPs the stage with the beat index. When the `ScoringOutputError` is because
      the judge returned no picks (every candidate broke the real-imagery, not-graphic or no-text-screen rules), tell
      Josh the beat index and the judge's reasoning. Josh can send photo files or links; save them locally (real
      archival photos only, tell me the source/license) and run 2A-e for that beat; a show-as-is link in the script
      also works but needs a Stage 1 + Stage 2 redo. Never pick a photo yourself.

   e. Supplying photos yourself (to replace a pick, or when the judge returned no picks). Save the real archival
      photos locally, then render that one beat. The source note is required (where the photos came from and their
      license); it is recorded on the review sheet:

      ```bash
      .venv/bin/python -c "
      import json, sys
      from footage.archival_build import render_manual_photos
      beat = next(b for b in json.load(open('archival_beats.json')) if b['beat_index'] == int(sys.argv[1]))
      render_manual_photos(beat, sys.argv[3:], sys.argv[2])
      print('photos rendered for beat', sys.argv[1])
      " <beat_index> "<source note>" <photo_path> [<photo_path> ...]
      ```

      A missing file or a blank source note raises `ValueError`: STOP and report it. Re-run Stage 4 afterwards.

2M. Mixed beats (`medium` is `"artwork_or_stock"` or `"photo_or_artwork"`). For EACH such beat in `archival_beats.json`, in
   order, run m-a to m-c instead of 2A a-d (there is no film search for them). Substitute the real `beat_index` as the trailing argument.

   m-a. Search artwork, photos and (only for `"artwork_or_stock"`) stock, and write the judging prompt:

      ```bash
      .venv/bin/python -c "
      import json, os, sys
      from dotenv import load_dotenv
      from footage.mixed_build import prepare_mixed
      from footage.quota import PER_BEAT_UNITS, record_spend

      load_dotenv()
      pexels_key = os.environ['PEXELS_API_KEY']
      youtube_key = os.environ['YOUTUBE_API_KEY']
      envato_profile_dir = os.environ.get('ENVATO_PROFILE_DIR', '.envato_automation_profile')
      excluded = json.load(open('excluded_channel_ids.json'))
      beat = next(b for b in json.load(open('archival_beats.json')) if b['beat_index'] == int(sys.argv[1]))
      used = json.load(open('used_footage_ids.json'))
      counts = prepare_mixed(beat, used, pexels_key, youtube_key, frozenset(excluded), envato_profile_dir)
      print('candidates:', counts)
      if beat['medium'] == 'artwork_or_stock':
          record_spend(PER_BEAT_UNITS, 'youtube_quota_usage.json')
      " <beat_index>
      ```

      Run this command with a long Bash timeout (`timeout: 600000`): it downloads candidate thumbnails. Only `"artwork_or_stock"` beats run the
      stock search, so only they record YouTube quota. An `ArchivalSearchError`, `ArchiveError`, `YouTubeError`, `PexelsError` or `ValueError`
      STOPs the stage with the beat index; a YouTube 403/`quotaExceeded` follows the quota handling in Step 2a. A Bash timeout counts as a STOP too: re-run
      this step once (the Met client now bounds its own time); if it times out again, report it. A `shot_list.json` built before this branch (pre-1839
      beats with blank archival queries) must be regenerated with Stage 1 Step 6b before running this step.

   m-b. Spawn ONE subagent (Agent tool, `model: "opus"`) with `archival_work/mixed_prompt_<beat_index>.txt`'s content as its full instructions
      (it needs Read access for the thumbnails). Save its raw response to `archival_work/mixed_response_<beat_index>.txt`.

   m-c. Apply the verdict (prints `stills`, `stock` or `none`):

      ```bash
      .venv/bin/python -c "
      import json, os, sys
      from dotenv import load_dotenv
      from footage.mixed_build import finish_mixed
      load_dotenv()
      envato_profile_dir = os.environ.get('ENVATO_PROFILE_DIR', '.envato_automation_profile')
      beat = next(b for b in json.load(open('archival_beats.json')) if b['beat_index'] == int(sys.argv[1]))
      raw = open(f'archival_work/mixed_response_{sys.argv[1]}.txt').read()
      print(finish_mixed(beat, raw, envato_profile_dir))
      " <beat_index>
      ```

      On `none`: STOP, tell Josh the beat index and the judge's reasoning, and ask for an image he supplies (run 2A-e `render_manual_photos`;
      a real historical artwork or photo only, with its source/license). Never pick one yourself. A `ScoringOutputError`, `ArchivalRenderError`,
      `ArchiveError`, `YouTubeDownloadError`, `EnvatoDownloadError`, `PortraitVideoError` or `DownloadError` STOPs the stage with the beat index.

3. Report to the user: how many footage beats were sourced (and how many, if any, were flagged
   as having no acceptable footage), a source breakdown (how many clips came from Pexels vs.
   YouTube vs. Envato), and the `footage_output/` directory containing the downloaded clips.
   Run `.venv/bin/python -c "from footage.archival_review import write_review; print(write_review())"` and tell
   Josh how many cuts were archival (film / photo / artwork / mixed stills / stock) and the path of `archival_review.html`. It is optional reading:
   the run continues to Stage 3/4 either way.
   Also report the total number of Envato *candidates* found across the whole run (not per
   beat) — count the `"source": "envato"` entries across every `candidates_<n>.json` written
   this run, plus the stock candidates of mixed beats: the `"stock"` list entries whose `"source"` is `envato` in every
   `archival_work/mixed_state_<n>.json` — plus any `WARNING: Envato ...` lines seen. **If that run-wide total is zero,
   say so prominently at the top of the report:** Envato silently contributed nothing, most
   likely because the Playwright profile's Envato session expired (fix: re-run
   `tests/fixtures/envato_automation_spike.py` and log in). This
   is the deliverable for this stage — Stage 4 (Final Assembly) consumes these files alongside
   Stage 1's `shot_list.json` and Stage 3's `graphics_output/` (motion graphics).

---

# Stage 3 (Motion Graphics)

Run this after Stage 1 has produced `shot_list.json`. Requires `GRAPHICS_DESIGN_SYSTEM_NAME` in
`.env`: the **exact display name** of the Claude Design design system to attach to every canvas,
as it appears in claude.ai/design's "Design system" picker (not set yet: the Bridged
design system has to be created first). It is a name, not an id: the
picker only selects by visible name. This is the Bridged design system project in
Claude Design, which Josh builds from his own Bridged frames and font. Until it exists the local
snapshot is a placeholder and Stage 3 must NOT be run. The placeholder lists 7 archetypes (`chart_card`, `definition`,
`distance`, `org_chart`, `place_chip`, `route_overlay`, `territory_map`). The
prompt-writer and reviewer subagents (and the Stage 1 director) read the local rules snapshot
`design_system/bridged-design-system.md` by absolute path rather than the design system
itself, since unattended subagents cannot read claude.ai. **Refresh that snapshot whenever the design
system changes: re-copy the readme content from claude.ai/design, but PRESERVE the snapshot's
header pipeline notes (the 7 archetypes) and its "Pre-ship checklist"
section (or re-derive the checklist from the new rules and keep the section heading unchanged),
because the pipeline added them and the reviewer prompt depends on that checklist**, and rebuild
it via `/design-sync` when Josh's frames change. `/design-sync` is a manual step you run
yourself. Nothing in this stage triggers it.

Beats of type `page_highlight` (from linked pages) are not graphic beats: Stage 3 ignores them, and
Stage 4 builds their clips from `page_stills/`. `image` beats (from non-italic links to an image
file) are not graphic beats either; Stage 3 ignores them and Stage 4 builds their clips from
`image_stills/`.

**Era rule.** When a graphic's fact names a historical year or period (e.g. "1847, City of
Atlanta"), the imagery must be period-appropriate: an old photograph, engraving, lithograph or
historic map of the place from the closest available decade. An exact-year match is not
required (1850 or 1860 is fine for 1847), but a modern photo, skyline, vehicles or buildings
are never acceptable. If the reviewer's screenshot shows modern imagery for a historical fact,
that is a correction, not an approval. The rule applies only to genuinely historical dates (before
roughly the mid-20th century), never to modern years, satellite maps or graphics without photos.

**This stage is driven by you, the agent, in the browser.** claude.ai/design is behind Cloudflare
bot detection that blocks any Python-launched automated browser (Playwright etc.), even with a
valid saved login. So no Python code touches the browser here. Every browser step below is done
with your own `claude-in-chrome` tools, which drive Josh's real, already-logged-in Chrome. Never
try to get around Cloudflare (no stealth flags, patched browsers, or challenge solvers). The
consequence: **this stage only runs in an interactive Claude Code session with the Claude in
Chrome extension connected.** It cannot run as an unattended or background job. Python does the
rest: prompt building, the small JSON state files between steps, and real `ffprobe` checks of the
exported clip.

`motion_graphics/driver.py`'s `ClaudeDesignDriver` Protocol and `motion_graphics/build.py`'s
`create_canvas_and_submit`/`submit_correction`/`finalize_export` are **not used** by this stage.
They predate the Cloudflare finding. See the note at the top of `motion_graphics/driver.py`.

**Before the first run** (one-time checks; none of these are done or checked by any step below):

- [ ] `GRAPHICS_DESIGN_SYSTEM_NAME` is set in `.env` to the design system's exact display name,
  and that design system has been built via `/design-sync` (see above).
- [ ] Chrome is logged into the claude.ai account that owns that design system. This stage never
  logs in; a login page mid-run is a stage-level STOP.
- [ ] The Claude in Chrome extension is installed, connected to this Claude Code session, and has
  site permission for `claude.ai` (the extension asks per site; without it every browser step
  fails).
- [ ] Chrome saves downloads straight to `~/Downloads` with "Ask where to save each file before
  downloading" turned OFF (Chrome Settings > Downloads). Step 2f only looks in `~/Downloads`;
  a save-as prompt would leave the export sitting in a dialog nobody answers.

**What has and hasn't been verified live (read before trusting this on a real video).** Two live
passes have now run against the real product, on 2026-09-28: an initial single-beat pass (short
hand-written prompts and verdicts; integer durations 5.0s/4.0s), and a follow-up multi-beat pass that specifically closed the gaps the first pass left
open. The follow-up pass, using the real prompt-writer and reviewer subagents end to end:

- Ran **two graphic beats in the same Chrome session**, with a second tab's canvas created
  while the first tab's export was still in progress, then finished each in turn — the per-beat
  tab lifecycle and `~/Downloads` matching across consecutive exports both worked. (A real tab
  lifecycle quirk was found and is now documented under "Browser setup and ground rules" above:
  closing one tab can tear down the whole tracked tab group even when another tab is still open;
  reattaching by URL recovers cleanly.)
- Used **fractional target durations** (3.4s and 4.7s, the second literally
  `4.699999999999999` — a real floating-point artifact from a shot list's beat boundaries, not a
  clean round number). Both exports came back matching their target exactly: `ffprobe` showed
  `duration=3.400000` and `duration=4.700000`.
- Used **realistic long authoring prompts** from the real prompt-writer subagent (3054 and 4143
  characters) — the prompt box grows correctly, Step 2b.5's "confirm the box holds your full
  prompt" screenshot check worked at this length, and the first-click-lost issue happened again
  (a fourth observed occurrence across both passes) but was caught and recovered exactly as
  documented.
- Exercised a **real correction round-trip**: the reviewer subagent correctly caught a real
  design-system-rule violation (a wrong-color highlight), the correction was sent and
  applied, and the second review approved.
- The full graphics beat pipeline output was consumed by **Stage 4 (Final Assembly)** for real —
  both exported clips, muxed with a synthetic voiceover, produced a final `assembled.mp4` at the
  exact target duration (8.100000s), proving the whole Stage 1 → 3 → 4 chain for graphic-only
  content end to end.

One thing is still genuinely untested: a run mixing graphic beats with real footage beats in the
same video. It is lower-risk than what these passes already covered.

**Per-beat flags vs. stage-level STOPs.** Like Stage 2's "NO ACCEPTABLE FOOTAGE", a reviewer
verdict against one beat does not end the stage. When Step 2d prints `GRAPHIC BEAT REJECTED` or
`GRAPHIC BEAT NOT APPROVED`, flag that beat, stop working on it, close its tab, and continue with
the next graphic beat; Step 3 lists the flagged beats. Every other "STOP" in this stage (anything
Step 2d's two verdicts don't cover: browser tools unreachable, claude.ai not loading, a
Cloudflare or login page, no design system matching the name, a UI step that doesn't match the
description, a parse or verification error) ends the whole stage, because it will almost
certainly hit every later beat the same way. See the catch-all at the end of Step 2.

## Browser setup and ground rules (read before Step 2)

- **Load the tools.** If the `mcp__claude-in-chrome__*` tools aren't available yet, invoke the
  `claude-in-chrome` skill, then load the core set in ONE `ToolSearch` call:
  `select:mcp__claude-in-chrome__tabs_context_mcp,mcp__claude-in-chrome__navigate,mcp__claude-in-chrome__computer,mcp__claude-in-chrome__read_page,mcp__claude-in-chrome__tabs_create_mcp,mcp__claude-in-chrome__tabs_close_mcp,mcp__claude-in-chrome__javascript_tool,mcp__claude-in-chrome__find,mcp__claude-in-chrome__browser_batch`.
  Call `tabs_context_mcp` first. Then create your OWN tab with `tabs_create_mcp` for each graphic
  beat. Never reuse a tab id from another session, and close your tab when that beat is done.
  After `tabs_close_mcp` inside a `browser_batch`, later items in that batch fail, so make it the
  last item. **Closing a tab can tear down the whole tracked tab group even when another tab of
  yours is still open**, observed live running two beats' tabs at once: closing beat 0's tab
  after export made `tabs_context_mcp` report no tabs at all, orphaning beat 1's still-open tab
  from tracking (it was still open in real Chrome, just no longer visible to any tool call). If a
  tool call fails with "tab group no longer exists" or "couldn't determine which page this action
  targets", call `tabs_context_mcp` with `createIfEmpty: true`, then reattach to whatever canvas
  you were working on via its full canvas URL — this always works, per the reattachment guarantee
  below, and is a normal recovery step, not a failure worth reporting.
- **JavaScript calls time out after about 45 seconds.** Every polling snippet below loops for at
  most 30 seconds and then returns. When it returns "not finished", run the same snippet again.
- **Coordinates.** Screenshot and `zoom` coordinates use the screenshot's own frame. The
  `computer` tool reports that frame with every screenshot, for example "1568x668". This frame is
  smaller than the page's CSS pixel frame (`window.innerWidth`, for example 1751). To convert a CSS
  rect from JavaScript to screenshot coordinates, multiply by
  `screenshot_frame_width / window.innerWidth`. Prefer `find` refs or labelled-button JavaScript
  over raw coordinates. When you must click by coordinate, take a fresh screenshot first.
- **The visibility override.** Your tab normally reports `document.hidden === true` because it is
  not the OS-frontmost window. That has two effects. (1) Video export stalls forever. The export
  dialog even says export pauses in the background. (2) The canvas preview renders washed-out and
  grey. The fix is to run this exact snippet with `javascript_tool`:

  ```js
  Object.defineProperty(document, 'hidden', { get: () => false, configurable: true });
  Object.defineProperty(document, 'visibilityState', { get: () => 'visible', configurable: true });
  document.dispatchEvent(new Event('visibilitychange'));
  document.hidden
  ```

  It should return `false`. Run it only on a settled canvas (see Procedure W), right before each
  screenshot and before each export. The preview iframe reloads after every edit, so run it again
  each time; a previous run's effect on the preview doesn't carry over. Navigating the tab (a
  fresh page load) removes the override entirely. The tab may also become genuinely visible on its
  own, for example if Josh brings that Chrome window to the front. Nothing below depends on it
  staying hidden.
- **Never click** "Publish as artifact", "Copy link", or the "Who can access" dropdown in the
  Share panel. Never click "Undo" in the chat, the thumbs up/down or star rating, or "Present".
  None of them are part of this workflow.

### Procedure W: wait for a generation or correction to finish

Use this right after clicking a submit/Send button. In the SAME `browser_batch` as the click, and
immediately before it, reset the tracker with `window.__mg = undefined` via `javascript_tool`.
Then run this snippet with `javascript_tool` after the click, repeatedly, until it returns
`settled: true`:

```js
const W = (window.__mg ??= { sawWorking: false, doneSince: null, start: Date.now() });
const isIdle = () => {
  const btns = [...document.querySelectorAll('button')].filter(b => b.offsetParent);
  const stop = btns.some(b => b.getAttribute('aria-label') === 'Stop' || b.title === 'Stop');
  const send = btns.some(b => b.title === 'Send (Enter)');
  const checking = document.body.innerText.includes('Checking the design for issues');
  return send && !stop && !checking && !document.title.startsWith('✶');
};
const t0 = Date.now();
while (Date.now() - t0 < 30000) {
  if (!isIdle()) { W.sawWorking = true; W.doneSince = null; }
  else if (W.sawWorking) {
    W.doneSince ??= Date.now();
    if (Date.now() - W.doneSince >= 30000) break;
  }
  await new Promise(r => setTimeout(r, 500));
}
({ settled: W.sawWorking && W.doneSince !== null && Date.now() - W.doneSince >= 30000,
   sawWorking: W.sawWorking, elapsed_s: (Date.now() - W.start) / 1000,
   title: document.title, url: location.href })
```

**Verification status:** this final multi-signal form has now been watched start to finish on a
brand-new first generation (settled correctly after 136 seconds, on a long ~3000-character
prompt), on a correction (a hidden page, settled correctly after ~40 seconds), and on a second,
independent brand-new first generation in a second tab open at the same time as the first (also
settled correctly). Treat it as proven for those cases. If it ever settles while the chat is
visibly still working, or never settles on an idle chat, STOP and report what the four signals
showed.

**A real gap this loop doesn't cover: reattaching to a turn that already finished elsewhere.**
If you navigate to a canvas URL that is NOT immediately following your own submit/correction
click in this same tab — for example checking on beat 0 again after spending a while on beat 1 in
a different tab, and beat 0's generation happened to finish while you were away — the page is
idle from the very first check, so `sawWorking` never flips `true` and `settled` never becomes
`true`, even though the content is fully done. This is expected, not a bug: don't run the full
30-second loop in that situation. Instead, after navigating and waiting the usual ~6 seconds,
check the chat panel directly (a screenshot, or `document.body.innerText`) for a complete
descriptive response with no visible "Working"/"Checking" state and a Send button present — if
that's what you see, treat the canvas as settled and move on to Procedure S or E. A "background
check didn't finish — the tab it was running in never reported back" banner (with "Re-run check"
/ "Dismiss" buttons) can appear here too — this is claude.ai/design's own internal post-generation
verification failing to report, separate from your generation itself; it does not mean the
rendered content is wrong. If the visible content otherwise looks complete, ignore the banner and
proceed.

The tracker lives on `window` and survives the homepage-to-project switch after the first submit.
That switch is an in-app navigation, not a page load. Why the snippet looks like this (observed
live, 2026-09-28):

- No single on-page signal was reliable in every live run, so the snippet counts the chat as
  working if ANY of these is true. (1) A button labelled "Stop" is showing. This was seen for the
  whole turn, in both hidden and visible pages. (2) The Send button (`title="Send (Enter)"`) is
  missing. In one visible-page run it vanished for the whole turn; in other runs it stayed. It
  is also missing on the claude.ai/design homepage, which is fine because the snippet is waiting
  for work there anyway. (3) The tab title starts with `✶ `. Hidden pages show this at the start
  of a turn. (4) "Checking the design for issues" is on the page.
- After the main turn finishes, claude.ai/design automatically runs a "Checking the design for
  issues…" pass. That pass can show "Found issues — fixing…" and start another editing turn on its
  own. So the snippet treats the check as "still working", and requires idle to hold continuously
  for 30 seconds before calling the canvas settled.
- `sawWorking` guards the stale-state race. On the project page the chat already looks idle
  before you submit, so idle only counts after the snippet has seen the turn actually running.
- **Do not use the tab title as the completion signal**, even though it looks tempting. The title
  does get a `✓ ` prefix when a turn finishes while the page is hidden (and `✶ ` while working).
  But the page clears that prefix as soon as the page counts as visible, and claude.ai/design's
  automatic project rename right after a first generation also wipes it. In one live run the final
  title never regained the `✓`.

Observed timings: first generations took 30 seconds to about 2 minutes, and corrections took
15-20 seconds, plus up to about 40 seconds of automatic checking and the 30-second settle. If
`elapsed_s` passes 600 (10 minutes) without `settled: true`, take a screenshot and STOP. Report the
beat index, the canvas URL, and what the chat panel shows. Do not resubmit the prompt.

### Procedure S: capture the canvas screenshot for the reviewer

Run this on a canvas whose latest turn has settled (Procedure W):

1. Run the visibility override snippet. The preview can stay washed-out grey for a moment
   afterwards. It repaints in full color once playback moves or you scrub (step 3). If it is still
   grey after the scrub, run the override again, wait 2 seconds, and scrub again.
2. Hide the in-design "Tweaks" panel if it is showing. It is a floating panel over the bottom-right
   of the canvas. Run
   `(() => { const b = [...document.querySelectorAll('button')].find(b => b.offsetParent && b.getAttribute('aria-label') === 'Tweaks'); const was = b?.getAttribute('aria-pressed'); if (was === 'true') b.click(); return was; })()`.
   This returns the state *before* the call: `'true'` means it was showing and has now been
   toggled off. `null`/`undefined` means the toolbar hasn't finished rendering (seen about 4
   seconds after a page load); wait 2 seconds and run it again. Confirm in the next screenshot
   that no "Tweaks" panel floats over the canvas.
3. Pause playback and show the finished composition, not a mid-animation frame. Run
   `(() => { const b = [...document.querySelectorAll('button')].find(b => b.offsetParent && b.getAttribute('aria-label') === 'Pause'); if (b) b.click(); return !!b; })()`.
   Then take a screenshot. Click on the time ruler at the very bottom of the canvas panel (the row
   of `0s … 1s … 2s …` tick labels directly above the segment bars) at about 90% of its length,
   just left of the end-time label. Zoom into that row to confirm the timecode at its left reads
   about 90% of the clip's duration, and that the play button (aria-label `Play`) shows it is
   paused. *Fragile:* the ruler has no stable selector and is clicked from the screenshot. It is
   among the steps most likely to break if the product's UI changes; check the timecode every
   time.
4. Get the preview's rect:
   `(() => { const f = [...document.querySelectorAll('iframe')].find(f => f.src.includes('claudeusercontent.com/_bootstrap')); const r = f.getBoundingClientRect(); return [r.left, r.top, r.right, r.bottom, window.innerWidth]; })()`.
   This iframe is exactly the canvas, without the chat sidebar, top toolbar, or timeline. Convert
   it to screenshot coordinates (see "Coordinates" above) and call `computer` with
   `action: "zoom"`, `region: [left, top, right, bottom]` (converted), and `save_to_disk: true`.
   **Do not pass `scale`**, because the saved file is downscaled to match it. The result says
   "Screenshot saved to: <path>". The saved image should be the canvas alone at its CSS size (for
   example 1156x624); view it to confirm the canvas is in full color. That `<path>` is a temp
   file. Pass it to the recording step below, which copies it into the project.

### Procedure E: export the approved clip

1. Record the export start time (the download is found by comparing against it):
   `.venv/bin/python -c "import sys, time; open(f'export_started_{sys.argv[1]}.txt', 'w').write(str(time.time()))" <beat_index>`
2. In the beat's tab, navigate to the canvas URL from `canvas_<beat_index>.json`. Wait about 6
   seconds, run the visibility override snippet, and hide the Tweaks panel as in Procedure S
   step 2.
3. Click the black "Share" button at the top right of the canvas panel. Take a screenshot to
   confirm a panel opened. It contains "Who can access", "Publish as artifact", and an "Export"
   list. In one live run the first click right after load did nothing; if so, click again. Under
   "Export", click the "Download" text at the right end of the "Video — MP4 of this animation" row
   (the first Export row). The "Project HTML", "PDF", and "PowerPoint" rows are not what you want.
   *Fragile:* that "Download" text is clicked from the screenshot, with no stable selector. It is
   among the steps most likely to break if the product's UI changes. The next step's "Export
   video" dialog is the confirmation that you hit the right row.
4. An "Export video" dialog appears with three radio options: 600 × 338, 1280 × 720 (selected by
   default), and "Original size — 1920 × 1080". `find` does not see this dialog, so work from a
   screenshot. Click the radio circle for **"Original size — 1920 × 1080"**, then `zoom` into
   the dialog to confirm that radio is now the filled one. Run the visibility override snippet
   again, then click the black "Export" button at the dialog's bottom right. *Fragile:* these
   radios are clicked from the screenshot and are among the steps most likely to break if the
   product's UI changes. Step 2f's mandatory 1920×1080 ffprobe check is the backstop.
5. Immediately run the visibility override snippet once more, then poll until the export
   finishes. Re-run this snippet until it returns `true`. If it still hasn't returned `true` after
   3 minutes, take a screenshot, then STOP the stage and report it with the beat index and canvas
   URL (a stage-level failure; see the catch-all at the end of Step 2). Do not start a second
   export:
   `const t0 = Date.now(); while (!document.body.innerText.includes('will download now') && Date.now() - t0 < 30000) await new Promise(r => setTimeout(r, 500)); document.body.innerText.includes('will download now')`.
   Observed: a 5-second clip exported in about 3 seconds with the override. Without it, export
   stalls forever at zero progress.
6. A "Your MP4 will download now…" dialog appears with "Download" and "Done" buttons. **The MP4
   downloads on its own when this dialog appears. Do NOT click "Download"**, because that saves a
   second copy. Run step 7 first. Once step 7 has found the file, click "Done". Only if step 7
   reports that no file arrived, click "Download" exactly once and run step 7 again.
7. Move the download into place and verify it for real (see Step 2f's command).

## Steps

1. Load `shot_list.json`, extract every graphic beat, and check the design-system setting:

   ```bash
   .venv/bin/python -c "
   import dataclasses, json, os, shutil
   from dotenv import load_dotenv
   from shot_list.models import ShotList, beat_from_dict
   from motion_graphics.shotlist_integration import graphic_beats

   load_dotenv()
   design_system_name = os.environ['GRAPHICS_DESIGN_SYSTEM_NAME']

   raw = json.load(open('shot_list.json'))
   beats = [beat_from_dict(b) for b in raw['beats']]
   shot_list = ShotList(beats=beats, duration=raw['duration'])
   pairs = graphic_beats(shot_list)

   if len(pairs) == 0:
       raise ValueError(
           'shot_list.json has no graphic beats — nothing for Stage 3 to render. '
           'Double-check this is the right shot list before proceeding (Global Constraint: fail loudly).'
       )

   json.dump(
       [{'beat_index': i, 'graphic': dataclasses.asdict(spec), 'target_duration': d} for i, spec, d in pairs],
       open('graphic_beats.json', 'w'),
   )

   # Fresh start for a new video — placed after shot-list parsing AND the len(pairs) == 0 check
   # both succeed, and after graphic_beats.json has been written, so a failure at either of those
   # points leaves a previous video's graphics_output/ untouched (same ordering lesson as Stage 2's
   # footage_output/ cleanup above — an earlier version of that cleanup ran too early and wiped a
   # previous video's still-needed output on an unrelated early failure).
   shutil.rmtree('graphics_output', ignore_errors=True)
   shutil.rmtree('graphics_screenshots', ignore_errors=True)

   print(f'{len(pairs)} graphic beats to render; design system: {design_system_name!r}')
   "
   ```

   If this raises `FileNotFoundError`, `json.JSONDecodeError`, `KeyError`, or `TypeError`, STOP
   and report it. Either `shot_list.json` is missing or malformed, or `GRAPHICS_DESIGN_SYSTEM_NAME`
   is not set in `.env`. A `TypeError` from `beat_from_dict` (a `GraphicSpec`/`FootageSpec`/`PageSpec` argument) can also mean an older-format
   shot_list.json (from before the 7-archetype set); regenerate it with Stage 1. If it raises `ValueError` because there are no graphic beats at all, STOP
   and confirm with the user that this is the right shot list (a video whose only italic spans are page highlights and/or show-as-is images (non-graphic spans) has no graphic beats; Stage 3 is simply not needed then, so do not stop to ask: skip to Stage 4). Do not clear `graphics_output/` for
   a video that has nothing to render.

2. Read `graphic_beats.json`. For EACH `(beat_index, graphic, target_duration)` entry, in order,
   run sub-steps a-f. Create a fresh browser tab for the beat when you first need it (sub-step b),
   and close it after the beat finishes or is flagged. A beat flagged in sub-step d (rejected, or
   not approved within the attempt cap) is set aside and the loop moves on to the next entry; any
   other STOP in this step ends the whole stage (see "Per-beat flags vs. stage-level STOPs" above).

   a. Build the prompt-writer subagent's instructions and spawn it (Opus):

      ```bash
      .venv/bin/python -c "
      import json, sys
      from motion_graphics.prompt_writer_prompt import build_prompt_writer_prompt

      beat_index = sys.argv[1]
      entries = json.load(open('graphic_beats.json'))
      entry = next(e for e in entries if e['beat_index'] == int(beat_index))
      graphic, target_duration = entry['graphic'], entry['target_duration']

      prompt = build_prompt_writer_prompt(
          archetype=graphic['archetype'], data=graphic['data'],
          target_duration=target_duration,
      )
      open(f'prompt_writer_prompt_{beat_index}.txt', 'w').write(prompt)
      " <beat_index>
      ```

      Spawn ONE subagent (Agent tool, `model: "opus"`) with `prompt_writer_prompt_<beat_index>.txt`'s
      content as its full instructions. Save its raw response to
      `prompt_writer_response_<beat_index>.txt`.

   b. Parse the response into the authoring prompt:

      ```bash
      .venv/bin/python -c "
      import sys
      from motion_graphics.prompt_writer_output import parse_prompt_writer_output

      beat_index = sys.argv[1]
      authoring_prompt = parse_prompt_writer_output(open(f'prompt_writer_response_{beat_index}.txt').read())
      # Flattened to one line: a newline typed into claude.ai/design's prompt box can submit it early.
      open(f'authoring_prompt_{beat_index}.txt', 'w').write(' '.join(authoring_prompt.split()))
      print(f'beat {beat_index}: authoring prompt ready ({len(authoring_prompt)} chars)')
      " <beat_index>
      ```

      If `parse_prompt_writer_output` raises `PromptWriterOutputError`, STOP and report it. Do not
      hand-patch the response and continue.

      Then create the canvas in the browser. **Do these in this order.** Each part was verified
      live, and skipping the template click silently produces the wrong format.

      1. Create a new tab (`tabs_create_mcp`) and navigate it to `https://claude.ai/design`. Wait
         about 3 seconds. The page reads "What should we create?" and has a prompt box. Below the
         box is a "CHOOSE A TEMPLATE" grid: Blank, Mobile app design, Slides, Document, Wireframe,
         **Animation**, and so on. If you see a Cloudflare challenge or a login page instead, STOP
         and tell the user. Never try to solve or bypass it.
      2. **Attach the design system by name.** Take a screenshot. Then click the "Design system"
         chip in the prompt box's bottom row, just right of the `+` button. It shows "Design
         system" over the name of the currently attached design system.
         Take another screenshot to confirm that a list opened under the chip with a focused
         "Search design systems" input. In one live run, the first click, made about 3 seconds
         after page load, silently did nothing. If no list opened, click the chip again. Once the
         list is open, type the exact value of `GRAPHICS_DESIGN_SYSTEM_NAME`. Then click the matching result
         row on its name text, not on the `>` chevron at the row's right edge. Confirm the chip
         now shows that name, either in a screenshot or with
         `[...document.querySelectorAll('button')].some(b => b.innerText.includes('Design system') && b.innerText.includes('<name>'))`.
         **This selector is a toggle, not a plain select.** If `GRAPHICS_DESIGN_SYSTEM_NAME` is
         already the attached design system when you open the list (it may be, on a fresh session
         or if a prior beat in this same run already attached it), clicking its row the first time
         deselects it instead: the confirmation check above will fail (the chip shows "None" or
         a different name). If that happens, click the same row a second time to re-select it,
         then re-run the confirmation check. If it still doesn't match after two clicks, STOP and
         report it. If no result matches the search at all, STOP and report it. Never fall back
         to a different design system.
      3. **Click the "Animation" template card.** Run this with `javascript_tool`:
         `(() => { const b = [...document.querySelectorAll('button')].find(b => b.offsetParent && b.getAttribute('aria-label') === 'Animation'); if (b) b.click(); return !!b; })()`.
         It should return `true`. (`find` with a loose description can fail to match this card.)
         Take a screenshot to confirm the prompt box now contains `Animate ` and the Animation card
         is highlighted. This click is what makes the canvas a timed `.dc.html` animation with a
         timeline. Typing a prompt that starts with "Animate", without clicking the card, was
         verified to produce a plain static `.html` "App" with no timeline, which is useless here.
      4. Click into the prompt box, press `cmd+a`, and `type` the full contents of
         `authoring_prompt_<beat_index>.txt`. This replaces the `Animate ` prefill.
      5. Take a fresh screenshot. Confirm the box holds your full prompt and no longer says
         `Animate` at the start (unless your prompt does). If the box is empty, still shows only
         `Animate `, or holds a partial prompt, click into it, press `cmd+a`, type the full prompt
         again, and re-check. The box grows with long text, so the submit button moves. Then, in
         one `browser_batch`: run `window.__mg = undefined` via `javascript_tool`, click the
         orange up-arrow submit button at the far right of the prompt box's bottom row (just right
         of the "Model" chip), and run the Procedure W snippet. *Fragile:* this button has no label
         or stable selector, so it is found only from the screenshot. It is among the steps most
         likely to break if the product's UI changes; if it isn't where described, STOP and report
         rather than guessing.
         **Check that the submit registered.** Procedure W can't tell a lost click on the homepage
         from real work, because the homepage has no Send button. If the `url` returned by the
         first 30-second Procedure W poll is still exactly `https://claude.ai/design`, the click
         was lost. Take a screenshot. If your prompt is still in the box, run
         `window.__mg = undefined`, click the submit button again, and restart Procedure W. If it
         is still on the homepage after a second try, STOP and report it.
      6. Within a few seconds the page switches to a project view. The URL becomes
         `https://claude.ai/design/p/<project-uuid>`. The chat shows your prompt with two chips
         under it: **"Animated video"** and your design system's name. If "Animated video" is
         missing, the template click didn't register. STOP and report it; do not continue with
         this canvas.
      7. Keep running Procedure W until `settled: true`. The URL then includes the canvas file,
         for example `https://claude.ai/design/p/01654af7-4100-45f4-aacf-e50811c6d5c9?file=Chart+Card+42.dc.html`.
         The canvas panel has a timeline under it: play controls, a `0s … <duration>` ruler, and
         named segment bars. **This full URL is the canvas's identity.** Navigating any tab
         straight to it later fully reattaches the chat history, canvas, and timeline. If the
         `?file=` value doesn't end in `.dc.html`, STOP. The canvas is not a real animation.
      8. Capture the reviewer screenshot with Procedure S.

      Record the canvas and the first attempt. Substitute the real URL (in double quotes) and the
      saved screenshot path:

      ```bash
      .venv/bin/python -c "
      import json, os, shutil, sys

      beat_index, canvas_url, saved_screenshot = sys.argv[1], sys.argv[2], sys.argv[3]
      if not (canvas_url.startswith('https://claude.ai/design/p/') and '?file=' in canvas_url
              and canvas_url.endswith('.dc.html')):
          raise ValueError(f'not a claude.ai/design animation canvas URL: {canvas_url}')
      if os.path.getsize(saved_screenshot) < 5_000:
          raise ValueError(f'screenshot {saved_screenshot} is suspiciously small')

      os.makedirs('graphics_screenshots', exist_ok=True)
      screenshot_path = os.path.abspath(f'graphics_screenshots/beat_{beat_index}_attempt_1.png')
      shutil.copyfile(saved_screenshot, screenshot_path)

      # Same shape as motion_graphics.driver.CanvasHandle: canvas_id is the full canvas URL.
      json.dump({'canvas_id': canvas_url}, open(f'canvas_{beat_index}.json', 'w'))
      json.dump({'screenshot_path': screenshot_path, 'attempt': 1}, open(f'review_state_{beat_index}.json', 'w'))
      print(f'beat {beat_index}: canvas {canvas_url} created, attempt 1 screenshot at {screenshot_path}')
      " <beat_index> "<canvas_url>" "<saved_screenshot_path>"
      ```

   c. Build the reviewer subagent's instructions for the current attempt and spawn it:

      ```bash
      .venv/bin/python -c "
      import json, sys
      from motion_graphics.reviewer_prompt import build_reviewer_prompt

      beat_index = sys.argv[1]
      entries = json.load(open('graphic_beats.json'))
      entry = next(e for e in entries if e['beat_index'] == int(beat_index))
      graphic = entry['graphic']
      state = json.load(open(f'review_state_{beat_index}.json'))

      MAX_ATTEMPTS = 3
      prompt = build_reviewer_prompt(
          archetype=graphic['archetype'], data=graphic['data'],
          screenshot_path=state['screenshot_path'], attempt=state['attempt'], max_attempts=MAX_ATTEMPTS,
      )
      open(f'reviewer_prompt_{beat_index}_{state[\"attempt\"]}.txt', 'w').write(prompt)
      " <beat_index>
      ```

      Spawn ONE subagent (Agent tool) with that file's content as its full instructions. It must
      have Read tool access (to view the screenshot). Save its raw response to
      `reviewer_response_{beat_index}_{attempt}.txt`, using the same attempt number as the prompt
      file just written.

   d. Parse the verdict and decide what happens next:

      ```bash
      .venv/bin/python -c "
      import json, sys
      from motion_graphics.reviewer_output import parse_reviewer_output

      beat_index = sys.argv[1]
      MAX_ATTEMPTS = 3

      state = json.load(open(f'review_state_{beat_index}.json'))
      attempt = state['attempt']
      verdict = parse_reviewer_output(open(f'reviewer_response_{beat_index}_{attempt}.txt').read())

      if verdict.verdict == 'approve':
          print(f'beat {beat_index}: approved on attempt {attempt} — NEXT: export (step 2f)')
      elif verdict.verdict == 'reject':
          print(f'GRAPHIC BEAT REJECTED for beat {beat_index} (attempt {attempt}): {verdict.reasoning}')
          sys.exit(2)
      elif attempt >= MAX_ATTEMPTS:
          print(f'GRAPHIC BEAT NOT APPROVED for beat {beat_index} after {MAX_ATTEMPTS} attempts: {verdict.reasoning}')
          sys.exit(2)
      else:
          # Flattened to one line for the same reason as the authoring prompt.
          open(f'correction_{beat_index}_{attempt}.txt', 'w').write(' '.join(verdict.correction_instructions.split()))
          print(f'beat {beat_index}: correction needed (attempt {attempt}) — NEXT: send correction (step 2e)')
      " <beat_index>
      ```

      If this exits with status 2 (`GRAPHIC BEAT REJECTED` or `GRAPHIC BEAT NOT APPROVED`), stop
      working on THIS beat only: note its index, archetype, the reasoning printed, and its canvas
      URL from `canvas_<beat_index>.json` for Step 3's report, close its tab, and continue with
      the next entry in `graphic_beats.json`. This is a per-beat flag, not a stage failure, the
      same as Stage 2's "NO ACCEPTABLE FOOTAGE". Do not re-run the reviewer yourself, approve it
      on your own judgment, or export it. No clip is written for a flagged beat. If
      `parse_reviewer_output` raises `ReviewerOutputError` (a malformed reviewer response), that
      is different: STOP the whole stage and report the exact error. Do not hand-patch the
      response and continue.

   e. **Send the correction** (only when 2d printed "NEXT: send correction"):

      1. Navigate the beat's tab to the canvas URL from `canvas_<beat_index>.json`, then wait
         about 6 seconds. Chat history, canvas, and timeline all come back, even in a brand-new
         tab. This was verified live.
      2. Click the chat input at the bottom of the left sidebar (placeholder "Describe what you
         want to create…"). `type` the full contents of `correction_<beat_index>_<attempt>.txt`.
         Then `zoom` into the input's area (the bottom of the left sidebar) and **confirm the text
         is really there**. Twice in live runs, the first click+type right after a page load was
         silently lost while the chat finished loading. If the input still shows the placeholder,
         click it and type again, then re-check.
      3. `find` "Send button". It is the button titled "Send (Enter)". Then, in one
         `browser_batch`: run `window.__mg = undefined`, click that ref, and run the Procedure W
         snippet. Keep running Procedure W until `settled: true`. Take a screenshot to confirm the
         chat shows your correction as a new message, followed by a reply describing what changed.
         If `sawWorking` is still `false` after the first 30-second poll, the message probably
         wasn't sent. Check the screenshot before doing anything else. Check that the URL's
         `?file=` is still the same `.dc.html` file. If it changed, STOP and report it.
      4. Capture the new screenshot with Procedure S, then record the new attempt:

      ```bash
      .venv/bin/python -c "
      import json, os, shutil, sys

      beat_index, saved_screenshot = sys.argv[1], sys.argv[2]
      state = json.load(open(f'review_state_{beat_index}.json'))
      attempt = state['attempt'] + 1
      if os.path.getsize(saved_screenshot) < 5_000:
          raise ValueError(f'screenshot {saved_screenshot} is suspiciously small')

      screenshot_path = os.path.abspath(f'graphics_screenshots/beat_{beat_index}_attempt_{attempt}.png')
      shutil.copyfile(saved_screenshot, screenshot_path)
      json.dump({'screenshot_path': screenshot_path, 'attempt': attempt}, open(f'review_state_{beat_index}.json', 'w'))
      print(f'beat {beat_index}: correction sent, re-review at attempt {attempt} needed — repeat step 2c')
      " <beat_index> "<saved_screenshot_path>"
      ```

      Then go back to sub-step 2c for the SAME beat. The attempt number has already advanced in
      `review_state_<beat_index>.json`. Do not move on to the next beat.

   f. **Export** (only when 2d printed "NEXT: export"): run Procedure E steps 1-6. Then move the
      download into place and verify it. This waits up to 60 seconds for exactly one new `.mp4`
      in `~/Downloads`, which is where Josh's Chrome saves downloads (see "Before the first run"
      at the top of this stage). Chrome names the file after the canvas, for example
      `Chart Card 42.mp4`, with ` (1)`-style suffixes on repeats, so the command matches by time,
      not by name. It moves the file to `graphics_output/beat_<n>.candidate.mp4`, verifies that,
      and only then renames it to `graphics_output/beat_<n>.mp4`:

      ```bash
      .venv/bin/python -c "
      import glob, json, os, shutil, subprocess, sys, time
      from motion_graphics.verify import ClipVerificationError, verify_exported_clip

      beat_index = sys.argv[1]
      entries = json.load(open('graphic_beats.json'))
      target_duration = next(e for e in entries if e['beat_index'] == int(beat_index))['target_duration']
      started = float(open(f'export_started_{beat_index}.txt').read())
      downloads = os.path.expanduser('~/Downloads')

      deadline = time.time() + 60
      while True:
          new = [p for p in glob.glob(os.path.join(downloads, '*.mp4')) if os.path.getmtime(p) >= started]
          pending = [p for p in glob.glob(os.path.join(downloads, '*.crdownload')) if os.path.getmtime(p) >= started]
          if new and not pending:
              break
          if time.time() > deadline:
              print(f'NO DOWNLOAD for beat {beat_index}: no finished .mp4 in {downloads} since export started')
              sys.exit(3)
          time.sleep(2)
      if len(new) != 1:
          raise RuntimeError(f'expected exactly one new .mp4 in {downloads}, found {new} — move/rename by hand is NOT safe; report this')

      dest = f'graphics_output/beat_{beat_index}.mp4'
      # Atomic write (HANDOFF lesson 10, same as assembly/build.py): verify a candidate file and
      # only os.replace() it onto dest once it passes, so a failure never leaves an unverified
      # file at dest (or clobbers an earlier good clip there).
      candidate = f'graphics_output/beat_{beat_index}.candidate.mp4'
      os.makedirs('graphics_output', exist_ok=True)
      shutil.move(new[0], candidate)
      try:
          verify_exported_clip(candidate, target_duration)
          # verify_exported_clip doesn't check resolution; a misclicked 1280x720 radio must not pass.
          res = subprocess.run(
              ['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height',
               '-of', 'csv=p=0', candidate], capture_output=True, text=True,
          ).stdout.strip()
          if res != '1920,1080':
              raise ClipVerificationError(f'{candidate} is {res or \"unreadable\"}, expected 1920,1080 — wrong export resolution picked')
      except Exception:
          if os.path.exists(candidate):
              os.remove(candidate)
          raise
      os.replace(candidate, dest)
      print(f'beat {beat_index}: exported and verified {dest} (from {os.path.basename(new[0])})')
      " <beat_index>
      ```

      If it exits with status 3 (`NO DOWNLOAD`), click the dialog's "Download" button exactly once
      and run this command again. If it still exits 3, STOP and report it. Once it succeeds,
      click "Done" in the dialog and close the beat's tab. If it raises `RuntimeError` (more than
      one new `.mp4`), STOP and report the file list. Do not guess which one is right. If
      it raises `ClipVerificationError` (missing file, too small, unreadable by `ffprobe`, duration
      more than 1 second off target, or resolution not exactly 1920×1080), STOP and report the
      exact error with the beat's index, archetype, and canvas URL. The bad file (the
      `.candidate.mp4`) has already been deleted, and nothing was written to
      `graphics_output/beat_<beat_index>.mp4`. A resolution failure almost always means the wrong
      radio was selected in Procedure E step 4. Report it anyway; do not silently re-export.

   **Catch-all: stage-level failures.** Apart from sub-step d's two per-beat verdicts (which are
   flagged and skipped, not fatal), every STOP above ends the whole stage, and so does any other
   browser failure: the `claude-in-chrome` tools being unreachable, claude.ai/design not loading,
   a Cloudflare or login page, no design system matching `GRAPHICS_DESIGN_SYSTEM_NAME`, a missing
   button, an unexpected dialog, or anything else that differs from the UI described here. These
   are stage-level because they will almost certainly repeat on every later beat. Report the beat
   index, the canvas URL if one exists, what you did, and what you saw, including a screenshot,
   plus which beats (if any) were already exported or flagged before the stop. Do not retry
   blindly, and do not improvise a different path through the product.

3. Report to the user: how many graphic beats were rendered, how many (if any) were flagged as
   rejected or not approved within the attempt cap (for each flagged beat: its index, archetype,
   the reviewer's reasoning, and its canvas URL, so Josh can review or fix them after the run),
   and the `graphics_output/` directory that contains the exported clips. This is the
   deliverable for this stage. Stage 4 (Final Assembly) consumes it alongside `footage_output/`
   and `shot_list.json`. A flagged beat has no `graphics_output/beat_<n>.mp4`, so Stage 4 will
   refuse to run (`MissingClipsError`) until each flagged beat has a clip.

---

# Stage 4 (Final Assembly)

Run this after Stage 1 (`shot_list.json`), Stage 2 (`footage_output/`), and Stage 3
(`graphics_output/`) have all completed for this video. Requires `ffmpeg` and `ffprobe` on
`PATH` (already required indirectly by Stage 3's clip verification) and the voiceover audio
file's path (the same recording used for Stage 1's forced alignment). `page_stills/` (Stage 1 Step 1c)
and `image_stills/` (Stage 1 Step 1d) belong to the LAST Stage 1 run; run Stage 4 right after this
video's own Stage 1 Steps 1c and 1d, never after starting Stage 1 for another video.

Unlike every earlier stage, this one needs no subagent — compositing already-approved clips
together is purely mechanical `ffmpeg` orchestration, so it runs as a single script.

Talking-head beats (from `**...**` in the script) need no source file: `assemble` makes each one
as a silent black 1920x1080 clip of exactly its spoken length, directly in the staging directory.

Page-highlight beats (from italic links with a `#:~:text=` highlight) need `page_stills/page_<n>.png`
and `page_<n>_plain.png` from Stage 1 Step 1c; `assemble` turns them into a clip (the highlight
fades in over the blurred page, with a slow push-in) for exactly the beat's spoken time. A missing
still fails like a missing clip (`MissingClipsError`); re-run Stage 1 Step 1c, not Stage 2/3.

Image beats (from non-italic hyperlinks to an image file) need `image_stills/image_<n>.<ext>`
from Stage 1 Step 1d; `assemble` builds the clip (a blurred, darkened copy of the image behind, the
sharp original centered, a slow push-in) for exactly the beat's spoken time. A missing file fails
like a missing clip (`MissingClipsError`); re-run Stage 1 Step 1d, not Stage 2/3. Only the first
frame of a GIF or WebP is used. Transparent images are flattened onto white (both the sharp image
and its blurred background), and a photo's EXIF rotation is not applied: a sideways-tagged JPEG
shows as stored.

The push-in clips (page highlights and show-as-is images) are upscaled to 7680x4320 before the zoom so the slow push-in stays smooth (`zoompan` crops at whole pixels; measured sub-pixel jitter), so a 4 s clip takes a few seconds to render.

Every `ffmpeg` invocation this stage makes uses `-y` (force overwrite), so a previous run's
staging or final-output files are always overwritten fresh, never silently reused — there is no
directory to manually clear between runs, unlike Stage 2/3.

## Steps

1. Run the full assembly pipeline:

   ```bash
   .venv/bin/python -c "
   import json, sys
   from shot_list.models import ShotList, beat_from_dict
   from assembly.beats import resolve_beat_clips
   from assembly.build import assemble

   audio_path = sys.argv[1]

   raw = json.load(open('shot_list.json'))
   beats = [beat_from_dict(b) for b in raw['beats']]
   shot_list = ShotList(beats=beats, duration=raw['duration'])

   clips = resolve_beat_clips(shot_list)

   final_path = assemble(
       clips=clips, audio_path=audio_path, staging_dir='assembly_staging',
       final_path='final_output/assembled.mp4', total_duration=shot_list.duration,
   )
   print(f'Final video assembled: {final_path}')
   " <audio_path>
   ```

   A `TypeError` from `beat_from_dict` (a `GraphicSpec`/`FootageSpec`/`PageSpec` argument) means an older-format shot_list.json (from before the
   7-archetype set): STOP and regenerate it with Stage 1.

   If this raises `MissingClipsError`, STOP and report every missing beat listed in the
   error — then re-run ONLY Step 2 (the per-beat sourcing loop) of Stage 2/3 for those specific
   missing beat indices; do not re-run this stage until every beat has a real clip. Do NOT
   re-run Step 1 of Stage 2/3 to do this — Step 1 starts with a full `shutil.rmtree` of
   `footage_output/`/`graphics_output/` for a fresh video, which would delete every
   already-approved clip (including human-reviewed motion-graphics exports), not just the
   missing ones. If any `ffmpeg` step raises (`NormalizeError`, `ConcatError`,
   `MuxError`), STOP and report the exact error, including the real `ffmpeg` stderr it
   contains — never retry blindly or fall back to a different approach silently. If
   `FinalOutputVerificationError` is raised, STOP and report it; the final file is not usable
   (Global Constraint: fail loudly).

2. Report to the user: the path to the final assembled video (`final_output/assembled.mp4`).
   This is the deliverable for the entire pipeline.
