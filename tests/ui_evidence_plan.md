# UI evidence capture — how to reproduce M20

The screenshots in `tests/results/ui-evidence/` were captured with a real
browser driving real clicks, not with `curl`. This note records exactly how, so
the capture can be repeated or challenged.

## What is captured

| File | State | What it must show |
|---|---|---|
| `state-1-ready.png` | environment ready | every dependency ticked, "Ready to compile", build button enabled |
| `state-2-success.png` | build succeeded | pill "succeeded", duration, the PDF frame with the compiled paper |
| `state-3-failure.png` | build failed | pill "failed (exit …)", the red banner naming `sections/method.tex` |

Each PNG has a matching `.txt` accessibility snapshot next to it, which is the
text the page actually contained at capture time.

## Reproduction with the Browser pane

1. Start the server on a throwaway copy so the real sample is never broken:

   ```bash
   python -I ui/server.py --no-browser --print-url --port 8771
   ```

2. Open the printed URL (it carries `#t=…`) in the Browser pane.
3. State 1: wait for "Ready to compile"; screenshot.
4. State 2: click **Compile the paper**, wait for the pill to read
   `succeeded`, click **Open the latest PDF**, screenshot.
5. State 3: append `\undefinedmacroforademo` to `sections/method.tex`, restart
   the server on that copy, click **Compile the paper**, wait for
   `failed (exit`, screenshot. Delete the throwaway copy afterwards.

## Reproduction with a headless script

`tests/capture_ui.py` does the same thing through the gstack browse daemon when
it is running (`gstack-browse open|click|text|screenshot`). It exits `3` and
prints why if the daemon is not reachable — it does not fake a capture.

## What this evidence does not prove

- It does not prove the science. No screenshot can.
- It does not cover macOS or Linux rendering.
- A screenshot is a moment in time; the `.txt` snapshot next to it is the
  authoritative record of what the page said.
