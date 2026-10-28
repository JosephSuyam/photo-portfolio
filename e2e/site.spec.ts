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
/** An album that is neither first nor last. */
const MIDDLE_ALBUM = ALBUMS[2];
/** Eleven photos of mixed ratios: a block of six, then the five-photo remainder; the album the lightbox and layout tests browse. */
const LANDSCAPES = ALBUMS[3];
const LONG_TITLE_ALBUM = ALBUMS[4];
const SINGLE_PHOTO_ALBUM = LAST_ALBUM;
const SITE_TITLE = "Reel E2E";
/** A site title too long for one line at the 40px desktop size in a 1280px window. */
const VERY_LONG_SITE_TITLE = "Reel E2E Fine Art, Documentary and Editorial Photography Company of Lisbon";
/** `--bg` of each theme, as computed `background-color`. */
const LIGHT_BACKGROUND = "rgb(255, 255, 255)";
const DARK_BACKGROUND = "rgb(0, 0, 0)";
/** Dark-theme `--fg` and `--muted`, as computed `color`. */
const DARK_FG = "rgb(255, 255, 255)";
const DARK_MUTED = "rgba(255, 255, 255, 0.65)";
/** Text overlaid on photos is always white, in both themes; secondary text is `--on-photo-muted`. */
const OVERLAY_TEXT = "rgb(255, 255, 255)";
const ON_PHOTO_MUTED = "rgba(255, 255, 255, 0.9)";
/** Display and body type, as computed `font-family`. */
const SANS = '"Helvetica Neue", Helvetica, Arial, sans-serif';
/** Gap between album tiles; `--gap` in site.css. */
const GAP_PX = 4;

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

function scene(page: Page, title: string): Locator {
  const exactTitle = page.locator(".scene-title").getByText(title, { exact: true });
  return page.locator("section.scenes article.scene").filter({ has: exactTitle });
}

