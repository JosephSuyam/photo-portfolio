import { expect, test, type Locator, type Page } from "@playwright/test";

const ALBUMS = [
  { title: "Book I", slug: "book-i", photos: 3, hasCoverFile: true },
  { title: "Book II", slug: "book-ii", photos: 2, hasCoverFile: false },
  { title: "Portraits", slug: "portraits", photos: 4, hasCoverFile: false },
  { title: "Landscapes", slug: "landscapes", photos: 11, hasCoverFile: false },
  {
    title: "The Long Road North Through Every Small Coastal Town In The Middle Of Deep Winter",
    slug: "the-long-road-north",
    photos: 2,
    hasCoverFile: false,
  },
  { title: "Still Life", slug: "still-life", photos: 1, hasCoverFile: false },
];
const FIRST_ALBUM = ALBUMS[0];
const LAST_ALBUM = ALBUMS[ALBUMS.length - 1];
/** Albums after the first, shown as cards in the grid below the feature card. */
const GRID_ALBUMS = ALBUMS.slice(1);
/** A grid card that is neither first nor last; the album the hover preview tests show. */
const PREVIEWED = ALBUMS[2];
/** Eleven photos of mixed ratios in several justified rows; the album the lightbox and layout tests browse. */
const LANDSCAPES = ALBUMS[3];
const LONG_TITLE_ALBUM = ALBUMS[4];
const SINGLE_PHOTO_ALBUM = LAST_ALBUM;
const SITE_TITLE = "Reel E2E";
/** A site title too long for one line at the 40px desktop size in a 1280px window. */
const VERY_LONG_SITE_TITLE = "Reel E2E Fine Art, Documentary and Editorial Photography Company of Lisbon";
const PHOTO_TOTAL = ALBUMS.reduce((sum, album) => sum + album.photos, 0);
/** `--bg` of each theme, as computed `background-color`. */
const LIGHT_BACKGROUND = "rgb(255, 255, 255)";
const DARK_BACKGROUND = "rgb(0, 0, 0)";
/** Dark-theme `--fg` and `--muted` channel values (#f2f2f2, #8f8f8f). */
const DARK_FG_CHANNEL = 242;
const DARK_MUTED_CHANNEL = 143;
/** Text overlaid on photos is always white, in both themes. */
const OVERLAY_TEXT = "rgb(255, 255, 255)";
/** Album page rows start at this height before stretching to fill the width; ROW_HEIGHT_VW in build.py. */
const ROW_HEIGHT_VW = 28;

function photoCount(count: number): string {
  return `${count} photo${count === 1 ? "" : "s"}`;
}

