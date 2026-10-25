import { expect, test, type Locator, type Page } from "@playwright/test";

const ALBUMS = [
  { title: "Book I", slug: "book-i", photos: 3, hasCoverFile: true },
  { title: "Book II", slug: "book-ii", photos: 2, hasCoverFile: false },
  { title: "Portraits", slug: "portraits", photos: 4, hasCoverFile: false },
  { title: "Landscapes", slug: "landscapes", photos: 11, hasCoverFile: false },
  { title: "Still Life", slug: "still-life", photos: 1, hasCoverFile: false },
];
const FIRST_ALBUM = ALBUMS[0];
const LAST_ALBUM = ALBUMS[ALBUMS.length - 1];
/** Both mosaic groups plus a remainder of three; the album the lightbox and layout tests browse. */
const LANDSCAPES = ALBUMS[3];
const SINGLE_PHOTO_ALBUM = LAST_ALBUM;

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

function tile(page: Page, title: string): Locator {
  const exactTitle = page.locator(".album-title").getByText(title, { exact: true });
  return page.locator(".album-tile").filter({ has: exactTitle });
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
  test("lists every album in order", async ({ page }) => {
    await page.goto("/work/");
    await expect(page.locator(".album-title")).toHaveText(ALBUMS.map((album) => album.title));
  });

  test("shows a cover image for every album", async ({ page }) => {
    await page.goto("/work/");
    for (const album of ALBUMS) {
      await expectImageLoaded(tile(page, album.title).locator("img"));
    }
  });

  test("covers link to their album pages", async ({ page }) => {
    await page.goto("/");
    await tile(page, "Book II").locator("a").click();
    await expect(page).toHaveURL(/\/book-ii\/$/);
  });

  test("marks Work as the current page", async ({ page }) => {
    await page.goto("/work/");
    await expect(page.getByRole("link", { name: "Work" })).toHaveAttribute("aria-current", "page");
  });

  for (const album of ALBUMS) {
    const rule = album.hasCoverFile ? "uses the cover.* file" : "uses the first photo";
    test(`${album.title} cover ${rule}`, async ({ page }) => {
      await page.goto("/work/");
      const coverSrcset = await tile(page, album.title).locator("img").getAttribute("srcset");
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
    await page.goto("/book-i/");
    await page.locator(".next-album a").click();
    await expect(page).toHaveURL(/\/book-ii\/$/);
  });

  test("Next on the last album wraps to the first", async ({ page }) => {
    await page.goto(`/${LAST_ALBUM.slug}/`);
    await expect(page.locator(".next-album a")).toHaveText(FIRST_ALBUM.title);
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

  test("heading is uppercased", async ({ page }) => {
    await page.goto("/portraits/");
    await expect(page.locator("h1.album-heading")).toHaveCSS("text-transform", "uppercase");
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

  test("its only tile is full size", async ({ page }) => {
    await expect(page.locator(".tile")).toHaveClass(/\btile--full\b/);
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

test("every page loads without errors or missing files", async ({ page }) => {
  const failures = trackFailures(page);
  for (const path of ["/", "/work/", ...ALBUMS.map((album) => `/${album.slug}/`)]) {
    await page.goto(path);
    for (const image of await page.locator("main img:not(.lightbox-image)").all()) {
      await expectImageLoaded(image);
    }
  }
  expect(failures).toEqual([]);
});

test.describe("desktop", () => {
  test.skip(({ isMobile }) => isMobile, "desktop layout only");

  test("mouse wheel scrolls the album index sideways", async ({ page }) => {
    await page.goto("/work/");
    const strip = page.locator(".album-strip");
    await strip.hover();
    await page.mouse.wheel(0, 600);
    await expect.poll(() => strip.evaluate((element) => element.scrollLeft)).toBeGreaterThan(0);
  });

  test("hovering a cover reveals the album title", async ({ page }) => {
    await page.goto("/work/");
    const title = tile(page, "Book I").locator(".album-title");
    await expect(title).toHaveCSS("opacity", "0");
    await tile(page, "Book I").locator("img").hover();
    await expect(title).toHaveCSS("opacity", "1");
  });

  test("album mosaic has four columns", async ({ page }) => {
    await page.goto(`/${LANDSCAPES.slug}/`);
    const columns = await page
      .locator(".mosaic")
      .evaluate((mosaic) => getComputedStyle(mosaic).gridTemplateColumns.split(" ").length);
    expect(columns).toBe(4);
  });

  test("big tile is about twice as wide as a small tile", async ({ page }) => {
    await page.goto(`/${LANDSCAPES.slug}/`);
    const big = await boxOf(page.locator(".tile--big").first());
    const small = await boxOf(page.locator(".tile--small").first());
    const ratio = big.width / small.width;
    expect(ratio).toBeGreaterThan(1.9);
    expect(ratio).toBeLessThan(2.15);
  });

  test("small tiles are square", async ({ page }) => {
    await page.goto(`/${LANDSCAPES.slug}/`);
    const small = await boxOf(page.locator(".tile--small").first());
    expect(Math.abs(small.width - small.height)).toBeLessThanOrEqual(1);
  });

  for (const album of ALBUMS) {
    test(`${album.title} tiles fill a rectangle without holes`, async ({ page }) => {
      await page.goto(`/${album.slug}/`);
      const coverage = await page.locator(".mosaic").evaluate((mosaic) => {
        const style = getComputedStyle(mosaic);
        const halfColumnGap = (Number.parseFloat(style.columnGap) || 0) / 2;
        const halfRowGap = (Number.parseFloat(style.rowGap) || 0) / 2;
        const rects = Array.from(mosaic.querySelectorAll(".tile"), (element) =>
          element.getBoundingClientRect(),
        );
        const left = Math.min(...rects.map((rect) => rect.left)) - halfColumnGap;
        const right = Math.max(...rects.map((rect) => rect.right)) + halfColumnGap;
        const top = Math.min(...rects.map((rect) => rect.top)) - halfRowGap;
        const bottom = Math.max(...rects.map((rect) => rect.bottom)) + halfRowGap;
        const tileArea = rects.reduce(
          (sum, rect) => sum + (rect.width + 2 * halfColumnGap) * (rect.height + 2 * halfRowGap),
          0,
        );
        return tileArea / ((right - left) * (bottom - top));
      });
      expect(coverage).toBeCloseTo(1, 2);
    });
  }

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

  test("album index is a two-column grid", async ({ page }) => {
    await page.goto("/work/");
    const [first, second] = await page.locator(".album-tile").all();
    const [a, b] = [await first.boundingBox(), await second.boundingBox()];
    expect(a).not.toBeNull();
    expect(b).not.toBeNull();
    expect(b!.y).toBe(a!.y);
    expect(b!.x).toBeGreaterThan(a!.x);
  });

  test("album titles are always visible", async ({ page }) => {
    await page.goto("/work/");
    await expect(tile(page, "Book I").locator(".album-title")).toHaveCSS("opacity", "1");
  });

  test("page has no horizontal overflow", async ({ page }) => {
    await page.goto("/work/");
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(0);
  });

  test("album page has no horizontal overflow", async ({ page }) => {
    await page.goto(`/${LANDSCAPES.slug}/`);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(0);
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