function sceneCover(page: Page, album: (typeof ALBUMS)[number]): Locator {
  return scene(page, album.title).locator("img");
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

type TileBox = Box & { shape: string };

/** The mosaic's box and each tile's box and `tile--<shape>`, in page order. */
function mosaicTiles(page: Page): Promise<{ grid: Box; tiles: TileBox[] }> {
  return page.locator(".mosaic").evaluate((mosaic) => {
    const toBox = (rect: DOMRect) => ({ x: rect.x, y: rect.y, width: rect.width, height: rect.height });
    const tiles = Array.from(mosaic.querySelectorAll(".tile"), (tile) => ({
      ...toBox(tile.getBoundingClientRect()),
      shape: Array.from(tile.classList).find((name) => name.startsWith("tile--"))?.slice("tile--".length) ?? "",
    }));
    return { grid: toBox(mosaic.getBoundingClientRect()), tiles };
  });
}

/**
 * How the tiles cover the mosaic: indexes of tiles outside it, pairs that overlap, and whether
 * the tiles, each grown by one gap to the right and below, add up to the mosaic grown the same way,
 * which holds only when the tiles close every row with `GAP_PX` gaps and leave no holes.
 */
function mosaicCoverage({ grid, tiles }: { grid: Box; tiles: TileBox[] }) {
  const outside = tiles.flatMap((tile, index) => (isInside(tile, grid) ? [] : [index]));
  const overlapping: [number, number][] = [];
  tiles.forEach((a, i) =>
    tiles.slice(i + 1).forEach((b, offset) => {
      const width = Math.min(a.x + a.width, b.x + b.width) - Math.max(a.x, b.x);
      const height = Math.min(a.y + a.height, b.y + b.height) - Math.max(a.y, b.y);
      if (width > 1 && height > 1) overlapping.push([i, i + 1 + offset]);
    }),
  );
  const tileArea = tiles.reduce((sum, tile) => sum + (tile.width + GAP_PX) * (tile.height + GAP_PX), 0);
  const gridArea = (grid.width + GAP_PX) * (grid.height + GAP_PX);
  return { outside, overlapping, covered: Math.abs(tileArea / gridArea - 1) < 0.001 };
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
    await expect(page.getByRole("heading", { level: 1, name: "Work", exact: true })).toHaveCount(1);
  });

  test("Work heading is visually hidden", async ({ page }) => {
    await page.goto("/work/");
    await expect(page.locator("h1.visually-hidden")).toHaveText("Work");
  });

  test("scenes show every album in order", async ({ page }) => {
    await page.goto("/work/");
    await expect(page.locator("section.scenes .scene-title")).toHaveText(ALBUMS.map((album) => album.title));
  });

  test("scenes show photo counts", async ({ page }) => {
    await page.goto("/work/");
    await expect(page.locator("section.scenes .scene-count")).toHaveText(
      ALBUMS.map((album) => `${photoCount(album.photos)} — View album →`),
    );
  });

  test("scenes are numbered out of the album total", async ({ page }) => {
    await page.goto("/work/");
    const total = String(ALBUMS.length).padStart(2, "0");
    await expect(page.locator("section.scenes .scene-number")).toHaveText(
      ALBUMS.map((_, index) => `${String(index + 1).padStart(2, "0")} / ${total}`),
    );
  });

  test("only the first scene's cover loads eagerly", async ({ page }) => {
    await page.goto("/work/");
    const loading = await page
      .locator("section.scenes .scene img")
      .evaluateAll((images) => images.map((image) => image.getAttribute("loading")));
    expect(loading).toEqual(ALBUMS.map((_, index) => (index === 0 ? null : "lazy")));
  });

  test("first scene links to the first album", async ({ page }) => {
    await page.goto("/");
    await scene(page, FIRST_ALBUM.title).locator("a").click();
    await expect(page).toHaveURL(new RegExp(`/${FIRST_ALBUM.slug}/$`));
  });

  test("scenes link to their album pages", async ({ page }) => {
    await page.goto("/");
    await scene(page, "Book II").locator("a").click();
    await expect(page).toHaveURL(/\/book-ii\/$/);
  });

  test("shows a cover image for every album", async ({ page }) => {
    await page.goto("/work/");
    for (const album of ALBUMS) {
      await expectImageLoaded(sceneCover(page, album));
    }
  });

  test("marks Work as the current page", async ({ page }) => {
    await page.goto("/work/");
    await expect(page.getByRole("link", { name: "Work", exact: true })).toHaveAttribute("aria-current", "page");
  });

  test("footer shows the site title and build year", async ({ page }) => {
    await page.goto("/work/");
    await expect(page.locator("footer.site-footer")).toContainText(footerText());
  });

  test("scenes snap into place", async ({ page }) => {
    await page.goto("/work/");
    await expect(page.locator("html")).toHaveCSS("scroll-snap-type", "y mandatory");
  });

  test("header stays fixed over the scenes", async ({ page }) => {
    await page.goto("/work/");
    await expect(page.locator(".site-header")).toHaveCSS("position", "fixed");
  });

  test("header is transparent over the scenes", async ({ page }) => {
    await page.goto("/work/");
    await expect(page.locator(".site-header")).toHaveCSS("background-color", "rgba(0, 0, 0, 0)");
  });

  test.describe("with reduced motion", () => {
    test.use({ reducedMotion: "reduce" });

    test("scenes do not snap", async ({ page }) => {
      await page.goto("/work/");
      await expect(page.locator("html")).toHaveCSS("scroll-snap-type", "none");
    });
  });

  for (const album of ALBUMS) {
    const rule = album.hasCoverFile ? "uses the cover.* file" : "uses the first photo";
    test(`${album.title} cover ${rule}`, async ({ page }) => {
      await page.goto("/work/");
      const coverSrcset = await sceneCover(page, album).getAttribute("srcset");
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

    test("first scene fills the window", async ({ page }) => {
      await page.goto("/work/");
      const box = await boxOf(page.locator(".scene").first());
      const full = await layoutWidth(page);
      expect({ x: Math.round(box.x), y: Math.round(box.y), width: Math.round(box.width), height: Math.round(box.height) }).toEqual({
        x: 0,
        y: 0,
        width: full,
        height,
      });
    });

    for (const album of [FIRST_ALBUM, LONG_TITLE_ALBUM]) {
      test(`${album.slug} scene text sits inside its scene`, async ({ page }) => {
        await page.goto("/work/");
        const frame = await boxOf(scene(page, album.title));
        const text = await boxOf(scene(page, album.title).locator(".scene-text"));
        expect(isInside(text, frame), `text ${JSON.stringify(text)} scene ${JSON.stringify(frame)}`).toBe(true);
      });
    }
  });
}