function escapeRegExp(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** Matches text ending in `title`, so "Book I" does not also match "Book II". */
function endsWithTitle(title: string): RegExp {
  return new RegExp(`(^|\\s)${escapeRegExp(title)}\\s*$`);
}

/** Footer text: the site title, then the build year. */
function footerText(): RegExp {
  return new RegExp(`${escapeRegExp(SITE_TITLE)}[\\s\\S]*© ${new Date().getFullYear()}`);
}

/** Presses Tab until `target` has focus, so it gets keyboard (`:focus-visible`) focus. */
async function tabTo(page: Page, target: Locator, maxPresses = 30): Promise<void> {
  for (let press = 0; press < maxPresses; press++) {
    if (await target.evaluate((element) => element === document.activeElement)) return;
    await page.keyboard.press("Tab");
  }
  await expect(target).toBeFocused();
}

function featureSizes(page: Page): Promise<{ source: string | null; image: string | null }> {
  return feature(page).evaluate((link) => ({
    source: link.querySelector("source")?.getAttribute("sizes") ?? null,
    image: link.querySelector("img")?.getAttribute("sizes") ?? null,
  }));
}

async function expectImageLoaded(image: Locator): Promise<void> {
  await image.scrollIntoViewIfNeeded();
  await expect
    .poll(() => image.evaluate((element: HTMLImageElement) => element.complete && element.naturalWidth > 0))
    .toBe(true);
}

function trackFailures(page: Page): string[] {
  const failures: string[] = [];
  page.on("pageerror", (error) => failures.push(`page error: ${error.message}`));
  page.on("console", (message) => {
    // Chrome's "Failed to load resource" text omits the URL; it is only in location().
    const url = message.location().url;
    if (message.type() === "error" && !url.endsWith("/favicon.ico")) {
      failures.push(`console error: ${message.text()} (${url})`);
    }
  });
  page.on("response", (response) => {
    if (response.status() >= 400 && !response.url().endsWith("/favicon.ico")) {
      failures.push(`${response.status()} ${response.url()}`);
    }
  });
  return failures;
}

function feature(page: Page): Locator {
  return page.locator("section.albums a.feature");
}

function card(page: Page, title: string): Locator {
  const exactTitle = page.locator(".album-title").getByText(title, { exact: true });
  return page.locator(".album-grid .album-card").filter({ has: exactTitle });
}

/** The index image showing `album`'s cover before any preview: the feature or its card. */
function indexCover(page: Page, album: (typeof ALBUMS)[number]): Locator {
  return album === FIRST_ALBUM ? feature(page).locator("img") : card(page, album.title).locator("img");
}

type PictureState = { webp: string | null; jpeg: string | null; width: string | null; height: string | null };

function pictureState(link: Locator): Promise<PictureState> {
  return link.evaluate((element) => {
    const source = element.querySelector("source");
    const image = element.querySelector("img");
    return {
      webp: source?.getAttribute("srcset") ?? null,
      jpeg: image?.getAttribute("srcset") ?? null,
      width: image?.getAttribute("width") ?? null,
      height: image?.getAttribute("height") ?? null,
    };
  });
}

/** Where a link leads, resolved; the preview script may store hrefs as absolute URLs. */
function linkTarget(link: Locator): Promise<string> {
  return link.evaluate((element: HTMLAnchorElement) => element.href);
}

function albumUrl(page: Page, album: (typeof ALBUMS)[number]): string {
  return new URL(`/${album.slug}/`, page.url()).href;
}

function themeToggle(page: Page): Locator {
  return page.locator(".site-nav button.theme-toggle");
}

const THEME_TRANSITION_CLASS = "theme-transition";
const HAS_THEME_TRANSITION_CLASS = new RegExp(`(^|\\s)${THEME_TRANSITION_CLASS}(\\s|$)`);
/** The fade lasts 1.5 s; the class must be gone well within this. */
const THEME_TRANSITION_SETTLE_MS = 4_000;

type ThemeTransitionEvent = { kind: "click" | "added" | "removed"; at: number };

/** Logs toggle clicks and every add/remove of the transition class on `<html>`, in page time. */
async function recordThemeTransitions(page: Page): Promise<void> {
  await page.evaluate((className) => {
    const log: ThemeTransitionEvent[] = [];
    (window as unknown as { themeTransitionLog: ThemeTransitionEvent[] }).themeTransitionLog = log;
    const root = document.documentElement;
    let present = root.classList.contains(className);
    new MutationObserver(() => {
      const now = root.classList.contains(className);
      if (now !== present) log.push({ kind: now ? "added" : "removed", at: performance.now() });
      present = now;
    }).observe(root, { attributes: true, attributeFilter: ["class"] });
    document.addEventListener(
      "click",
      (event) => {
        if ((event.target as Element).closest(".theme-toggle")) log.push({ kind: "click", at: performance.now() });
      },
      true,
    );
  }, THEME_TRANSITION_CLASS);
}

function themeTransitionLog(page: Page): Promise<ThemeTransitionEvent[]> {
  return page.evaluate(() => (window as unknown as { themeTransitionLog: ThemeTransitionEvent[] }).themeTransitionLog);
}

/** Only the adds and removes of the transition class, without the clicks. */
async function themeTransitionClassChanges(page: Page): Promise<ThemeTransitionEvent[]> {
  return (await themeTransitionLog(page)).filter((event) => event.kind !== "click");
}

/** Clicks the toggle in the page itself, `gapMs` apart, so slow test actions cannot stretch the gap. */
function clickToggleTwiceInPage(page: Page, gapMs: number): Promise<void> {
  return themeToggle(page).evaluate(async (button: HTMLButtonElement, gap) => {
    button.click();
    await new Promise((resolve) => setTimeout(resolve, gap));
    button.click();
  }, gapMs);
}

/** Whether `color` is an opaque `rgb()` with every channel strictly between dark and light. */
function isBetweenThemeBackgrounds(color: string): boolean {
  const match = /^rgb\((\d+), (\d+), (\d+)\)$/.exec(color);
  if (!match) return false;
  const dark = [0, 0, 0];
  const light = [255, 255, 255];
  return match.slice(1).every((channel, index) => Number(channel) > dark[index] && Number(channel) < light[index]);
}

function bodyBackground(page: Page): Promise<string> {
  return page.locator("body").evaluate((body) => getComputedStyle(body).backgroundColor);
}

function horizontalOverflow(page: Page): Promise<number> {
  return page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
}

function photoLinks(page: Page): Locator {
  return page.locator(".tile a");
}

function counter(position: number, total = LANDSCAPES.photos): string {
  return `${position} / ${total}`;
}

function lightboxCounter(page: Page): Locator {
  return page.locator(".lightbox-counter");
}

function lightbox(page: Page): Locator {
  return page.getByRole("dialog", { name: "Photo viewer" });
}

async function openLightbox(page: Page, photoIndex: number): Promise<void> {
  await photoLinks(page).nth(photoIndex).click();
  await expect(page.locator(".lightbox-counter")).toHaveText(counter(photoIndex + 1));
}

/** Dispatches a one-finger swipe from the viewport centre over the lightbox image. */
function swipe(page: Page, dx: number, dy: number): Promise<void> {
  return page.locator(".lightbox-image").evaluate(
    (target, [deltaX, deltaY]) => {
      const startX = window.innerWidth / 2;
      const startY = window.innerHeight / 2;
      const touchAt = (clientX: number, clientY: number) =>
        new Touch({ identifier: 1, target, clientX, clientY });
      const start = touchAt(startX, startY);
      const end = touchAt(startX + deltaX, startY + deltaY);
      const init = { bubbles: true, cancelable: true };
      target.dispatchEvent(
        new TouchEvent("touchstart", { ...init, touches: [start], targetTouches: [start], changedTouches: [start] }),
      );
      target.dispatchEvent(
        new TouchEvent("touchmove", { ...init, touches: [end], targetTouches: [end], changedTouches: [end] }),
      );
      target.dispatchEvent(
        new TouchEvent("touchend", { ...init, touches: [], targetTouches: [], changedTouches: [end] }),
      );
    },
    [dx, dy],
  );
}

async function boxOf(locator: Locator): Promise<{ x: number; y: number; width: number; height: number }> {
  const box = await locator.boundingBox();
  expect(box).not.toBeNull();
  return box!;
}

type Box = { x: number; y: number; width: number; height: number };

/** Whether `inner` lies within `outer`, allowing `slack` px for sub-pixel rounding. */
function isInside(inner: Box, outer: Box, slack = 1): boolean {
  return (
    inner.x >= outer.x - slack &&
    inner.y >= outer.y - slack &&
    inner.x + inner.width <= outer.x + outer.width + slack &&
    inner.y + inner.height <= outer.y + outer.height + slack
  );
}

/** Width of the viewport without a vertical scrollbar. */
function layoutWidth(page: Page): Promise<number> {
  return page.evaluate(() => document.documentElement.clientWidth);
}

function setSiteTitle(page: Page, text: string): Promise<void> {
  return page.locator(".site-header .site-title").evaluate((title, value) => {
    title.textContent = value;
  }, text);
}

type TileRect = { top: number; left: number; right: number; height: number; width: number; ratio: number };

/** Album page tiles grouped into rows the way flex-wrap lays them out: a new row starts when a tile wraps left. */
function justifiedRows(page: Page): Promise<TileRect[][]> {
  return page.locator(".mosaic").evaluate((mosaic) => {
    const rows: TileRect[][] = [];
    for (const tile of mosaic.querySelectorAll<HTMLElement>(".tile")) {
      const rect = tile.getBoundingClientRect();
      const entry = {
        top: rect.top,
        left: rect.left,
        right: rect.right,
        height: rect.height,
        width: rect.width,
        ratio: Number.parseFloat(tile.style.getPropertyValue("--ratio")),
      };
      const row = rows.at(-1);
      if (!row || rect.left < row.at(-1)!.right) rows.push([entry]);
      else row.push(entry);
    }
    return rows;
  });
}

/** Whether the Bodoni Moda face has loaded and the browser can render it. */
function bodoniState(page: Page): Promise<{ check: boolean; loaded: boolean }> {
  return page.evaluate(async () => {
    await document.fonts.ready;
    const faces = Array.from(document.fonts as unknown as Iterable<FontFace>);
    return {
      check: document.fonts.check('700 40px "Bodoni Moda"'),
      loaded: faces.some((face) => face.family.replace(/["']/g, "") === "Bodoni Moda" && face.status === "loaded"),
    };
  });
}

/** Load status of each Bodoni Moda face, once font loading has settled. */
function bodoniStatuses(page: Page): Promise<string[]> {
  return page.evaluate(async () => {
    await document.fonts.ready;
    return Array.from(document.fonts as unknown as Iterable<FontFace>)
      .filter((face) => face.family.replace(/["']/g, "") === "Bodoni Moda")
      .map((face) => face.status);
  });
}

function lightboxImageSrc(page: Page): Promise<string> {
  return page.locator(".lightbox-image").evaluate((image: HTMLImageElement) => image.src);
}

function imageScale(image: Locator): Promise<number> {
  return image.evaluate((element) => {
    const transform = getComputedStyle(element).transform;
    return transform === "none" ? 1 : new DOMMatrixReadOnly(transform).a;
  });
}

/** A viewport point whose hit target is the dialog itself (its backdrop), not its contents. */
function findBackdropPoint(page: Page): Promise<{ x: number; y: number } | null> {
  return page.evaluate(() => {
    const dialog = document.querySelector("dialog.lightbox");
    const steps = 20;
    for (let row = 0; row <= steps; row++) {
      for (let column = 0; column <= steps; column++) {
        const x = Math.min(window.innerWidth - 1, (window.innerWidth * column) / steps);
        const y = Math.min(window.innerHeight - 1, (window.innerHeight * row) / steps);
        if (document.elementFromPoint(x, y) === dialog) return { x, y };
      }
    }
    return null;
  });
}

test.describe("album index", () => {
  test("heading is Work", async ({ page }) => {
    await page.goto("/work/");
    await expect(page.locator("h1.page-heading")).toHaveText("Work");
  });

  test("meta line counts albums and photographs", async ({ page }) => {
    await page.goto("/work/");
    await expect(page.locator(".page-meta")).toHaveText(`${ALBUMS.length} albums · ${PHOTO_TOTAL} photographs`);
  });

  test("feature card shows the first album", async ({ page }) => {
    await page.goto("/work/");
    await expect(feature(page).locator(".feature-title")).toHaveText(FIRST_ALBUM.title);
  });

  test("feature card is labelled Latest album", async ({ page }) => {
    await page.goto("/work/");
    await expect(feature(page).locator(".feature-label")).toHaveText("Latest album");
  });

  test("feature card shows the first album's photo count", async ({ page }) => {
    await page.goto("/work/");
    await expect(feature(page).locator(".feature-count")).toHaveText(photoCount(FIRST_ALBUM.photos));
  });

  test("feature card links to the first album", async ({ page }) => {
    await page.goto("/");
    await feature(page).click();
    await expect(page).toHaveURL(new RegExp(`/${FIRST_ALBUM.slug}/$`));
  });

  test("grid lists the other albums in order", async ({ page }) => {
    await page.goto("/work/");
    await expect(page.locator(".album-grid .album-title")).toHaveText(GRID_ALBUMS.map((album) => album.title));
  });

  test("grid cards show photo counts", async ({ page }) => {
    await page.goto("/work/");
    await expect(page.locator(".album-grid .album-count")).toHaveText(
      GRID_ALBUMS.map((album) => photoCount(album.photos)),
    );
  });

  test("shows a cover image for every album", async ({ page }) => {
    await page.goto("/work/");
    for (const album of ALBUMS) {
      await expectImageLoaded(indexCover(page, album));
    }
  });

  test("cards link to their album pages", async ({ page }) => {
    await page.goto("/");
    await card(page, "Book II").locator("a").click();
    await expect(page).toHaveURL(/\/book-ii\/$/);
  });

  test("marks Work as the current page", async ({ page }) => {
    await page.goto("/work/");
    await expect(page.getByRole("link", { name: "Work", exact: true })).toHaveAttribute("aria-current", "page");
  });

  test("footer shows the site title and build year", async ({ page }) => {
    await page.goto("/work/");
    await expect(page.locator("footer.site-footer")).toContainText(
      footerText(),
    );
  });

  for (const album of ALBUMS) {
    const rule = album.hasCoverFile ? "uses the cover.* file" : "uses the first photo";
    test(`${album.title} cover ${rule}`, async ({ page }) => {
      await page.goto("/work/");
      const coverSrcset = await indexCover(page, album).getAttribute("srcset");
      await page.goto(`/${album.slug}/`);
      const firstPhotoSrcset = await page.locator(".tile img").first().getAttribute("srcset");
      if (album.hasCoverFile) {
        expect(coverSrcset).not.toBe(firstPhotoSrcset);
      } else {
        expect(coverSrcset).toBe(firstPhotoSrcset);
      }
    });
  }
});

test.describe("album preview on hover", () => {
  test.skip(({ isMobile }) => isMobile, "hover needs a mouse");

  test.beforeEach(async ({ page }) => {
    await page.goto("/work/");
  });

  async function hoverPreviewedCard(page: Page): Promise<void> {
    await card(page, PREVIEWED.title).locator("a").hover();
  }

  test("hovering a card shows its title in the feature", async ({ page }) => {
    await hoverPreviewedCard(page);
    await expect(feature(page).locator(".feature-title")).toHaveText(PREVIEWED.title);
  });

  test("hovering a card shows its photo count in the feature", async ({ page }) => {
    await hoverPreviewedCard(page);
    await expect(feature(page).locator(".feature-count")).toHaveText(photoCount(PREVIEWED.photos));
  });

  test("hovering a card points the feature link at its album", async ({ page }) => {
    await hoverPreviewedCard(page);
    await expect.poll(() => linkTarget(feature(page))).toBe(albumUrl(page, PREVIEWED));
  });

  test("hovering a card shows its cover in the feature", async ({ page }) => {
    const expected = await pictureState(card(page, PREVIEWED.title));
    await hoverPreviewedCard(page);
    await expect.poll(() => pictureState(feature(page))).toEqual(expected);
  });

  test("hovering a card loads its cover in the feature", async ({ page }) => {
    const candidates = await card(page, PREVIEWED.title)
      .locator("a")
      .evaluate((link) =>
        Array.from(link.querySelectorAll("source, img"), (element) => element.getAttribute("srcset") ?? "")
          .flatMap((srcset) => srcset.split(","))
          .map((candidate) => new URL(candidate.trim().split(" ")[0], document.baseURI).href),
      );
    await hoverPreviewedCard(page);
    const image = feature(page).locator("img");
    await expectImageLoaded(image);
    await expect
      .poll(() => image.evaluate((element: HTMLImageElement, urls) => urls.includes(element.currentSrc), candidates))
      .toBe(true);
  });

  test("hovering a card hides the Latest album label", async ({ page }) => {
    await hoverPreviewedCard(page);
    await expect(feature(page).locator(".feature-label")).toHaveCount(1);
    await expect(feature(page).locator(".feature-label")).toBeHidden();
  });

  test("moving from a card onto the feature and clicking opens the previewed album", async ({ page }) => {
    await hoverPreviewedCard(page);
    // The full-bleed feature is taller than half the window: scroll its bottom edge to mid-screen.
    await feature(page)
      .locator(".feature-frame")
      .evaluate((frame) => window.scrollBy(0, frame.getBoundingClientRect().bottom - window.innerHeight / 2));
    const cardFrame = await boxOf(card(page, PREVIEWED.title).locator(".album-frame"));
    const featureFrame = await boxOf(feature(page).locator(".feature-frame"));
    const x = cardFrame.x + cardFrame.width / 2;
    const fromY = cardFrame.y + 10;
    const toY = featureFrame.y + featureFrame.height - 10;
    const viewportHeight = page.viewportSize()?.height ?? 0;
    // Straight up from the card must land on the feature frame, with both ends on screen.
    expect(x).toBeLessThan(featureFrame.x + featureFrame.width);
    expect(toY).toBeGreaterThan(0);
    expect(fromY).toBeLessThan(viewportHeight);
    await page.mouse.move(x, fromY);
    await page.mouse.move(x, toY, { steps: 15 });
    await page.mouse.click(x, toY);
    await expect(page).toHaveURL(new RegExp(`/${PREVIEWED.slug}/$`));
  });

  test("leaving the albums section restores the first album's title", async ({ page }) => {
    await hoverPreviewedCard(page);
    await expect(feature(page).locator(".feature-title")).toHaveText(PREVIEWED.title);
    await page.locator("h1.page-heading").hover();
    await expect(feature(page).locator(".feature-title")).toHaveText(FIRST_ALBUM.title);
  });

  test("leaving the albums section shows the Latest album label again", async ({ page }) => {
    await hoverPreviewedCard(page);
    await expect(feature(page).locator(".feature-label")).toHaveCount(1);
    await expect(feature(page).locator(".feature-label")).toBeHidden();
    await page.locator("h1.page-heading").hover();
    await expect(feature(page).locator(".feature-label")).toBeVisible();
  });

  test("leaving the albums section restores the first album's cover and link", async ({ page }) => {
    const initial = { picture: await pictureState(feature(page)), href: albumUrl(page, FIRST_ALBUM) };
    await hoverPreviewedCard(page);
    await expect.poll(() => linkTarget(feature(page))).toBe(albumUrl(page, PREVIEWED));
    await page.locator("h1.page-heading").hover();
    await expect
      .poll(async () => ({ picture: await pictureState(feature(page)), href: await linkTarget(feature(page)) }))
      .toEqual(initial);
  });

  test("hovering a card sets the feature sizes from the card", async ({ page }) => {
    const expected = await card(page, PREVIEWED.title).locator("a").getAttribute("data-feature-sizes");
    expect(expected).toMatch(/vw$/);
    await hoverPreviewedCard(page);
    await expect.poll(() => featureSizes(page)).toEqual({ source: expected, image: expected });
  });

  test("leaving the albums section restores the feature sizes", async ({ page }) => {
    const initial = await featureSizes(page);
    await hoverPreviewedCard(page);
    await expect(feature(page).locator(".feature-title")).toHaveText(PREVIEWED.title);
    await page.locator("h1.page-heading").hover();
    await expect.poll(() => featureSizes(page)).toEqual(initial);
  });

  test("mouse leaving the section keeps a preview the keyboard focus is on", async ({ page }) => {
    await tabTo(page, card(page, PREVIEWED.title).locator("a"));
    await expect(feature(page).locator(".feature-title")).toHaveText(PREVIEWED.title);
    await feature(page).locator(".feature-frame").hover();
    await page.locator("h1.page-heading").hover();
    await expect(feature(page).locator(".feature-title")).toHaveText(PREVIEWED.title);
  });
});

test.describe("album preview on keyboard focus", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/work/");
  });

  test("tabbing to a card shows its album in the feature", async ({ page }) => {
    await tabTo(page, card(page, PREVIEWED.title).locator("a"));
    await expect(feature(page).locator(".feature-title")).toHaveText(PREVIEWED.title);
  });

  test("tabbing back from a card to the feature keeps the preview", async ({ page }) => {
    const firstCard = GRID_ALBUMS[0];
    await tabTo(page, card(page, firstCard.title).locator("a"));
    await expect(feature(page).locator(".feature-title")).toHaveText(firstCard.title);
    await page.keyboard.press("Shift+Tab");
    await expect(feature(page)).toBeFocused();
    await expect.poll(() => linkTarget(feature(page))).toBe(albumUrl(page, firstCard));
  });

  test("focus leaving the albums section restores the first album", async ({ page }) => {
    await tabTo(page, card(page, PREVIEWED.title).locator("a"));
    await expect(feature(page).locator(".feature-title")).toHaveText(PREVIEWED.title);
    await page.locator(".site-title").focus();
    await expect(feature(page).locator(".feature-title")).toHaveText(FIRST_ALBUM.title);
  });
});

test.describe("album preview by pointer type", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/work/");
  });

  /** Dispatches pointerenter on the previewed card and returns the feature title right after. */
  function featureTitleAfterPointerEnter(page: Page, pointerType: string): Promise<string> {
    return card(page, PREVIEWED.title)
      .locator("a")
      .evaluate((link, type) => {
        link.dispatchEvent(new PointerEvent("pointerenter", { pointerType: type }));
        return document.querySelector(".feature-title")?.textContent?.trim() ?? "";
      }, pointerType);
  }

  test("a mouse entering a card previews it", async ({ page }) => {
    expect(await featureTitleAfterPointerEnter(page, "mouse")).toBe(PREVIEWED.title);
  });

  test("a touch entering a card does not preview it", async ({ page }) => {
    expect(await featureTitleAfterPointerEnter(page, "touch")).toBe(FIRST_ALBUM.title);
  });

  test.describe("on touch screens", () => {
    test.skip(({ isMobile }) => !isMobile, "taps need a touch screen");

    test("tapping a card opens its album", async ({ page }) => {
      await card(page, PREVIEWED.title).locator("a").tap();
      await expect(page).toHaveURL(new RegExp(`/${PREVIEWED.slug}/$`));
    });
  });
});

/** Desktop windows from wide to just above the 767px phone breakpoint; the default project window is 1440x900. */
const DESKTOP_VIEWPORTS = [
  { width: 1440, height: 900 },
  { width: 1280, height: 800 },
  { width: 1024, height: 768 },
  { width: 1000, height: 800 },
  { width: 800, height: 1000 },
];

for (const { width, height } of DESKTOP_VIEWPORTS) {
  test.describe(`desktop browser at ${width}x${height}`, () => {
    test.skip(({ isMobile }) => isMobile, "a desktop window");
    test.use({ viewport: { width, height } });

    test("album index has no horizontal overflow", async ({ page }) => {
      await page.goto("/work/");
      expect(await horizontalOverflow(page)).toBeLessThanOrEqual(0);
    });

    for (const album of [LANDSCAPES, LONG_TITLE_ALBUM]) {
      test(`${album.slug} album page has no horizontal overflow`, async ({ page }) => {
        await page.goto(`/${album.slug}/`);
        expect(await horizontalOverflow(page)).toBeLessThanOrEqual(0);
      });
    }

    test("a very long site title causes no horizontal overflow", async ({ page }) => {
      await page.goto("/work/");
      await setSiteTitle(page, VERY_LONG_SITE_TITLE);
      expect(await horizontalOverflow(page)).toBeLessThanOrEqual(0);
    });

    test("feature frame is 21:9", async ({ page }) => {
      await page.goto("/work/");
      const frame = await boxOf(feature(page).locator(".feature-frame"));
      expect(frame.width / frame.height).toBeCloseTo(21 / 9, 1);
    });

    test("feature frame spans the full window width", async ({ page }) => {
      await page.goto("/work/");
      const frame = await boxOf(feature(page).locator(".feature-frame"));
      const full = await layoutWidth(page);
      expect({ left: Math.round(frame.x), width: Math.round(frame.width) }).toEqual({ left: 0, width: full });
    });

    test("feature text sits inside its frame", async ({ page }) => {
      await page.goto("/work/");
      const frame = await boxOf(feature(page).locator(".feature-frame"));
      const text = await boxOf(feature(page).locator(".feature-text"));
      expect(isInside(text, frame), `text ${JSON.stringify(text)} frame ${JSON.stringify(frame)}`).toBe(true);
    });
  });
}

test.describe("album index on desktop", () => {
  test.skip(({ isMobile }) => isMobile, "desktop layout only");

  test.beforeEach(async ({ page }) => {
    await page.goto("/work/");
  });

  test("cards sit two to a row with a lone last card", async ({ page }) => {
    const tops = await page
      .locator(".album-grid .album-card")
      .evaluateAll((cards) => cards.map((element) => Math.round(element.getBoundingClientRect().top)));
    const perRow = [...new Set(tops)].map((top) => tops.filter((value) => value === top).length);
    expect(perRow).toEqual([2, 2, 1]);
  });

  test("card frames all have the same height", async ({ page }) => {
    const heights = await page
      .locator(".album-grid .album-frame")
      .evaluateAll((frames) => frames.map((element) => element.getBoundingClientRect().height));
    expect(Math.max(...heights) - Math.min(...heights)).toBeLessThanOrEqual(1);
  });

  test("each grid row spans the full grid width", async ({ page }) => {
    const worstGap = await page.locator(".album-grid").evaluate((grid) => {
      const style = getComputedStyle(grid);
      const box = grid.getBoundingClientRect();
      const left = box.left + Number.parseFloat(style.paddingLeft) + Number.parseFloat(style.borderLeftWidth);
      const right = box.right - Number.parseFloat(style.paddingRight) - Number.parseFloat(style.borderRightWidth);
      const rows = new Map<number, DOMRect[]>();
      for (const element of grid.querySelectorAll(".album-card")) {
        const rect = element.getBoundingClientRect();
        rows.set(Math.round(rect.top), [...(rows.get(Math.round(rect.top)) ?? []), rect]);
      }
      return Math.max(
        ...Array.from(rows.values(), (rects) =>
          Math.max(
            Math.abs(Math.min(...rects.map((rect) => rect.left)) - left),
            Math.abs(right - Math.max(...rects.map((rect) => rect.right))),
          ),
        ),
      );
    });
    expect(worstGap).toBeLessThanOrEqual(3);
  });

  test("album grid spans the full window width", async ({ page }) => {
    const grid = await boxOf(page.locator(".album-grid"));
    const full = await layoutWidth(page);
    expect({ left: Math.round(grid.x), width: Math.round(grid.width) }).toEqual({ left: 0, width: full });
  });

  test("span-6 card frames are 3:2", async ({ page }) => {
    const ratios = await page
      .locator(".album-card--span-6 .album-frame")
      .evaluateAll((frames) =>
        frames.map((element) => element.getBoundingClientRect().width / element.getBoundingClientRect().height),
      );
    expect({ count: ratios.length, worst: Math.max(...ratios.map((ratio) => Math.abs(ratio - 3 / 2))) < 0.03 }).toEqual({
      count: 4,
      worst: true,
    });
  });

  test("the lone last card spans the full grid width", async ({ page }) => {
    const lastCard = page.locator(".album-grid .album-card").last();
    await expect(lastCard).toHaveClass(/\balbum-card--span-12\b/);
    const cardBox = await boxOf(lastCard);
    const grid = await boxOf(page.locator(".album-grid"));
    expect(Math.abs(cardBox.width - grid.width)).toBeLessThanOrEqual(1);
  });

  test("the lone last card frame is 3:1", async ({ page }) => {
    const frame = await boxOf(card(page, LAST_ALBUM.title).locator(".album-frame"));
    expect(frame.width / frame.height).toBeCloseTo(3, 1);
  });

  for (const album of [PREVIEWED, LAST_ALBUM]) {
    test(`${album.title} card title and count sit inside its frame`, async ({ page }) => {
      const frame = await boxOf(card(page, album.title).locator(".album-frame"));
      const title = await boxOf(card(page, album.title).locator(".album-title"));
      const count = await boxOf(card(page, album.title).locator(".album-count"));
      expect([isInside(title, frame), isInside(count, frame)]).toEqual([true, true]);
    });
  }

  test("a long card title stays inside its frame", async ({ page }) => {
    const frame = await boxOf(card(page, LONG_TITLE_ALBUM.title).locator(".album-frame"));
    const title = await boxOf(card(page, LONG_TITLE_ALBUM.title).locator(".album-title"));
    expect(isInside(title, frame), `title ${JSON.stringify(title)} frame ${JSON.stringify(frame)}`).toBe(true);
  });

  test("feature text sits at the bottom left of its frame", async ({ page }) => {
    const frame = await boxOf(feature(page).locator(".feature-frame"));
    const text = await boxOf(feature(page).locator(".feature-text"));
    expect({
      nearLeft: text.x - frame.x <= 60,
      nearBottom: frame.y + frame.height - (text.y + text.height) <= 60,
    }).toEqual({ nearLeft: true, nearBottom: true });
  });

  test("hovering a card zooms its cover", async ({ page }) => {
    const target = card(page, PREVIEWED.title);
    await target.locator("a").hover();
    await expect.poll(() => imageScale(target.locator("img")), { timeout: 3_000 }).toBeCloseTo(1.03, 2);
  });

  test.describe("with reduced motion", () => {
    test.use({ reducedMotion: "reduce" });

    test("hovering a card neither zooms nor animates its cover", async ({ page }) => {
      const target = card(page, PREVIEWED.title);
      await target.locator("a").hover();
      await expect.poll(() => target.evaluate((element) => element.matches(":hover"))).toBe(true);
      const state = await target.locator("img").evaluate((image) => ({
        transform: getComputedStyle(image).transform,
        running: image.getAnimations().length,
      }));
      expect(state).toEqual({ transform: "none", running: 0 });
    });
  });

  test("site title is centred above the navigation", async ({ page }) => {
    const title = await boxOf(page.locator(".site-header .site-title"));
    const links = await page
      .locator(".site-header .site-nav a")
      .evaluateAll((elements) => elements.map((element) => element.getBoundingClientRect()));
    const navLeft = Math.min(...links.map((rect) => rect.left));
    const navRight = Math.max(...links.map((rect) => rect.right));
    const navTop = Math.min(...links.map((rect) => rect.top));
    const centre = (await layoutWidth(page)) / 2;
    expect({
      titleAboveNav: title.y + title.height <= navTop + 1,
      titleCentred: Math.abs(title.x + title.width / 2 - centre) <= 2,
      navCentred: Math.abs((navLeft + navRight) / 2 - centre) <= 2,
    }).toEqual({ titleAboveNav: true, titleCentred: true, navCentred: true });
  });

  test("theme toggle sits at the top right, level with the title", async ({ page }) => {
    const toggle = await boxOf(themeToggle(page));
    const title = await boxOf(page.locator(".site-header .site-title"));
    const full = await layoutWidth(page);
    const toggleMiddle = toggle.y + toggle.height / 2;
    expect({
      rightInset: Math.abs(full - (toggle.x + toggle.width) - 24) <= 4,
      levelWithTitle: toggleMiddle >= title.y && toggleMiddle <= title.y + title.height,
    }).toEqual({ rightInset: true, levelWithTitle: true });
  });
});

for (const colorScheme of ["light", "dark"] as const) {
  test.describe(`overlay text in the ${colorScheme} theme`, () => {
    test.use({ colorScheme });

    for (const selector of [".feature-title", ".feature-count", ".album-title", ".album-count"]) {
      test(`${selector} is white`, async ({ page }) => {
        await page.goto("/work/");
        await expect(page.locator(`section.albums ${selector}`).first()).toHaveCSS("color", OVERLAY_TEXT);
      });
    }
  });
}

test.describe("display font", () => {
  test("Bodoni Moda loads", async ({ page }) => {
    await page.goto("/work/");
    await expect.poll(() => bodoniState(page)).toEqual({ check: true, loaded: true });
  });

  for (const selector of [".site-header .site-title", "h1.page-heading", ".feature-title"]) {
    test(`${selector} is set in Bodoni Moda`, async ({ page }) => {
      await page.goto("/work/");
      await expect(page.locator(selector)).toHaveCSS("font-family", /^"?Bodoni Moda"?,/);
    });
  }

  test("site title is bold", async ({ page }) => {
    await page.goto("/work/");
    await expect(page.locator(".site-header .site-title")).toHaveCSS("font-weight", "700");
  });

  test.describe("when the font file fails to load", () => {
    test.beforeEach(async ({ page }) => {
      await page.route("**/*.woff2", (route) => route.abort());
      await page.goto("/work/");
    });

    test("the font face is reported as failed", async ({ page }) => {
      await expect.poll(() => bodoniStatuses(page)).toEqual(["error"]);
    });

    test("the site title still renders", async ({ page }) => {
      await expect(page.locator(".site-header .site-title")).toBeVisible();
    });

    test("the page has no horizontal overflow", async ({ page }) => {
      await page.evaluate(() => document.fonts.ready);
      expect(await horizontalOverflow(page)).toBeLessThanOrEqual(0);
    });
  });
});

test.describe("album index on phones", () => {
  test.skip(({ isMobile }) => !isMobile, "mobile layout only");

  test.beforeEach(async ({ page }) => {
    await page.goto("/work/");
  });

  test("feature and cards form a single column", async ({ page }) => {
    const lefts = await page
      .locator(".feature-frame, .album-grid .album-card")
      .evaluateAll((elements) => elements.map((element) => Math.round(element.getBoundingClientRect().left)));
    expect(new Set(lefts).size).toBe(1);
  });

  test("feature and cards span the full screen width", async ({ page }) => {
    const widths = await page
      .locator(".feature-frame, .album-grid .album-card")
      .evaluateAll((elements) => elements.map((element) => Math.round(element.getBoundingClientRect().width)));
    const full = await layoutWidth(page);
    expect(widths).toEqual(widths.map(() => full));
  });

  test("feature text sits inside its frame", async ({ page }) => {
    const frame = await boxOf(feature(page).locator(".feature-frame"));
    const text = await boxOf(feature(page).locator(".feature-text"));
    expect(isInside(text, frame), `text ${JSON.stringify(text)} frame ${JSON.stringify(frame)}`).toBe(true);
  });

  test("feature frame is 4:5", async ({ page }) => {
    const frame = await boxOf(feature(page).locator(".feature-frame"));
    expect(frame.width / frame.height).toBeCloseTo(4 / 5, 1);
  });

  test("every card frame is 3:2, including the lone last card", async ({ page }) => {
    const ratios = await page
      .locator(".album-frame")
      .evaluateAll((frames) =>
        frames.map((element) => element.getBoundingClientRect().width / element.getBoundingClientRect().height),
      );
    expect(Math.max(...ratios.map((ratio) => Math.abs(ratio - 3 / 2)))).toBeLessThan(0.03);
  });

  test("site title sits above the navigation", async ({ page }) => {
    const title = await boxOf(page.locator(".site-header .site-title"));
    const nav = await boxOf(page.locator(".site-header .site-nav a").first());
    expect(nav.y).toBeGreaterThanOrEqual(title.y + title.height - 1);
  });

  test("page has no horizontal overflow", async ({ page }) => {
    expect(await horizontalOverflow(page)).toBeLessThanOrEqual(0);
  });
});

for (const viewport of [
  { width: 412, height: 915 },
  { width: 360, height: 740 },
]) {
  test.describe(`phone at ${viewport.width}x${viewport.height}`, () => {
    test.skip(({ isMobile }) => !isMobile, "mobile layout only");
    test.use({ viewport });

    for (const path of ["/work/", `/${LANDSCAPES.slug}/`, `/${LONG_TITLE_ALBUM.slug}/`]) {
      test(`${path} has no horizontal overflow`, async ({ page }) => {
        await page.goto(path);
        expect(await horizontalOverflow(page)).toBeLessThanOrEqual(0);
      });
    }

    test("a very long site title causes no horizontal overflow", async ({ page }) => {
      await page.goto("/work/");
      await setSiteTitle(page, VERY_LONG_SITE_TITLE);
      expect(await horizontalOverflow(page)).toBeLessThanOrEqual(0);
    });
  });
}

test.describe("theme with a light OS setting", () => {
  test.use({ colorScheme: "light" });

  test.beforeEach(async ({ page }) => {
    await page.goto("/work/");
  });

  test("page is light by default", async ({ page }) => {
    await expect(page.locator("body")).toHaveCSS("background-color", LIGHT_BACKGROUND);
  });

  test("toggle button is visible", async ({ page }) => {
    await expect(themeToggle(page)).toBeVisible();
  });

  test("toggle offers dark mode", async ({ page }) => {
    await expect(themeToggle(page)).toHaveAttribute("aria-label", "Switch to dark mode");
  });

  test("clicking the toggle switches to dark", async ({ page }) => {
    await themeToggle(page).click();
    await expect(page.locator("body")).toHaveCSS("background-color", DARK_BACKGROUND);
  });

  test("clicking the toggle then offers light mode", async ({ page }) => {
    await themeToggle(page).click();
    await expect(themeToggle(page)).toHaveAttribute("aria-label", "Switch to light mode");
  });

  test("clicking the toggle twice returns to light", async ({ page }) => {
    await themeToggle(page).click();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
    await themeToggle(page).click();
    await expect(page.locator("body")).toHaveCSS("background-color", LIGHT_BACKGROUND);
  });

  test("chosen theme is stored", async ({ page }) => {
    await themeToggle(page).click();
    await expect.poll(() => page.evaluate(() => localStorage.getItem("portfolio-theme"))).toBe("dark");
  });

  test("chosen theme persists across a reload", async ({ page }) => {
    await themeToggle(page).click();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
    await page.reload();
    await expect(page.locator("body")).toHaveCSS("background-color", DARK_BACKGROUND);
  });

  test("chosen theme applies on album pages", async ({ page }) => {
    await themeToggle(page).click();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
    await page.goto(`/${LANDSCAPES.slug}/`);
    await expect(page.locator("body")).toHaveCSS("background-color", DARK_BACKGROUND);
  });

  test("viewer keeps its dark backdrop", async ({ page }) => {
    await page.goto(`/${LANDSCAPES.slug}/`);
    await openLightbox(page, 0);
    const backdrop = await lightbox(page).evaluate((dialog) => getComputedStyle(dialog, "::backdrop").backgroundColor);
    expect(backdrop).toBe("rgba(0, 0, 0, 0.92)");
  });

  test("page follows an OS switch to dark while open", async ({ page }) => {
    await page.emulateMedia({ colorScheme: "dark" });
    await expect(page.locator("body")).toHaveCSS("background-color", DARK_BACKGROUND);
  });

  test("toggle label follows an OS switch to dark while open", async ({ page }) => {
    await page.emulateMedia({ colorScheme: "dark" });
    await expect(themeToggle(page)).toHaveAttribute("aria-label", "Switch to light mode");
  });

  test.describe("with a stored light choice", () => {
    test.beforeEach(async ({ page }) => {
      await page.evaluate(() => localStorage.setItem("portfolio-theme", "light"));
      await page.reload();
      await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
    });

    test("page stays light after an OS switch to dark", async ({ page }) => {
      await page.emulateMedia({ colorScheme: "dark" });
      await expect(page.locator("body")).toHaveCSS("background-color", LIGHT_BACKGROUND);
    });

    test("toggle still offers dark mode after an OS switch to dark", async ({ page }) => {
      await page.emulateMedia({ colorScheme: "dark" });
      await expect(themeToggle(page)).toHaveAttribute("aria-label", "Switch to dark mode");
    });
  });

  test("toggle label matches a stored theme after reload", async ({ page }) => {
    await themeToggle(page).click();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
    await page.reload();
    await expect(themeToggle(page)).toHaveAttribute("aria-label", "Switch to light mode");
  });
});

test.describe("theme transition", () => {
  test.use({ colorScheme: "light" });

  test.beforeEach(async ({ page }) => {
    await page.goto("/work/");
    await recordThemeTransitions(page);
  });

  test("clicking the toggle adds the transition class", async ({ page }) => {
    await themeToggle(page).click();
    await expect(page.locator("html")).toHaveClass(HAS_THEME_TRANSITION_CLASS);
  });

  test("clicking the toggle fades the colour tokens on the root over 1.5 s", async ({ page }) => {
    const rootTransition = await themeToggle(page).evaluate((button: HTMLButtonElement) => {
      button.click();
      const style = getComputedStyle(document.documentElement);
      const properties = style.transitionProperty.split(",").map((part) => part.trim());
      const durations = style.transitionDuration.split(",").map((part) => part.trim());
      return ["--bg", "--fg"].map((token) => ({ token, duration: durations[properties.indexOf(token)] ?? null }));
    });
    expect(rootTransition).toEqual([
      { token: "--bg", duration: "1.5s" },
      { token: "--fg", duration: "1.5s" },
    ]);
  });

  test("only the root runs a CSS transition mid-fade", async ({ page }) => {
    const targets = await themeToggle(page).evaluate(async (button: HTMLButtonElement) => {
      button.click();
      await new Promise((resolve) => setTimeout(resolve, 300));
      return {
        fading: document.documentElement.classList.contains("theme-transition"),
        others: document
          .getAnimations()
          .filter((animation) => animation instanceof CSSTransition)
          .map((animation) => (animation.effect as KeyframeEffect).target)
          .filter((target) => target !== document.documentElement)
          .map((target) => (target instanceof Element ? `${target.tagName}.${target.getAttribute("class") ?? ""}` : String(target))),
      };
    });
    expect(targets).toEqual({ fading: true, others: [] });
  });

  test("nested text reaches its final colour by the end of the fade", async ({ page }) => {
    // On /work/ the first nav link is the current page (--fg); the meta line and footer are --muted.
    const selectors = [".site-title", ".site-nav a", ".theme-toggle", ".page-meta", ".site-footer"];
    const sample = await page.evaluate(async (selectors) => {
      const colours = () => selectors.map((selector) => getComputedStyle(document.querySelector(selector)!).color);
      document.querySelector<HTMLButtonElement>(".site-nav button.theme-toggle")!.click();
      // The fade lasts 1500 ms and the class is removed at 1600 ms; sample in between.
      await new Promise((resolve) => setTimeout(resolve, 1_520));
      const atEnd = colours();
      const fading = document.documentElement.classList.contains("theme-transition");
      return { fading, atEnd };
    }, selectors);
    const channels = (colour: string) => (/^rgb\((\d+), (\d+), (\d+)\)$/.exec(colour) ?? []).slice(1).map(Number);
    const finalChannels = [DARK_FG_CHANNEL, DARK_FG_CHANNEL, DARK_FG_CHANNEL, DARK_MUTED_CHANNEL, DARK_MUTED_CHANNEL].map(
      (value) => [value, value, value],
    );
    const farthest = Math.max(
      ...sample.atEnd.flatMap((colour, index) => {
        const actual = channels(colour);
        return actual.length === 3 ? actual.map((value, channel) => Math.abs(value - finalChannels[index][channel])) : [Infinity];
      }),
    );
    expect({ fading: sample.fading, withinFewUnits: farthest <= 4 }, `colours ${sample.atEnd.join(" | ")}`).toEqual({
      fading: true,
      withinFewUnits: true,
    });
  });

  test("background is between the two colours mid-fade", async ({ page }) => {
    await themeToggle(page).click();
    await expect
      .poll(async () => isBetweenThemeBackgrounds(await bodyBackground(page)), {
        intervals: [50],
        timeout: 1_500,
      })
      .toBe(true);
  });

  test("transition class is removed after the fade", async ({ page }) => {
    await themeToggle(page).click();
    await expect(page.locator("html")).toHaveClass(HAS_THEME_TRANSITION_CLASS);
    await expect(page.locator("html")).not.toHaveClass(HAS_THEME_TRANSITION_CLASS, {
      timeout: THEME_TRANSITION_SETTLE_MS,
    });
  });

  test("transition class lasts a little over 1.5 s", async ({ page }) => {
    await themeToggle(page).click();
    await expect
      .poll(async () => (await themeTransitionClassChanges(page)).map((event) => event.kind), {
        timeout: THEME_TRANSITION_SETTLE_MS,
      })
      .toEqual(["added", "removed"]);
    const [added, removed] = await themeTransitionClassChanges(page);
    const lasted = removed.at - added.at;
    expect(lasted >= 1_450 && lasted <= 3_000, `class lasted ${lasted} ms`).toBe(true);
  });

  test("background reaches dark after the fade", async ({ page }) => {
    await themeToggle(page).click();
    await expect(page.locator("html")).not.toHaveClass(HAS_THEME_TRANSITION_CLASS, {
      timeout: THEME_TRANSITION_SETTLE_MS,
    });
    expect(await bodyBackground(page)).toBe(DARK_BACKGROUND);
  });

  test("page loads without the transition class", async ({ page }) => {
    expect((await page.locator("html").getAttribute("class")) ?? "").not.toMatch(HAS_THEME_TRANSITION_CLASS);
  });

  test("OS switch to dark adds no transition class", async ({ page }) => {
    await page.emulateMedia({ colorScheme: "dark" });
    await expect(page.locator("body")).toHaveCSS("background-color", DARK_BACKGROUND);
    expect(await themeTransitionClassChanges(page)).toEqual([]);
  });

  test("rapid double click ends on light", async ({ page }) => {
    await themeToggle(page).click();
    await themeToggle(page).click();
    await expect(page.locator("html")).not.toHaveClass(HAS_THEME_TRANSITION_CLASS, {
      timeout: THEME_TRANSITION_SETTLE_MS,
    });
    expect(await bodyBackground(page)).toBe(LIGHT_BACKGROUND);
  });

  test("rapid double click keeps the class until the fade ends", async ({ page }) => {
    await clickToggleTwiceInPage(page, 0);
    await expect
      .poll(async () => (await themeTransitionClassChanges(page)).some((event) => event.kind === "removed"), {
        timeout: THEME_TRANSITION_SETTLE_MS,
      })
      .toBe(true);
    const log = await themeTransitionLog(page);
    const lastClick = log.filter((event) => event.kind === "click").at(-1)!;
    const classChanges = log.filter((event) => event.kind !== "click");
    expect({
      changes: classChanges.map((event) => event.kind),
      removedAfterLastClick: classChanges.at(-1)!.at > lastClick.at,
    }).toEqual({ changes: ["added", "removed"], removedAfterLastClick: true });
  });

  test("second click restarts the 1.5 s timer", async ({ page }) => {
    // Far enough into the first fade that a timer which did not restart would end ~1 s after the second click.
    await clickToggleTwiceInPage(page, 500);
    await expect
      .poll(async () => (await themeTransitionClassChanges(page)).some((event) => event.kind === "removed"), {
        timeout: THEME_TRANSITION_SETTLE_MS,
      })
      .toBe(true);
    const log = await themeTransitionLog(page);
    const lastClick = log.filter((event) => event.kind === "click").at(-1)!;
    const classChanges = log.filter((event) => event.kind !== "click");
    const afterLastClick = classChanges.at(-1)!.at - lastClick.at;
    expect(
      { changes: classChanges.map((event) => event.kind), restarted: afterLastClick >= 1_450 },
      `class removed ${afterLastClick} ms after the last click`,
    ).toEqual({ changes: ["added", "removed"], restarted: true });
  });

  test("photos keep their own transition during the fade", async ({ page }) => {
    await page.goto(`/${LANDSCAPES.slug}/`);
    const duringFade = await page.evaluate(() => {
      document.querySelector<HTMLButtonElement>(".site-nav button.theme-toggle")!.click();
      return {
        fading: document.documentElement.classList.contains("theme-transition"),
        photoTransition: getComputedStyle(document.querySelector(".tile img")!).transitionProperty,
      };
    });
    expect(duringFade).toEqual({ fading: true, photoTransition: "transform" });
  });

  test.describe("with a stored dark choice", () => {
    test.beforeEach(async ({ page }) => {
      await page.evaluate(() => localStorage.setItem("portfolio-theme", "dark"));
      await page.reload();
    });

    test("page loads dark without the transition class", async ({ page }) => {
      expect((await page.locator("html").getAttribute("class")) ?? "").not.toMatch(HAS_THEME_TRANSITION_CLASS);
    });

    test("background is dark as soon as the page loads", async ({ page }) => {
      expect(await bodyBackground(page)).toBe(DARK_BACKGROUND);
    });
  });

  test.describe("with reduced motion", () => {
    test.use({ reducedMotion: "reduce" });

    test("clicking the toggle switches to dark instantly", async ({ page }) => {
      await themeToggle(page).click();
      expect(await bodyBackground(page)).toBe(DARK_BACKGROUND);
    });

    test("clicking the toggle never adds the transition class", async ({ page }) => {
      await themeToggle(page).click();
      await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
      expect(await themeTransitionClassChanges(page)).toEqual([]);
    });
  });
});

test.describe("theme with a dark OS setting", () => {
  test.use({ colorScheme: "dark" });

  test.beforeEach(async ({ page }) => {
    await page.goto("/work/");
  });

  test("page is dark by default", async ({ page }) => {
    await expect(page.locator("body")).toHaveCSS("background-color", DARK_BACKGROUND);
  });

  test("toggle offers light mode", async ({ page }) => {
    await expect(themeToggle(page)).toHaveAttribute("aria-label", "Switch to light mode");
  });

  test("clicking the toggle switches to light", async ({ page }) => {
    await themeToggle(page).click();
    await expect(page.locator("body")).toHaveCSS("background-color", LIGHT_BACKGROUND);
  });

  test("a stored light choice overrides the OS after a reload", async ({ page }) => {
    await themeToggle(page).click();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
    await page.reload();
    await expect(page.locator("body")).toHaveCSS("background-color", LIGHT_BACKGROUND);
  });
});

test.describe("theme when storage is blocked", () => {
  test.use({ colorScheme: "light" });

  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      Object.defineProperty(window, "localStorage", {
        configurable: true,
        get() {
          throw new DOMException("Storage is blocked", "SecurityError");
        },
      });
    });
  });

  test("storage access throws in this context", async ({ page }) => {
    await page.goto("/work/");
    const blocked = await page.evaluate(() => {
      try {
        return localStorage === null;
      } catch {
        return true;
      }
    });
    expect(blocked).toBe(true);
  });

  test("pages load without script errors", async ({ page }) => {
    const failures = trackFailures(page);
    await page.goto("/work/");
    await themeToggle(page).click();
    await page.goto(`/${LANDSCAPES.slug}/`);
    expect(failures).toEqual([]);
  });

  test("toggle still switches the theme", async ({ page }) => {
    await page.goto("/work/");
    await themeToggle(page).click();
    await expect(page.locator("body")).toHaveCSS("background-color", DARK_BACKGROUND);
  });
});

