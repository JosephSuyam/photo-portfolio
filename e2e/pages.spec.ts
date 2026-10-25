import { expect, test, type Locator, type Page } from "@playwright/test";

/** Must match ABOUT_TEXT, CONTACT_TEXT, and CONTACT_FORM_URL in e2e/serve_fixture.py. */
const ABOUT_LEDE = "I photograph quiet places at the edges of cities, mostly at dusk.";
const ABOUT_PARAGRAPHS = [
  "Most of this work is made on medium-format film and printed by hand in a small darkroom.",
  "Prints and commissions are available on request.",
];
const EMAIL = "studio@example.test";
const FACTS = [
  {
    label: "Instagram",
    text: "instagram.example.test/reel-e2e",
    href: "https://instagram.example.test/reel-e2e/",
  },
  { label: "Based in", text: "Lisbon, Portugal", href: null },
];
const FORM_URL = "https://forms.example.test/f/reel-e2e";
const SITE_TITLE = "Reel E2E";
const NAV_LINKS = ["Work", "About", "Contact"];
const DARK_BACKGROUND = "rgb(15, 15, 15)";
/** A title long enough that it and the nav cannot share one row on a phone. */
const LONG_SITE_TITLE = "Reel E2E Fine Art Photography";
/** A title too long for one phone line; it must wrap on its own row instead of overflowing. */
const VERY_LONG_SITE_TITLE = "Reel E2E Fine Art, Documentary and Editorial Photography Co.";

const PAGES = [
  { name: "home", path: "/", current: "Work" },
  { name: "album index", path: "/work/", current: "Work" },
  { name: "album page", path: "/book-i/", current: null },
  { name: "about", path: "/about/", current: "About" },
  { name: "contact", path: "/contact/", current: "Contact" },
];

function navLinks(page: Page): Locator {
  return page.locator(".site-header .site-nav a");
}

function formField(page: Page, name: string): Locator {
  return page.getByRole("textbox", { name, exact: true });
}

function honeypot(page: Page): Locator {
  return page.locator('form.contact-form input[name="_gotcha"]');
}

function themeToggle(page: Page): Locator {
  return page.locator(".site-nav button.theme-toggle");
}

function horizontalOverflow(page: Page): Promise<number> {
  return page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
}

async function boxOf(locator: Locator): Promise<{ x: number; y: number; width: number; height: number }> {
  const box = await locator.boundingBox();
  expect(box).not.toBeNull();
  return box!;
}

/** Distinct line boxes the element's text is laid out on. */
function lineCount(locator: Locator): Promise<number> {
  return locator.evaluate((element) => {
    const range = document.createRange();
    range.selectNodeContents(element);
    return new Set([...range.getClientRects()].map((rect) => Math.round(rect.top))).size;
  });
}

function trackFailures(page: Page): string[] {
  const failures: string[] = [];
  page.on("pageerror", (error) => failures.push(`page error: ${error.message}`));
  page.on("console", (message) => {
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

// Nothing in these tests may reach the network; only the fixture server on localhost answers.
test.beforeEach(async ({ context }) => {
  await context.route(
    (url) => url.hostname !== "localhost",
    (route) => route.abort(),
  );
});

test.describe("site navigation", () => {
  for (const { name, path, current } of PAGES) {
    test(`${name} nav lists Work, About, Contact`, async ({ page }) => {
      await page.goto(path);
      await expect(navLinks(page)).toHaveText(NAV_LINKS);
    });

    test(`${name} nav marks ${current ?? "no link"} as current`, async ({ page }) => {
      await page.goto(path);
      await expect(page.locator('.site-nav a[aria-current="page"]')).toHaveText(current ? [current] : []);
    });
  }

  test("About link opens the about page", async ({ page }) => {
    await page.goto("/work/");
    await page.locator(".site-nav").getByRole("link", { name: "About", exact: true }).click();
    await expect(page).toHaveURL(/\/about\/$/);
  });

  test("Contact link opens the contact page", async ({ page }) => {
    await page.goto("/about/");
    await page.locator(".site-nav").getByRole("link", { name: "Contact", exact: true }).click();
    await expect(page).toHaveURL(/\/contact\/$/);
  });

  for (const path of ["/about/", "/contact/"]) {
    test(`${path} loads without errors`, async ({ page }) => {
      const failures = trackFailures(page);
      await page.goto(path);
      await page.waitForLoadState("load");
      expect(failures).toEqual([]);
    });
  }
});

test.describe("about page", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/about/");
  });

  test("document title names the page and site", async ({ page }) => {
    await expect(page).toHaveTitle(`About | ${SITE_TITLE}`);
  });

  test("heading is About", async ({ page }) => {
    await expect(page.locator("h1.page-heading")).toHaveText("About");
  });

  test("lede is the first paragraph", async ({ page }) => {
    await expect(page.locator(".text-column .lede")).toHaveText(ABOUT_LEDE);
  });

  test("prose lists the other paragraphs", async ({ page }) => {
    await expect(page.locator(".text-column .prose p")).toHaveText(ABOUT_PARAGRAPHS);
  });

  test("has no meta line", async ({ page }) => {
    await expect(page.locator(".page-meta")).toHaveCount(0);
  });

  test("signoff link opens the contact page", async ({ page }) => {
    await page.locator(".signoff").getByRole("link", { name: "Contact", exact: true }).click();
    await expect(page).toHaveURL(/\/contact\/$/);
  });
});

