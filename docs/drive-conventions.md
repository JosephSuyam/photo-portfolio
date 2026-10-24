# Drive folder conventions

```
Portfolio/            <- root folder (DRIVE_ROOT_FOLDER_ID)
  01 Book I/          <- album "01 Book I", URL /01-book-i/
    cover.jpg         <- album cover
    001.jpg
    002.jpg
  Book 2/
  Book 10/
```

- Albums are the immediate subfolders of the root. Deeper folders are ignored.
- Albums are ordered by folder name, naturally ("Book 2" before "Book 10"). Prefix with numbers
  (`01 Book I`) to force an order.
- The album title shown on the site is the folder name exactly as written, prefix included.
- Photos are ordered by filename, naturally.
- The cover is a file named `cover.*`, otherwise the first photo.
- Supported: JPEG, PNG, WebP. Other files and shortcuts are skipped.
- Each album's URL slug comes from its title ("01 Book I" -> `/01-book-i/`). If two albums
  share a slug, the later one gets `-2`, `-3`, and so on.
- Empty albums are not published.
- The root folder can live in My Drive or in a shared drive.
