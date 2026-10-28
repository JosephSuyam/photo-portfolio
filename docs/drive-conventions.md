# Drive folder conventions

```
Portfolio/            <- root folder (DRIVE_ROOT_FOLDER_ID)
  about.json          <- optional, About page at /about/
  contact.json        <- optional, Contact page at /contact/
  01 Book I/          <- album "01 Book I", URL /01-book-i/
    cover.jpg         <- album cover
    001.jpg
    002.jpg
  Book 2/
  Book 10/
```

## Albums

- Albums are the immediate subfolders of the root. Deeper folders are ignored.
- Albums are ordered by folder name, naturally ("Book 2" before "Book 10"). Prefix with numbers (`01 Book I`) to force an order.
- The index shows one full-screen album after another in that order, numbered "01 / 03" and so on. To choose the first, give it the lowest prefix (`01 Book I`). The album pages' Previous/Next links follow the same order.
- The album title shown on the site is the folder name exactly as written, prefix included.
- Photos are ordered by filename, naturally, and the album page shows them in that order in a mosaic of cropped tiles: mostly squares, large and small, plus a few 2:1 tiles where the last photos close the grid; on a phone every tile is square. A tile's size depends on the photo's position, not its shape (in each full group of six, the 1st and 4th are large). Panoramas and tall portraits lose their edges in the mosaic, so keep the subject near the center. Clicking a tile opens the photo whole.
- The cover is a file named `cover.*`, otherwise the first photo. It is cropped to fill the screen (landscape on a computer, portrait on a phone, where a landscape cover shows only its middle) on the index, at the top of its album page, and in the "Next album" banner of the album before it. The title is set over its lower-left corner and the site menu over its top, so keep the subject near the center and clear of the bottom-left. Clicking the cover on the album page opens it whole.
- Supported: JPEG, PNG, WebP. Other files and shortcuts are skipped.
- Each album's URL slug comes from its title ("01 Book I" -> `/01-book-i/`). If two albums share a slug, the later one gets `-2`, `-3`, and so on. `work`, `static`, `images`, `about`, `contact`, and `api` belong to the site, so an album folder named "About" gets `/about-2/` and "Contact" gets `/contact-2/`.
- Empty albums are not published.
- The root folder can live in My Drive or in a shared drive.

## About and Contact pages

Upload `about.json` and `contact.json` to the Drive root, next to the album folders. They are then shared with the service account like everything else in the root. Ready-to-edit samples: [`docs/examples/about.json`](examples/about.json) and [`docs/examples/contact.json`](examples/contact.json).

- Names are matched ignoring case and surrounding spaces (`About.JSON` works; `about.txt`, `about`, `about.json.txt` don't). Other files in the root are ignored.
- Files are matched by name, whatever type Drive gives them (`application/json`, `text/plain`, ...). Folders, shortcuts, and files Drive converted (e.g. to a Google Doc) are skipped with a warning. Keep Drive's "Convert uploads" setting off, or the upload becomes a Google Doc.
- Several files with the same name: the first usable one in natural order wins; the others are skipped with a warning.
- No file -> no page and no nav link. Files over 64 KiB, not UTF-8, not valid JSON, or not in the shape below are skipped with a warning, and the page is left out. The warning names the field (e.g. `details.1.label: Field required`) but never shows the contents. One invalid entry in `details` (e.g. an empty `label`) leaves out the whole Contact page.
- JSON has no comments, so keys the site doesn't use (such as `"_comment"`) are ignored. A misspelled key (`"paragraph"`) is ignored too. If a key appears twice, the last one is used. Invisible control characters (e.g. NUL, bidi overrides) are removed from the About text.

`about.json`: `lede` (required) is shown large; each entry of `paragraphs` (optional) is one paragraph. Line breaks and repeated spaces inside a string become single spaces; empty paragraphs are dropped.

```json
{
  "lede": "I photograph people at work.",
  "paragraphs": ["Based in Lisbon, shooting portraits and editorial commissions since 2015."]
}
```

`contact.json`: `email` (optional) is shown large at the top; `details` (optional) are listed in order, each with a `label` and a `value` (both non-empty text).

```json
{
  "email": "hello@example.com",
  "details": [
    { "label": "Instagram", "value": "https://instagram.com/yourhandle" },
    { "label": "Studio", "value": "studio@example.com" },
    { "label": "Based in", "value": "Lisbon, Portugal" }
  ]
}
```

- An `email` that isn't an address is dropped with a warning; the details are kept. No `email` and no `details` -> no page (with a warning).
- `https://` and `http://` values become links, shown without the scheme and trailing `/` (`instagram.com/yourhandle`). Email addresses become `mailto:` links.
- Anything else (`@yourhandle`, `Lisbon, Portugal`) is plain text.
- With a `contact.json`, the About page ends with a link to Contact.
- An optional message form: see [Setup](setup.md#contact-form-optional).