test.describe("contact page", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/contact/");
  });

  test("document title names the page and site", async ({ page }) => {
    await expect(page).toHaveTitle(`Contact | ${SITE_TITLE}`);
  });

  test("heading is Contact", async ({ page }) => {
    await expect(page.locator("h1.page-heading")).toHaveText("Contact");
  });

  test("big email shows the address", async ({ page }) => {
    await expect(page.locator("a.contact-email")).toHaveText(EMAIL);
  });

  test("big email is a mailto link", async ({ page }) => {
    await expect(page.locator("a.contact-email")).toHaveAttribute("href", `mailto:${EMAIL}`);
  });

  test("facts row shows each label", async ({ page }) => {
    await expect(page.locator(".contact-facts li .label")).toHaveText(FACTS.map((fact) => fact.label));
  });

  test("facts row shows each value", async ({ page }) => {
    await expect(page.locator(".contact-facts li .contact-value")).toHaveText(FACTS.map((fact) => fact.text));
  });

  test("facts row links only URL values", async ({ page }) => {
    const hrefs = await page
      .locator(".contact-facts li .contact-value")
      .evaluateAll((values) => values.map((value) => value.querySelector("a")?.getAttribute("href") ?? null));
    expect(hrefs).toEqual(FACTS.map((fact) => fact.href));
  });

  test("has no meta line", async ({ page }) => {
    await expect(page.locator(".page-meta")).toHaveCount(0);
  });

  test("form section is labelled Send a message", async ({ page }) => {
    await expect(page.getByRole("region", { name: "Send a message", exact: true })).toBeVisible();
  });

  for (const name of ["Name", "Email", "Message"]) {
    test(`${name} field is visible and required`, async ({ page }) => {
      const field = formField(page, name);
      await expect(field).toBeVisible();
      await expect(field).toHaveJSProperty("required", true);
    });
  }

  test("honeypot field is in the form", async ({ page }) => {
    await expect(honeypot(page)).toHaveCount(1);
  });

  test("form exposes exactly the three visible textboxes", async ({ page }) => {
    await expect(page.locator("form.contact-form").getByRole("textbox")).toHaveCount(3);
  });

  test("honeypot field sits inside the aria-hidden trap", async ({ page }) => {
    await expect(
      page.locator('form.contact-form .form-trap[aria-hidden="true"] input[name="_gotcha"]'),
    ).toHaveCount(1);
  });

  test("honeypot field is off-screen", async ({ page }) => {
    const box = await boxOf(honeypot(page));
    expect(box.x + box.width).toBeLessThanOrEqual(0);
  });

  test("honeypot trap is not display none", async ({ page }) => {
    await expect(page.locator(".form-trap")).not.toHaveCSS("display", "none");
  });

  test("submitting posts name, email, and message to the form service", async ({ page }) => {
    const posted: { method: string; fields: Record<string, string> }[] = [];
    await page.route(`${FORM_URL}**`, async (route) => {
      const request = route.request();
      posted.push({
        method: request.method(),
        fields: Object.fromEntries(new URLSearchParams(request.postData() ?? "")),
      });
      await route.fulfill({ status: 200, contentType: "text/html", body: "<!doctype html><p>Thanks</p>" });
    });
    await formField(page, "Name").fill("Ada Lovelace");
    await formField(page, "Email").fill("ada@example.test");
    await formField(page, "Message").fill("Do you sell prints?");
    await page.getByRole("button", { name: "Send message", exact: true }).click();
    await expect.poll(() => posted.length).toBe(1);
    expect(posted[0]).toEqual({
      method: "POST",
      fields: { name: "Ada Lovelace", email: "ada@example.test", message: "Do you sell prints?", _gotcha: "" },
    });
  });

  test("empty form is invalid", async ({ page }) => {
    const valid = await page.locator("form.contact-form").evaluate((form: HTMLFormElement) => form.checkValidity());
    expect(valid).toBe(false);
  });

  test("clicking Send message on an empty form posts nothing", async ({ page }) => {
    const posted: Record<string, string>[] = [];
    await page.route(`${FORM_URL}**`, async (route) => {
      posted.push(Object.fromEntries(new URLSearchParams(route.request().postData() ?? "")));
      await route.fulfill({ status: 200, contentType: "text/html", body: "<!doctype html><p>Thanks</p>" });
    });
    const send = page.getByRole("button", { name: "Send message", exact: true });
    await send.click();
    await expect(page).toHaveURL(/\/contact\/$/);
    // A later valid submission is the sync point: had the empty one gone out, it would be first.
    await formField(page, "Name").fill("Ada Lovelace");
    await formField(page, "Email").fill("ada@example.test");
    await formField(page, "Message").fill("Hello");
    await send.click();
    await expect.poll(() => posted.length).toBe(1);
    expect(posted[0].name).toBe("Ada Lovelace");
  });
});