test.describe("album index on desktop", () => {
  test.skip(({ isMobile }) => isMobile, "desktop layout only");

  test.beforeEach(async ({ page }) => {
    await page.goto("/work/");
  });

  test("scene text sits at the bottom left of its scene", async ({ page }) => {
    const frame = await boxOf(scene(page, FIRST_ALBUM.title));
    const text = await boxOf(scene(page, FIRST_ALBUM.title).locator(".scene-text"));
    expect({
      nearLeft: text.x - frame.x <= 60,
      nearBottom: frame.y + frame.height - (text.y + text.height) <= 60,
    }).toEqual({ nearLeft: true, nearBottom: true });
  });

  test("scene number sits at the top right of its scene", async ({ page }) => {
    const frame = await boxOf(scene(page, FIRST_ALBUM.title));
    const number = await boxOf(scene(page, FIRST_ALBUM.title).locator(".scene-number"));
    expect({
      nearRight: frame.x + frame.width - (number.x + number.width) <= 60,
      nearTop: number.y - frame.y <= 100,
    }).toEqual({ nearRight: true, nearTop: true });
  });

  test("hovering a scene zooms its cover", async ({ page }) => {
    const target = scene(page, FIRST_ALBUM.title);
    await target.locator("a").hover();
    await expect.poll(() => imageScale(target.locator("img")), { timeout: 3_000 }).toBeCloseTo(1.03, 2);
  });

  test.describe("with reduced motion", () => {
    test.use({ reducedMotion: "reduce" });

    test("hovering a scene neither zooms nor animates its cover", async ({ page }) => {
      const target = scene(page, FIRST_ALBUM.title);
      await target.locator("a").hover();
      await expect.poll(() => target.evaluate((element) => element.matches(":hover"))).toBe(true);
      const state = await target.locator("img").evaluate((image) => ({
        transform: getComputedStyle(image).transform,
        running: image.getAnimations().length,
      }));
      expect(state).toEqual({ transform: "none", running: 0 });
    });
  });

  test("site title sits left of the navigation on one row", async ({ page }) => {
    const title = await boxOf(page.locator(".site-header .site-title"));
    const links = await page
      .locator(".site-header .site-nav a")
      .evaluateAll((elements) => elements.map((element) => element.getBoundingClientRect()));
    const navLeft = Math.min(...links.map((rect) => rect.left));
    const titleMiddle = title.y + title.height / 2;
    expect({
      titleAtLeftInset: Math.abs(title.x - 40) <= 2,
      titleLeftOfNav: title.x + title.width <= navLeft,
      sameRow: links.every((rect) => titleMiddle >= rect.top && titleMiddle <= rect.bottom),
    }).toEqual({ titleAtLeftInset: true, titleLeftOfNav: true, sameRow: true });
  });

  test("theme toggle sits at the top right, level with the title", async ({ page }) => {
    const toggle = await boxOf(themeToggle(page));
    const title = await boxOf(page.locator(".site-header .site-title"));
    const full = await layoutWidth(page);
    const toggleMiddle = toggle.y + toggle.height / 2;
    // 40px header padding less the toggle's -8px margin.
    expect({
      rightInset: Math.abs(full - (toggle.x + toggle.width) - 32) <= 4,
      levelWithTitle: toggleMiddle >= title.y && toggleMiddle <= title.y + title.height,
    }).toEqual({ rightInset: true, levelWithTitle: true });
  });
});

for (const colorScheme of ["light", "dark"] as const) {
  test.describe(`text on photos in the ${colorScheme} theme`, () => {
    test.use({ colorScheme });

    const cases = [
      { path: "/work/", selector: ".scene-title", color: OVERLAY_TEXT },
      { path: "/work/", selector: ".scene-count", color: ON_PHOTO_MUTED },
      { path: "/work/", selector: ".scene-number", color: ON_PHOTO_MUTED },
      { path: "/work/", selector: ".site-header .site-title", color: OVERLAY_TEXT },
      { path: "/work/", selector: ".site-nav a[aria-current]", color: OVERLAY_TEXT },
      { path: `/${FIRST_ALBUM.slug}/`, selector: ".album-heading", color: OVERLAY_TEXT },
      { path: `/${FIRST_ALBUM.slug}/`, selector: ".album-count", color: ON_PHOTO_MUTED },
      { path: `/${FIRST_ALBUM.slug}/`, selector: ".site-header .site-title", color: OVERLAY_TEXT },
      { path: `/${FIRST_ALBUM.slug}/`, selector: ".pager-text > span", color: OVERLAY_TEXT },
      { path: `/${FIRST_ALBUM.slug}/`, selector: ".pager-prev span", color: OVERLAY_TEXT },
    ];
    for (const { path, selector, color } of cases) {
      test(`${selector} on ${path} is readable white`, async ({ page }) => {
        await page.goto(path);
        await expect(page.locator(selector).first()).toHaveCSS("color", color);
      });
    }
  });
}