test.describe("theme without JavaScript", () => {
  test.use({ javaScriptEnabled: false });

  test("toggle button is hidden", async ({ page }) => {
    await page.goto("/work/");
    await expect(themeToggle(page)).toHaveCount(1);
    await expect(themeToggle(page)).toBeHidden();
  });

  test.describe("with a dark OS setting", () => {
    test.use({ colorScheme: "dark" });

    test("page follows the OS and is dark", async ({ page }) => {
      await page.goto("/work/");
      await expect(page.locator("body")).toHaveCSS("background-color", DARK_BACKGROUND);
    });
  });
});

test.describe("album page", () => {
  for (const album of ALBUMS) {
    test(`${album.title} shows all ${album.photos} photos`, async ({ page }) => {
      await page.goto(`/${album.slug}/`);
      const photos = page.locator(".tile img");
      await expect(photos).toHaveCount(album.photos);
      for (const photo of await photos.all()) {
        await expectImageLoaded(photo);
      }
    });
  }

  test("Next links to the following album", async ({ page }) => {
    await page.goto(`/${FIRST_ALBUM.slug}/`);
    await page.locator(".album-pager a.pager-next").click();
    await expect(page).toHaveURL(new RegExp(`/${ALBUMS[1].slug}/$`));
  });

  test("Previous links to the preceding album", async ({ page }) => {
    await page.goto(`/${PREVIEWED.slug}/`);
    await page.locator(".album-pager a.pager-prev").click();
    await expect(page).toHaveURL(new RegExp(`/${ALBUMS[1].slug}/$`));
  });

  test("Next on the last album wraps to the first", async ({ page }) => {
    await page.goto(`/${LAST_ALBUM.slug}/`);
    await expect(page.locator(".album-pager a.pager-next")).toHaveAttribute("href", `/${FIRST_ALBUM.slug}/`);
  });

  test("Previous on the first album wraps to the last", async ({ page }) => {
    await page.goto(`/${FIRST_ALBUM.slug}/`);
    await expect(page.locator(".album-pager a.pager-prev")).toHaveAttribute("href", `/${LAST_ALBUM.slug}/`);
  });

  test("Next shows the following album's title", async ({ page }) => {
    await page.goto(`/${LAST_ALBUM.slug}/`);
    await expect(page.locator(".album-pager a.pager-next")).toHaveText(endsWithTitle(FIRST_ALBUM.title));
  });

  test("Previous shows the preceding album's title", async ({ page }) => {
    await page.goto(`/${FIRST_ALBUM.slug}/`);
    await expect(page.locator(".album-pager a.pager-prev")).toHaveText(endsWithTitle(LAST_ALBUM.title));
  });

  test("Previous sits left of Next on desktop and above it on phones", async ({ page, isMobile }) => {
    await page.goto(`/${PREVIEWED.slug}/`);
    const previous = await boxOf(page.locator(".album-pager a.pager-prev"));
    const next = await boxOf(page.locator(".album-pager a.pager-next"));
    if (isMobile) {
      expect(previous.y + previous.height).toBeLessThanOrEqual(next.y + 1);
    } else {
      expect(previous.x + previous.width).toBeLessThanOrEqual(next.x + 1);
    }
  });

  test("has the album title in the page title", async ({ page }) => {
    await page.goto("/portraits/");
    await expect(page).toHaveTitle("Portraits | Reel E2E");
  });

  test("shows the album title as a visible heading", async ({ page }) => {
    await page.goto("/portraits/");
    await expect(page.locator("h1.album-heading")).toBeVisible();
  });

  test("heading text is the album title", async ({ page }) => {
    await page.goto("/portraits/");
    await expect(page.locator("h1.album-heading")).toHaveText("Portraits");
  });

  test("heading is not uppercased", async ({ page }) => {
    await page.goto("/portraits/");
    await expect(page.locator("h1.album-heading")).toHaveCSS("text-transform", "none");
  });

  test("heading is set in a serif face", async ({ page }) => {
    await page.goto("/portraits/");
    await expect(page.locator("h1.album-heading")).toHaveCSS("font-family", /Georgia/);
  });

  test("heading is set in Bodoni Moda", async ({ page }) => {
    await page.goto("/portraits/");
    await expect(page.locator("h1.album-heading")).toHaveCSS("font-family", /^"?Bodoni Moda"?,/);
  });

  test("heading is centred", async ({ page }) => {
    await page.goto("/portraits/");
    await expect(page.locator("h1.album-heading")).toHaveCSS("text-align", "center");
  });

  test("shows the photo count", async ({ page }) => {
    await page.goto(`/${LANDSCAPES.slug}/`);
    await expect(page.locator("main .album-count")).toHaveText(photoCount(LANDSCAPES.photos));
  });

  test("footer shows the site title and build year", async ({ page }) => {
    await page.goto(`/${LANDSCAPES.slug}/`);
    const footer = page.locator("footer.site-footer");
    await footer.scrollIntoViewIfNeeded();
    await expect(footer).toBeVisible();
    await expect(footer).toContainText(footerText());
  });

  test("header scrolls away with the page", async ({ page }) => {
    await page.goto(`/${LANDSCAPES.slug}/`);
    const header = page.locator(".site-header");
    const { height } = await boxOf(header);
    await page.evaluate((distance) => window.scrollTo(0, distance), height + 200);
    await expect.poll(async () => (await boxOf(header)).y).toBeLessThan(0);
  });
});

