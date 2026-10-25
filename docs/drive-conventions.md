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
- The first album in that order is featured at the top of the index as "Latest album". To
  choose it, give it the lowest prefix (`01 Book I`). The others follow as cards in the same
  order, and the album pages' Previous/Next links follow it too.
- The album title shown on the site is the folder name exactly as written, prefix included.
- Photos are ordered by filename, naturally. The order decides the album page layout: photos
  are cropped into a mosaic (shown whole in the lightbox and on phones), and the 1st and 6th
  of every 8 get the big tiles. Put the photos that should be big in those positions. If
  the count isn't a multiple of 4, the last 1-3 photos get larger tiles (one leftover is full
  width) so there are no gaps.
- The cover is a file named `cover.*`, otherwise the first photo. The index crops it to fill
  its card (16:9 for the featured album; cards are taller or wider depending on how many
  share the row), so keep the subject near the center.
- Supported: JPEG, PNG, WebP. Other files and shortcuts are skipped.
- Each album's URL slug comes from its title ("01 Book I" -> `/01-book-i/`). If two albums
  share a slug, the later one gets `-2`, `-3`, and so on.
- Empty albums are not published.
- The root folder can live in My Drive or in a shared drive.
