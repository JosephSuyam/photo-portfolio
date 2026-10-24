import { expect, test, type Locator, type Page } from "@playwright/test";

const ALBUMS = [
  { title: "Book I", slug: "book-i", photos: 3, hasCoverFile: true },
  { title: "Book II", slug: "book-ii", photos: 2, hasCoverFile: false },
  { title: "Portraits", slug: "portraits", photos: 4, hasCoverFile: false },
];

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
      const firstPhotoSrcset = await page.locator(".photo img").first().getAttribute("srcset");
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
      const photos = page.locator(".photo img");
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
    await page.goto("/portraits/");
    await expect(page.locator(".next-album a")).toHaveText("Book I");
  });

  test("has the album title in the page title", async ({ page }) => {
    await page.goto("/portraits/");
    await expect(page).toHaveTitle("Portraits | Reel E2E");
  });
});

test("every page loads without errors or missing files", async ({ page }) => {
  const failures = trackFailures(page);
  for (const path of ["/", "/work/", ...ALBUMS.map((album) => `/${album.slug}/`)]) {
    await page.goto(path);
    for (const image of await page.locator("main img").all()) {
      await expectImageLoaded(image);
    }
  }
  expect(failures).toEqual([]);
});

test.describe("desktop", () => {
  test.skip(({ isMobile }) => isMobile, "desktop layout only");

  test("mouse wheel scrolls the album strip sideways", async ({ page }) => {
    await page.goto("/portraits/");
    const strip = page.locator(".photo-strip");
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
});