test.describe("single-photo album", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(`/${SINGLE_PHOTO_ALBUM.slug}/`);
  });

  test("its only tile is not stretched to fill a desktop row", async ({ page, isMobile }) => {
    test.skip(isMobile, "phones show every tile full width");
    const tile = await boxOf(page.locator(".tile"));
    const rowHeight = (ROW_HEIGHT_VW * (await page.evaluate(() => window.innerWidth))) / 100;
    expect(Math.abs(tile.height - rowHeight), `tile ${tile.height}px, row ${rowHeight}px`).toBeLessThanOrEqual(2);
  });

  test("its only tile is full width on phones", async ({ page, isMobile }) => {
    test.skip(!isMobile, "desktop rows keep the base row height");
    const tile = await boxOf(page.locator(".tile"));
    expect(Math.round(tile.width)).toBe(await layoutWidth(page));
  });

  for (const name of ["Previous photo", "Next photo"]) {
    test(`viewer hides the ${name} button`, async ({ page }) => {
      await photoLinks(page).first().click();
      await expect(lightboxCounter(page)).toHaveText(counter(1, SINGLE_PHOTO_ALBUM.photos));
      await expect(lightbox(page).getByRole("button", { name, exact: true })).toBeHidden();
    });
  }
});

test.describe("lightbox", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(`/${LANDSCAPES.slug}/`);
  });

  test("clicking a photo opens the viewer", async ({ page }) => {
    await photoLinks(page).first().click();
    await expect(lightbox(page)).toBeVisible();
  });

  test("clicking a photo stays on the album page", async ({ page }) => {
    await openLightbox(page, 0);
    await expect(page).toHaveURL(new RegExp(`/${LANDSCAPES.slug}/$`));
  });

  test("viewer image loads", async ({ page }) => {
    await openLightbox(page, 0);
    await expectImageLoaded(page.locator(".lightbox-image"));
  });

  test("viewer image is the clicked photo's link target", async ({ page }) => {
    await openLightbox(page, 0);
    const href = await photoLinks(page).first().evaluate((link: HTMLAnchorElement) => link.href);
    await expect.poll(() => lightboxImageSrc(page)).toBe(href);
  });

  test("viewer image alt names its position", async ({ page }) => {
    await openLightbox(page, 2);
    await expect(page.locator(".lightbox-image")).toHaveAttribute("alt", `Photo 3 of ${LANDSCAPES.photos}`);
  });

  test("counter shows the first photo", async ({ page }) => {
    await photoLinks(page).first().click();
    await expect(page.locator(".lightbox-counter")).toHaveText(counter(1));
  });

  test("opens at the clicked photo", async ({ page }) => {
    await photoLinks(page).nth(2).click();
    await expect(page.locator(".lightbox-counter")).toHaveText(counter(3));
  });

  test("ArrowRight shows the next photo", async ({ page }) => {
    await openLightbox(page, 0);
    await page.keyboard.press("ArrowRight");
    await expect(page.locator(".lightbox-counter")).toHaveText(counter(2));
  });

  test("ArrowRight changes the image to the next photo", async ({ page }) => {
    await openLightbox(page, 0);
    await page.keyboard.press("ArrowRight");
    const href = await photoLinks(page).nth(1).evaluate((link: HTMLAnchorElement) => link.href);
    await expect.poll(() => lightboxImageSrc(page)).toBe(href);
  });

  test("ArrowRight on the last photo wraps to the first", async ({ page }) => {
    await openLightbox(page, LANDSCAPES.photos - 1);
    await page.keyboard.press("ArrowRight");
    await expect(page.locator(".lightbox-counter")).toHaveText(counter(1));
  });

  test("ArrowLeft on the first photo wraps to the last", async ({ page }) => {
    await openLightbox(page, 0);
    await page.keyboard.press("ArrowLeft");
    await expect(page.locator(".lightbox-counter")).toHaveText(counter(LANDSCAPES.photos));
  });

  test("Next button advances", async ({ page }) => {
    await openLightbox(page, 0);
    await lightbox(page).getByRole("button", { name: "Next photo", exact: true }).click();
    await expect(page.locator(".lightbox-counter")).toHaveText(counter(2));
  });

  test("Previous button goes back", async ({ page }) => {
    await openLightbox(page, 2);
    await lightbox(page).getByRole("button", { name: "Previous photo", exact: true }).click();
    await expect(page.locator(".lightbox-counter")).toHaveText(counter(2));
  });

  test("Escape closes the viewer", async ({ page }) => {
    await openLightbox(page, 0);
    await page.keyboard.press("Escape");
    await expect(lightbox(page)).toBeHidden();
  });

  test("Close button closes the viewer", async ({ page }) => {
    await openLightbox(page, 0);
    await lightbox(page).getByRole("button", { name: "Close", exact: true }).click();
    await expect(lightbox(page)).toBeHidden();
  });

  test("clicking the backdrop closes the viewer", async ({ page }) => {
    await openLightbox(page, 0);
    const point = await findBackdropPoint(page);
    expect(point, "no point outside the image and controls hits the dialog").not.toBeNull();
    await page.mouse.click(point!.x, point!.y);
    await expect(lightbox(page)).toBeHidden();
  });

  test("closing returns focus to the opened photo's link", async ({ page }) => {
    await openLightbox(page, 0);
    await page.keyboard.press("Escape");
    await expect(photoLinks(page).first()).toBeFocused();
  });

  test("closing returns focus to the link of the photo last shown", async ({ page }) => {
    await openLightbox(page, 0);
    await page.keyboard.press("ArrowRight");
    await expect(page.locator(".lightbox-counter")).toHaveText(counter(2));
    await page.keyboard.press("Escape");
    await expect(photoLinks(page).nth(1)).toBeFocused();
  });

  // overflow: hidden blocks wheel and touch scrolling but, by the CSSOM View spec, not
  // window.scrollBy(), so the lock is asserted through the root's computed overflow.
  test("page scrolling is locked while the viewer is open", async ({ page }) => {
    await openLightbox(page, 0);
    await expect(page.locator("html")).toHaveCSS("overflow-y", "hidden");
  });

  test("page scrolling is unlocked after the viewer closes", async ({ page }) => {
    await openLightbox(page, 0);
    await page.keyboard.press("Escape");
    await expect(page.locator("html")).not.toHaveCSS("overflow-y", "hidden");
  });

  for (const modifier of ["Control", "Meta"] as const) {
    test(`${modifier}+click on a photo does not open the viewer`, async ({ page, context }) => {
      context.on("page", (opened) => void opened.close());
      await photoLinks(page).first().click({ modifiers: [modifier] });
      await expect(lightbox(page)).toBeHidden();
    });
  }
});

