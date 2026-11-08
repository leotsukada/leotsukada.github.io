# Website editor

A local app for editing the site without touching HTML.

## Start it

Double-click **`Open Editor.command`** in Finder, or run:

```sh
python3 _editor/editor.py
```

Your browser opens the editor. Stop it with Ctrl+C in the terminal window.
Only Python 3 is needed; there is nothing to install.

> If macOS says the `.command` file can't be opened, right-click it → Open once,
> or run `chmod +x "_editor/Open Editor.command"`.

## Use it

1. **Edit**: pick a section on the left, or click anything in the preview on the right.
   - *What's new*: add, reorder (drag the ⠿ handle), hide or delete news items.
     To add an image, click the image box and paste a screenshot (⌘V), or drag a file onto it.
   - *Header & hero*: drag the name, tagline or image credit in the preview to move them.
     They snap to the center and to each other (hold ⌥ to move freely). Exact X/Y values,
     text alignment and "Reset to automatic layout" are in the panel. Phones keep the centered layout.
   - *Colors*: menu bar text and background, social icons (X, LinkedIn…), hero text,
     section titles, footer and the accent color. Empty = default; a note warns if text becomes hard to read.
     Each social icon can also have its own color in *Menu & social* ("Use brand colors" sets the official ones).
   - *Images*: every file in `assets/images`. Upload several at once (button, drag & drop or ⌘V),
     filter by name or Used/Unused, preview, copy a path, rename, and select several
     (shift-click for a range) to delete them together. Images still used anywhere — including
     unsaved edits and hand-made pages like `page2.html` — can't be deleted. Renaming updates the
     editor's pages automatically, but is refused if a hand-made page, CSS or JS file uses the image.
   - *About Me*, *Contact*, *Menu & social*, *Sub pages*, *Site settings*.
2. **Save** (⌘S) regenerates `index.html`, `page1.html` and `page3.html`.
3. **Publish…** commits the saved changes and runs `git push`, so GitHub Pages updates the live site.

Undo/redo (⌘Z / ⇧⌘Z) works for everything since the editor was opened.

## How it fits together

| File | Purpose |
| --- | --- |
| `content.json` | All the site's text, links and image paths. **This is the source of truth.** |
| `build.py` | Turns `content.json` into the HTML pages (`python3 _editor/build.py`). |
| `editor.py` | Local server for the editor (listens on 127.0.0.1 only). |
| `editor.html` | The editor interface. |

Styling lives in `assets/css/site.css`, behaviour in `assets/js/site.js`.
Don't edit the generated HTML pages by hand: the next save overwrites them.
Because this folder starts with `_`, GitHub Pages does not publish it.

To replace the resume, overwrite `assets/files/resume.pdf` with the new PDF and publish.