for (const path of ["/about/", "/contact/"]) {
  test(`${path} has no horizontal overflow`, async ({ page }) => {
    await page.goto(path);
    expect(await horizontalOverflow(page)).toBeLessThanOrEqual(0);
  });
}

test.describe("text pages on phones", () => {
  test.skip(({ isMobile }) => !isMobile, "mobile layout only");

  for (const path of ["/about/", "/contact/"]) {
    test.describe(path, () => {
      test.beforeEach(async ({ page }) => {
        await page.goto(path);
        await page.locator(".site-header .site-title").evaluate((title, text) => {
          title.textContent = text;
        }, LONG_SITE_TITLE);
      });

      test("a long site title stays on one line", async ({ page }) => {
        expect(await lineCount(page.locator(".site-header .site-title"))).toBe(1);
      });

      test("the nav wraps below a long site title", async ({ page }) => {
        const title = await boxOf(page.locator(".site-header .site-title"));
        const nav = await boxOf(page.locator(".site-header .site-nav"));
        expect(nav.y).toBeGreaterThanOrEqual(title.y + title.height - 1);
      });

      test("a long site title causes no horizontal overflow", async ({ page }) => {
        expect(await horizontalOverflow(page)).toBeLessThanOrEqual(0);
      });
    });

    test.describe(`${path} with a title too long for one line`, () => {
      test.beforeEach(async ({ page }) => {
        await page.goto(path);
        await page.locator(".site-header .site-title").evaluate((title, text) => {
          title.textContent = text;
        }, VERY_LONG_SITE_TITLE);
      });

      test("page has no horizontal overflow", async ({ page }) => {
        expect(await horizontalOverflow(page)).toBeLessThanOrEqual(0);
      });

      test("the nav sits below the title", async ({ page }) => {
        const title = await boxOf(page.locator(".site-header .site-title"));
        const nav = await boxOf(page.locator(".site-header .site-nav"));
        expect(nav.y).toBeGreaterThanOrEqual(title.y + title.height - 1);
      });

      test("the title stays within the viewport", async ({ page }) => {
        const title = await boxOf(page.locator(".site-header .site-title"));
        const viewportWidth = page.viewportSize()?.width ?? 0;
        expect([title.x >= 0, title.x + title.width <= viewportWidth + 0.5]).toEqual([true, true]);
      });
    });
  }
});

/** Desktop windows tall enough that each text page's content is shorter than the viewport. */
const SHORT_PAGE_VIEWPORTS = [
  { path: "/about/", viewport: { width: 1440, height: 900 } },
  { path: "/contact/", viewport: { width: 1440, height: 1600 } },
];

for (const { path, viewport } of SHORT_PAGE_VIEWPORTS) {
  test.describe(`${path} in a ${viewport.width}x${viewport.height} desktop window`, () => {
    test.skip(({ isMobile }) => isMobile, "desktop layout only");
    test.use({ viewport });

    test.beforeEach(async ({ page }) => {
      await page.goto(path);
    });

    test("content is shorter than the viewport", async ({ page }) => {
      const contentHeight = await page.evaluate(() => {
        const lastBlock = document.querySelector("main")!.lastElementChild!;
        const footer = document.querySelector("footer.site-footer")!;
        return lastBlock.getBoundingClientRect().bottom + window.scrollY + footer.getBoundingClientRect().height;
      });
      expect(contentHeight).toBeLessThan(viewport.height);
    });

    test("footer bottom is at the viewport bottom", async ({ page }) => {
      const footer = await boxOf(page.locator("footer.site-footer"));
      expect(Math.abs(footer.y + footer.height - viewport.height)).toBeLessThanOrEqual(1);
    });
  });
}

test.describe("theme toggle on text pages", () => {
  test.use({ colorScheme: "light" });

  for (const path of ["/about/", "/contact/"]) {
    test(`${path} toggle switches to dark`, async ({ page }) => {
      await page.goto(path);
      await themeToggle(page).click();
      await expect(page.locator("body")).toHaveCSS("background-color", DARK_BACKGROUND);
    });
  }

  test("a theme chosen on the about page applies on the contact page", async ({ page }) => {
    await page.goto("/about/");
    await themeToggle(page).click();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
    await page.goto("/contact/");
    await expect(page.locator("body")).toHaveCSS("background-color", DARK_BACKGROUND);
  });
});