test.describe("lightbox on desktop", () => {
  test.skip(({ isMobile }) => isMobile, "keyboard shortcuts are a desktop concern");

  test.beforeEach(async ({ page }) => {
    await page.goto(`/${LANDSCAPES.slug}/`);
  });

  test("Alt+ArrowRight does not change the photo", async ({ page }) => {
    await openLightbox(page, 0);
    await page.keyboard.press("Alt+ArrowRight");
    // A plain ArrowRight afterwards lands on 2 only if Alt+ArrowRight was ignored.
    await page.keyboard.press("ArrowRight");
    await expect(lightboxCounter(page)).toHaveText(counter(2));
  });
});

test.describe("lightbox on touch screens", () => {
  test.skip(({ isMobile }) => !isMobile, "swipes need a touch screen");

  test.beforeEach(async ({ page }) => {
    await page.goto(`/${LANDSCAPES.slug}/`);
  });

  test("swiping left shows the next photo", async ({ page }) => {
    await openLightbox(page, 0);
    await swipe(page, -150, 0);
    await expect(lightboxCounter(page)).toHaveText(counter(2));
  });

  test("swiping right shows the previous photo", async ({ page }) => {
    await openLightbox(page, 2);
    await swipe(page, 150, 0);
    await expect(lightboxCounter(page)).toHaveText(counter(2));
  });

  test("a mostly vertical swipe does not change the photo", async ({ page }) => {
    await openLightbox(page, 0);
    await swipe(page, -60, 200);
    // A left swipe afterwards lands on 2 only if the vertical swipe was ignored.
    await swipe(page, -150, 0);
    await expect(lightboxCounter(page)).toHaveText(counter(2));
  });
});