test.describe("display type", () => {
  for (const { path, selector } of [
    { path: "/work/", selector: ".scene-title" },
    { path: `/${FIRST_ALBUM.slug}/`, selector: "h1.album-heading" },
    { path: `/${FIRST_ALBUM.slug}/`, selector: ".pager-text > span" },
  ]) {
    test(`${selector} is heavy uppercase Helvetica`, async ({ page }) => {
      await page.goto(path);
      const style = await page
        .locator(selector)
        .first()
        .evaluate((element) => {
          const computed = getComputedStyle(element);
          return { family: computed.fontFamily, weight: computed.fontWeight, transform: computed.textTransform };
        });
      expect(style).toEqual({ family: SANS, weight: "900", transform: "uppercase" });
    });
  }

  test("site title is bold", async ({ page }) => {
    await page.goto("/work/");
    await expect(page.locator(".site-header .site-title")).toHaveCSS("font-weight", "700");
  });

  test("no web font is requested", async ({ page }) => {
    const fonts: string[] = [];
    page.on("request", (request) => {
      if (request.resourceType() === "font") fonts.push(request.url());
    });
    await page.goto("/work/");
    await page.evaluate(() => document.fonts.ready);
    expect(fonts).toEqual([]);
  });
});

test.describe("album index on phones", () => {
  test.skip(({ isMobile }) => !isMobile, "mobile layout only");

  test.beforeEach(async ({ page }) => {
    await page.goto("/work/");
  });

  test("scenes form a single column", async ({ page }) => {
    const lefts = await page
      .locator(".scene")
      .evaluateAll((elements) => elements.map((element) => Math.round(element.getBoundingClientRect().left)));
    expect(new Set(lefts).size).toBe(1);
  });

  test("scenes span the full screen width", async ({ page }) => {
    const widths = await page
      .locator(".scene")
      .evaluateAll((elements) => elements.map((element) => Math.round(element.getBoundingClientRect().width)));
    const full = await layoutWidth(page);
    expect(widths).toEqual(widths.map(() => full));
  });

  test("first scene fills the screen height", async ({ page }) => {
    const box = await boxOf(page.locator(".scene").first());
    const height = await page.evaluate(() => window.innerHeight);
    expect(Math.abs(box.height - height), `scene ${box.height}px, screen ${height}px`).toBeLessThanOrEqual(2);
  });

  for (const album of [FIRST_ALBUM, LONG_TITLE_ALBUM]) {
    test(`${album.slug} scene text sits inside its scene`, async ({ page }) => {
      const frame = await boxOf(scene(page, album.title));
      const text = await boxOf(scene(page, album.title).locator(".scene-text"));
      expect(isInside(text, frame), `text ${JSON.stringify(text)} scene ${JSON.stringify(frame)}`).toBe(true);
    });
  }

  test("header stays inside the 20px gutters", async ({ page }) => {
    const title = await boxOf(page.locator(".site-header .site-title"));
    const toggle = await boxOf(themeToggle(page));
    const full = await layoutWidth(page);
    // 20px header padding; the toggle's -8px margin pulls it 8px further out.
    expect({
      titleLeft: Math.abs(title.x - 20) <= 2,
      toggleRight: Math.abs(full - (toggle.x + toggle.width) - 12) <= 4,
    }).toEqual({ titleLeft: true, toggleRight: true });
  });

  test("tapping a scene opens its album", async ({ page }) => {
    await scene(page, MIDDLE_ALBUM.title).locator("a").tap();
    await expect(page).toHaveURL(new RegExp(`/${MIDDLE_ALBUM.slug}/$`));
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
    // Text pages keep the header in theme colours: the current link is --fg, other links and the footer --muted.
    await page.goto("/about/");
    const targets = [
      { selector: ".site-title", final: DARK_FG },
      { selector: ".site-nav a[aria-current]", final: DARK_FG },
      { selector: ".theme-toggle", final: DARK_FG },
      { selector: ".site-nav a:not([aria-current])", final: DARK_MUTED },
      { selector: ".site-footer", final: DARK_MUTED },
    ];
    const sample = await page.evaluate(async (selectors) => {
      const colours = () => selectors.map((selector) => getComputedStyle(document.querySelector(selector)!).color);
      document.querySelector<HTMLButtonElement>(".site-nav button.theme-toggle")!.click();
      // The fade lasts 1500 ms and the class is removed at 1600 ms; sample in between.
      await new Promise((resolve) => setTimeout(resolve, 1_520));
      const atEnd = colours();
      const fading = document.documentElement.classList.contains("theme-transition");
      return { fading, atEnd };
    }, targets.map((target) => target.selector));
    // Red, green, blue, and alpha scaled to 0-255, so one tolerance fits every channel.
    const channels = (colour: string) => {
      const match = /^rgba?\((\d+), (\d+), (\d+)(?:, ([\d.]+))?\)$/.exec(colour);
      return match ? [...match.slice(1, 4).map(Number), Number(match[4] ?? 1) * 255] : [];
    };
    const farthest = Math.max(
      ...sample.atEnd.flatMap((colour, index) => {
        const actual = channels(colour);
        const expected = channels(targets[index].final);
        return actual.length === 4 ? actual.map((value, channel) => Math.abs(value - expected[channel])) : [Infinity];
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
    await page.goto(`/${MIDDLE_ALBUM.slug}/`);
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

  test("Previous sits in the top left corner of the Next banner", async ({ page }) => {
    await page.goto(`/${MIDDLE_ALBUM.slug}/`);
    const previous = await boxOf(page.locator(".album-pager a.pager-prev"));
    const next = await boxOf(page.locator(".album-pager a.pager-next"));
    expect({
      inside: isInside(previous, next),
      nearLeft: previous.x - next.x <= 48,
      nearTop: previous.y - next.y <= 32,
    }).toEqual({ inside: true, nearLeft: true, nearTop: true });
  });

  test("Next banner shows the next album's cover", async ({ page }) => {
    await page.goto("/work/");
    const nextCover = await sceneCover(page, ALBUMS[1]).getAttribute("srcset");
    await page.goto(`/${FIRST_ALBUM.slug}/`);
    const banner = page.locator(".album-pager a.pager-next img");
    await expectImageLoaded(banner);
    expect(await banner.getAttribute("srcset")).toBe(nextCover);
  });

  test("Next banner spans the full window width", async ({ page }) => {
    await page.goto(`/${FIRST_ALBUM.slug}/`);
    const banner = await boxOf(page.locator(".album-pager a.pager-next"));
    const full = await layoutWidth(page);
    expect({ left: Math.round(banner.x), width: Math.round(banner.width) }).toEqual({ left: 0, width: full });
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

  test("hero shows the album cover", async ({ page }) => {
    await page.goto("/work/");
    const cover = await sceneCover(page, FIRST_ALBUM).getAttribute("srcset");
    await page.goto(`/${FIRST_ALBUM.slug}/`);
    const hero = page.locator("section.album-hero img");
    await expectImageLoaded(hero);
    expect(await hero.getAttribute("srcset")).toBe(cover);
  });

  test("hero comes before the photos", async ({ page }) => {
    await page.goto(`/${LANDSCAPES.slug}/`);
    const hero = await boxOf(page.locator("section.album-hero"));
    const firstTile = await boxOf(page.locator(".tile").first());
    expect(hero.y + hero.height).toBeLessThanOrEqual(firstTile.y + 1);
  });

  test("hero is 88% of the window height", async ({ page }) => {
    await page.goto(`/${LANDSCAPES.slug}/`);
    const hero = await boxOf(page.locator("section.album-hero"));
    const height = await page.evaluate(() => window.innerHeight);
    expect(Math.abs(hero.height - 0.88 * height), `hero ${hero.height}px, window ${height}px`).toBeLessThanOrEqual(2);
  });

  for (const album of [LANDSCAPES, LONG_TITLE_ALBUM]) {
    test(`${album.slug} heading and count sit inside the hero`, async ({ page }) => {
      await page.goto(`/${album.slug}/`);
      const hero = await boxOf(page.locator("section.album-hero"));
      const heading = await boxOf(page.locator("h1.album-heading"));
      const count = await boxOf(page.locator(".album-count"));
      expect([isInside(heading, hero), isInside(count, hero)]).toEqual([true, true]);
    });
  }

  test("hero text sits at the bottom left of the hero", async ({ page }) => {
    await page.goto(`/${LANDSCAPES.slug}/`);
    const hero = await boxOf(page.locator("section.album-hero"));
    const text = await boxOf(page.locator(".album-hero-text"));
    expect({
      nearLeft: text.x - hero.x <= 48,
      nearBottom: hero.y + hero.height - (text.y + text.height) <= 56,
    }).toEqual({ nearLeft: true, nearBottom: true });
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

function heroLink(page: Page, album: (typeof ALBUMS)[number]): Locator {
  return page.getByRole("link", { name: `Open cover photo of ${album.title}`, exact: true });
}

test.describe("album hero cover link", () => {
  /** FIRST_ALBUM has a separate cover.* file, so the viewer shows it before the photos. */
  const coverFileTotal = FIRST_ALBUM.photos + 1;

  test("clicking the hero opens the viewer on the cover file", async ({ page }) => {
    await page.goto(`/${FIRST_ALBUM.slug}/`);
    await heroLink(page, FIRST_ALBUM).click();
    await expect(lightboxCounter(page)).toHaveText(counter(1, coverFileTotal));
  });

  test("with a cover file, a tile opens one past its position", async ({ page }) => {
    await page.goto(`/${FIRST_ALBUM.slug}/`);
    await photoLinks(page).first().click();
    await expect(lightboxCounter(page)).toHaveText(counter(2, coverFileTotal));
  });

  for (const selector of ["h1.album-heading", ".album-hero .album-count"]) {
    test(`clicking ${selector} does not open the viewer`, async ({ page }) => {
      await page.goto(`/${FIRST_ALBUM.slug}/`);
      const box = await boxOf(page.locator(selector));
      await page.mouse.click(box.x + box.width - 2, box.y + box.height / 2);
      await page.waitForTimeout(300);
      await expect(lightbox(page)).toBeHidden();
    });
  }

  test("clicking the empty end of the caption strip opens the viewer on the cover", async ({ page }) => {
    await page.goto(`/${FIRST_ALBUM.slug}/`);
    const caption = await boxOf(page.locator(".album-hero-text"));
    await page.mouse.click(caption.x + caption.width - 2, caption.y + caption.height / 2);
    await expect(lightboxCounter(page)).toHaveText(counter(1, coverFileTotal));
  });

  test("clicking the cover above the caption opens the viewer on the cover", async ({ page }) => {
    await page.goto(`/${FIRST_ALBUM.slug}/`);
    const caption = await boxOf(page.locator(".album-hero-text"));
    await page.mouse.click(caption.x + caption.width / 2, caption.y - 20);
    await expect(lightboxCounter(page)).toHaveText(counter(1, coverFileTotal));
  });

  test("closing after opening from the hero returns focus to the hero", async ({ page }) => {
    await page.goto(`/${FIRST_ALBUM.slug}/`);
    await heroLink(page, FIRST_ALBUM).click();
    await expect(lightboxCounter(page)).toHaveText(counter(1, coverFileTotal));
    await page.keyboard.press("Escape");
    await expect(heroLink(page, FIRST_ALBUM)).toBeFocused();
  });

  test("without a cover file, the hero opens the first photo once", async ({ page }) => {
    await page.goto(`/${LANDSCAPES.slug}/`);
    await heroLink(page, LANDSCAPES).click();
    await expect(lightboxCounter(page)).toHaveText(counter(1));
  });

  test("without a cover file, closing after opening from the hero focuses the first tile", async ({ page }) => {
    await page.goto(`/${LANDSCAPES.slug}/`);
    await heroLink(page, LANDSCAPES).click();
    await expect(lightboxCounter(page)).toHaveText(counter(1));
    await page.keyboard.press("Escape");
    await expect(photoLinks(page).first()).toBeFocused();
  });

  test("without a cover file, the hero shows the first tile's image", async ({ page }) => {
    await page.goto(`/${LANDSCAPES.slug}/`);
    const href = await photoLinks(page).first().evaluate((link: HTMLAnchorElement) => link.href);
    await heroLink(page, LANDSCAPES).click();
    await expect.poll(() => lightboxImageSrc(page)).toBe(href);
  });

  test("without a cover file, Next from the hero shows the second photo", async ({ page }) => {
    await page.goto(`/${LANDSCAPES.slug}/`);
    const href = await photoLinks(page).nth(1).evaluate((link: HTMLAnchorElement) => link.href);
    await heroLink(page, LANDSCAPES).click();
    await expect(lightboxCounter(page)).toHaveText(counter(1));
    await lightbox(page).getByRole("button", { name: "Next photo", exact: true }).click();
    await expect.poll(() => lightboxImageSrc(page)).toBe(href);
  });

  test("album and index scene titles are 5vw, 9vw on phones", async ({ page }) => {
    const fontSize = (locator: Locator) =>
      locator.evaluate((element) => parseFloat(getComputedStyle(element).fontSize));
    const width = page.viewportSize()!.width;
    const expected = width * (width <= 767 ? 0.09 : 0.05);
    await page.goto("/work/");
    expect(await fontSize(page.locator(".scene-title").first())).toBeCloseTo(expected, 0);
    await page.goto(`/${FIRST_ALBUM.slug}/`);
    expect(await fontSize(page.locator("h1.album-heading"))).toBeCloseTo(expected, 0);
  });
});

test.describe("single-photo album", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(`/${SINGLE_PHOTO_ALBUM.slug}/`);
  });

  test("its only tile is a full tile, four columns wide and two rows tall on desktop", async ({ page, isMobile }) => {
    test.skip(isMobile, "phones show every tile as a square");
    const { grid, tiles } = await mosaicTiles(page);
    const twoRows = 2 * ((grid.width - 3 * GAP_PX) / 4) + GAP_PX;
    expect(tiles.map((tile) => [Math.round(tile.width), Math.round(tile.height)])).toEqual([
      [Math.round(grid.width), Math.round(twoRows)],
    ]);
  });

  test("its only tile is full width on phones", async ({ page, isMobile }) => {
    test.skip(!isMobile, "desktop shows a two-row full tile");
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

/** Mosaic grids wide enough for more than one column: 4 above 1024px, 2 from 768 to 1024px. */
const MOSAIC_GRIDS = [
  { name: "desktop", viewport: { width: 1440, height: 900 }, columns: 4 },
  { name: "tablet", viewport: { width: 1024, height: 768 }, columns: 2 },
];

for (const { name, viewport, columns } of MOSAIC_GRIDS) {
  test.describe(`album mosaic on a ${name} at ${viewport.width}px`, () => {
    test.skip(({ isMobile }) => isMobile, "a desktop window");
    test.use({ viewport });

    test(`mosaic has ${columns} columns`, async ({ page }) => {
      await page.goto(`/${LANDSCAPES.slug}/`);
      const tracks = await page
        .locator(".mosaic")
        .evaluate((mosaic) => getComputedStyle(mosaic).gridTemplateColumns.split(" ").length);
      expect(tracks).toBe(columns);
    });

    for (const album of ALBUMS) {
      test(`${album.slug} tiles cover the mosaic with no holes`, async ({ page }) => {
        await page.goto(`/${album.slug}/`);
        expect(mosaicCoverage(await mosaicTiles(page))).toEqual({ outside: [], overlapping: [], covered: true });
      });
    }

    test("big tiles are square", async ({ page }) => {
      await page.goto(`/${LANDSCAPES.slug}/`);
      const big = (await mosaicTiles(page)).tiles.filter((tile) => tile.shape === "big");
      expect(big.length).toBeGreaterThan(0);
      expect(big.map((tile) => Math.abs(tile.width - tile.height) <= 1)).toEqual(big.map(() => true));
    });
  });
}

test.describe("album mosaic", () => {
  test("tile photos fill their tile, cropped rather than stretched", async ({ page }) => {
    await page.goto(`/${LANDSCAPES.slug}/`);
    const fits = await page.locator(".tile img").evaluateAll((images: HTMLImageElement[]) =>
      images.map((image) => {
        const tile = image.closest<HTMLElement>(".tile")!;
        return (
          getComputedStyle(image).objectFit === "cover" &&
          Math.abs(image.clientWidth - tile.clientWidth) <= 1 &&
          Math.abs(image.clientHeight - tile.clientHeight) <= 1
        );
      }),
    );
    expect(fits).toEqual(fits.map(() => true));
  });
});

test.describe("desktop", () => {
  test.skip(({ isMobile }) => isMobile, "desktop layout only");

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

  test("album tiles are square", async ({ page }) => {
    await page.goto(`/${LANDSCAPES.slug}/`);
    const { tiles } = await mosaicTiles(page);
    expect(tiles.map((tile) => Math.abs(tile.width - tile.height) <= 1)).toEqual(tiles.map(() => true));
  });
});
