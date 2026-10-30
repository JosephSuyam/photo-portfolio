// Open album photos in a full-screen viewer instead of navigating to the image file.

// A block keeps these names out of the global scope shared with the other site scripts.
{
  const SWIPE_MIN_PX = 50;

  const hasModifier = (event: MouseEvent | KeyboardEvent): boolean =>
    event.ctrlKey || event.metaKey || event.shiftKey || event.altKey;

  const setUpLightbox = (dialog: HTMLDialogElement): void => {
    const openers = Array.from(document.querySelectorAll<HTMLAnchorElement>("a[data-lightbox]"));
    // The cover is left out when a tile shows the same photo; clicking it opens that tile's photo.
    const links = openers.filter(
      (link) =>
        !link.matches(".album-hero-link") ||
        !openers.some((other) => other !== link && other.href === link.href),
    );
    const image = dialog.querySelector<HTMLImageElement>(".lightbox-image");
    const counter = dialog.querySelector<HTMLElement>(".lightbox-counter");
    const closeButton = dialog.querySelector<HTMLButtonElement>(".lightbox-close");
    const previousButton = dialog.querySelector<HTMLButtonElement>(".lightbox-prev");
    const nextButton = dialog.querySelector<HTMLButtonElement>(".lightbox-next");
    if (!image || !counter || !closeButton || !previousButton || !nextButton || links.length === 0) {
      return;
    }
    let current = 0;
    let touchStart: { x: number; y: number } | null = null;

    previousButton.hidden = links.length < 2;
    nextButton.hidden = links.length < 2;

    // Hide the previous photo until the next one has loaded, so it never sits under a new counter.
    const markLoaded = (): void => image.classList.remove("is-loading");
    image.addEventListener("load", markLoaded);
    image.addEventListener("error", markLoaded);

    const show = (index: number): void => {
      current = (index + links.length) % links.length;
      image.classList.add("is-loading");
      image.src = links[current].href;
      image.alt = `Photo ${current + 1} of ${links.length}`;
      counter.textContent = `${current + 1} / ${links.length}`;
      if (image.complete) markLoaded();
    };

    openers.forEach((opener) => {
      opener.addEventListener("click", (event: MouseEvent) => {
        // Modified clicks open the viewer too, so they cannot open the raw image in a new tab.
        if (event.button !== 0) return;
        event.preventDefault();
        const index = links.indexOf(opener);
        show(index >= 0 ? index : links.findIndex((link) => link.href === opener.href));
        dialog.showModal();
      });
    });

    previousButton.addEventListener("click", () => show(current - 1));
    nextButton.addEventListener("click", () => show(current + 1));
    closeButton.addEventListener("click", () => dialog.close());

    dialog.addEventListener("click", (event: MouseEvent) => {
      if (event.target === dialog) dialog.close();
    });

    dialog.addEventListener("keydown", (event: KeyboardEvent) => {
      // Alt+Arrow is browser history navigation; leave modified keys to the browser.
      if (hasModifier(event)) return;
      if (event.key === "ArrowLeft") show(current - 1);
      else if (event.key === "ArrowRight") show(current + 1);
    });

    dialog.addEventListener("touchstart", (event: TouchEvent) => {
      const touch = event.touches.length === 1 ? event.touches[0] : null;
      touchStart = touch ? { x: touch.clientX, y: touch.clientY } : null;
    });

    dialog.addEventListener("touchend", (event: TouchEvent) => {
      if (touchStart === null) return;
      const dx = event.changedTouches[0].clientX - touchStart.x;
      const dy = event.changedTouches[0].clientY - touchStart.y;
      touchStart = null;
      if (Math.abs(dx) >= SWIPE_MIN_PX && Math.abs(dx) > Math.abs(dy)) {
        show(dx < 0 ? current + 1 : current - 1);
      }
    });

    dialog.addEventListener("close", () => {
      image.removeAttribute("src");
      // Edge moves focus back to the opening link after this event; wait a frame to override it.
      requestAnimationFrame(() => links[current].focus());
    });
  };

  const lightbox = document.querySelector<HTMLDialogElement>("dialog.lightbox");
  if (lightbox) setUpLightbox(lightbox);
}