test.describe("without JavaScript", () => {
  test.use({ javaScriptEnabled: false });

  test("clicking a photo opens the display JPEG", async ({ page }) => {
    await page.goto(`/${LANDSCAPES.slug}/`);
    await photoLinks(page).first().click();
    await expect(page).toHaveURL(/\.jpg$/);
  });
});

for (const colorScheme of ["light", "dark"] as const) {
  test(`every page loads without errors or missing files in the ${colorScheme} theme`, async ({ page }) => {
    await page.emulateMedia({ colorScheme });
    const failures = trackFailures(page);
    for (const path of ["/", "/work/", ...ALBUMS.map((album) => `/${album.slug}/`)]) {
      await page.goto(path);
      for (const image of await page.locator("main img:not(.lightbox-image)").all()) {
        await expectImageLoaded(image);
      }
    }
    expect(failures).toEqual([]);
  });
}

test.describe("desktop", () => {
  test.skip(({ isMobile }) => isMobile, "desktop layout only");

  test("tiles in one row share a top", async ({ page }) => {
    await page.goto(`/${LANDSCAPES.slug}/`);
    const rows = await justifiedRows(page);
    const spreads = rows.map((row) => Math.max(...row.map((t) => t.top)) - Math.min(...row.map((t) => t.top)));
    expect({ rows: rows.length > 2, worst: Math.max(...spreads) <= 1 }).toEqual({ rows: true, worst: true });
  });

  test("tiles in one row share a height", async ({ page }) => {
    await page.goto(`/${LANDSCAPES.slug}/`);
    const rows = await justifiedRows(page);
    const spreads = rows.map((row) => Math.max(...row.map((t) => t.height)) - Math.min(...row.map((t) => t.height)));
    expect(Math.max(...spreads)).toBeLessThanOrEqual(1);
  });

  test("every row but the last fills the mosaic width", async ({ page }) => {
    await page.goto(`/${LANDSCAPES.slug}/`);
    const content = await page.locator(".mosaic").evaluate((mosaic) => {
      const style = getComputedStyle(mosaic);
      const box = mosaic.getBoundingClientRect();
      return { left: box.left + Number.parseFloat(style.paddingLeft), right: box.right - Number.parseFloat(style.paddingRight) };
    });
    const rows = (await justifiedRows(page)).slice(0, -1);
    const worst = Math.max(
      ...rows.map((row) => Math.max(Math.abs(row[0].left - content.left), Math.abs(content.right - row.at(-1)!.right))),
    );
    expect(worst).toBeLessThanOrEqual(2);
  });

  test("the last row is not stretched taller than the other rows", async ({ page }) => {
    await page.goto(`/${LANDSCAPES.slug}/`);
    const heights = (await justifiedRows(page)).map((row) => row[0].height);
    const last = heights.at(-1)!;
    expect(last).toBeLessThanOrEqual(Math.min(...heights.slice(0, -1)) + 1);
  });

  test("the last row keeps the base row height", async ({ page }) => {
    await page.goto(`/${LANDSCAPES.slug}/`);
    const last = (await justifiedRows(page)).at(-1)![0].height;
    const rowHeight = (ROW_HEIGHT_VW * (await page.evaluate(() => window.innerWidth))) / 100;
    expect(Math.abs(last - rowHeight), `last row ${last}px, base ${rowHeight}px`).toBeLessThanOrEqual(2);
  });

  test("tiles keep their photo's ratio", async ({ page }) => {
    await page.goto(`/${LANDSCAPES.slug}/`);
    const tiles = (await justifiedRows(page)).flat();
    const worst = Math.max(...tiles.map((tile) => Math.abs(tile.width / tile.height - tile.ratio)));
    expect(worst).toBeLessThan(0.02);
  });

  test("tile images are not cropped", async ({ page }) => {
    await page.goto(`/${LANDSCAPES.slug}/`);
    const images = page.locator(".tile img");
    for (const image of await images.all()) {
      await expectImageLoaded(image);
    }
    const worstDistortion = await images.evaluateAll((elements: HTMLImageElement[]) =>
      Math.max(
        ...elements.map((image) => {
          const tile = image.closest(".tile")!.getBoundingClientRect();
          return Math.abs(tile.width / tile.height - image.naturalWidth / image.naturalHeight);
        }),
      ),
    );
    expect(worstDistortion).toBeLessThan(0.02);
  });

  test("hovering a tile zooms its image", async ({ page }) => {
    await page.goto(`/${LANDSCAPES.slug}/`);
    const firstTile = page.locator(".tile").first();
    await firstTile.hover();
    await expect.poll(() => imageScale(firstTile.locator("img"))).toBeGreaterThan(1);
  });

  test.describe("with reduced motion", () => {
    test.use({ reducedMotion: "reduce" });

    test("hovering a tile neither zooms nor animates its image", async ({ page }) => {
      await page.goto(`/${LANDSCAPES.slug}/`);
      const firstTile = page.locator(".tile").first();
      await firstTile.hover();
      await expect.poll(() => firstTile.evaluate((element) => element.matches(":hover"))).toBe(true);
      const state = await firstTile.locator("img").evaluate((image) => ({
        transform: getComputedStyle(image).transform,
        running: image.getAnimations().length,
      }));
      expect(state).toEqual({ transform: "none", running: 0 });
    });
  });
});

test.describe("mobile", () => {
  test.skip(({ isMobile }) => !isMobile, "mobile layout only");

  test("album page has no horizontal overflow", async ({ page }) => {
    await page.goto(`/${LANDSCAPES.slug}/`);
    expect(await horizontalOverflow(page)).toBeLessThanOrEqual(0);
  });

  test("album tiles form a single column", async ({ page }) => {
    await page.goto(`/${LANDSCAPES.slug}/`);
    const lefts = await page
      .locator(".tile")
      .evaluateAll((tiles) => tiles.map((t) => Math.round(t.getBoundingClientRect().left)));
    expect(new Set(lefts).size).toBe(1);
  });

  test("album tiles span the full mosaic width", async ({ page }) => {
    await page.goto(`/${LANDSCAPES.slug}/`);
    const worstGap = await page.locator(".mosaic").evaluate((mosaic) => {
      const tiles = Array.from(mosaic.querySelectorAll(".tile"));
      return Math.max(...tiles.map((t) => Math.abs(t.getBoundingClientRect().width - mosaic.clientWidth)));
    });
    expect(worstGap).toBeLessThanOrEqual(1);
  });

  test("album tiles span the full screen width", async ({ page }) => {
    await page.goto(`/${LANDSCAPES.slug}/`);
    const widths = await page
      .locator(".tile")
      .evaluateAll((tiles) => tiles.map((t) => Math.round(t.getBoundingClientRect().width)));
    const full = await layoutWidth(page);
    expect(widths).toEqual(widths.map(() => full));
  });

  test("album tiles keep their photo's ratio", async ({ page }) => {
    await page.goto(`/${LANDSCAPES.slug}/`);
    const tiles = (await justifiedRows(page)).flat();
    const worst = Math.max(...tiles.map((tile) => Math.abs(tile.width / tile.height - tile.ratio)));
    expect(worst).toBeLessThan(0.02);
  });

  test("album photos keep their natural aspect ratio", async ({ page }) => {
    await page.goto(`/${LANDSCAPES.slug}/`);
    const images = page.locator(".tile img");
    for (const image of await images.all()) {
      await expectImageLoaded(image);
    }
    const worstDistortion = await images.evaluateAll((elements: HTMLImageElement[]) =>
      Math.max(
        ...elements.map((image) =>
          Math.abs(image.clientWidth / image.clientHeight - image.naturalWidth / image.naturalHeight),
        ),
      ),
    );
    expect(worstDistortion).toBeLessThan(0.02);
  });
});
