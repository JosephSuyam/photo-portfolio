// Album index: hovering an album card with a mouse, or reaching it with the keyboard, shows
// that album in the feature card. Leaving the albums section shows the first album again.
// Taps on touch screens just open the album.

// A block keeps these names out of the global scope shared with the other site scripts.
{
  interface AlbumView {
    href: string;
    title: string;
    count: string;
    sizes: string;
    webpSrcset: string;
    jpegSrcset: string;
    src: string;
    width: string;
    height: string;
  }

  const readView = (link: HTMLAnchorElement): AlbumView | null => {
    const source = link.querySelector<HTMLSourceElement>("source");
    const image = link.querySelector<HTMLImageElement>("img");
    const title = link.querySelector(".feature-title, .album-title");
    const count = link.querySelector(".feature-count, .album-count");
    if (!source || !image || !title || !count) return null;
    return {
      href: link.getAttribute("href") ?? "",
      title: title.textContent ?? "",
      count: count.textContent ?? "",
      // How wide this album's cover renders in the feature box; it depends on the cover's shape.
      sizes: link.dataset.featureSizes ?? image.sizes,
      webpSrcset: source.srcset,
      jpegSrcset: image.srcset,
      src: image.getAttribute("src") ?? "",
      width: image.getAttribute("width") ?? "",
      height: image.getAttribute("height") ?? "",
    };
  };

  const setUpPreview = (section: HTMLElement): void => {
    const feature = section.querySelector<HTMLAnchorElement>("a.feature");
    const source = feature?.querySelector<HTMLSourceElement>("source");
    const image = feature?.querySelector<HTMLImageElement>("img");
    const title = feature?.querySelector<HTMLElement>(".feature-title");
    const count = feature?.querySelector<HTMLElement>(".feature-count");
    const label = feature?.querySelector<HTMLElement>(".feature-label");
    const first = feature ? readView(feature) : null;
    if (!feature || !source || !image || !title || !count || !label || !first) return;

    const show = (view: AlbumView): void => {
      if (feature.getAttribute("href") === view.href) return;
      feature.setAttribute("href", view.href);
      title.textContent = view.title;
      count.textContent = view.count;
      source.sizes = view.sizes;
      image.sizes = view.sizes;
      source.srcset = view.webpSrcset;
      image.srcset = view.jpegSrcset;
      image.src = view.src;
      image.setAttribute("width", view.width);
      image.setAttribute("height", view.height);
      label.hidden = view.href !== first.href;
    };

    section.querySelectorAll<HTMLAnchorElement>(".album-card a").forEach((link) => {
      const view = readView(link);
      if (!view) return;
      link.addEventListener("pointerenter", (event: PointerEvent) => {
        if (event.pointerType !== "touch") show(view);
      });
      link.addEventListener("focus", () => {
        if (link.matches(":focus-visible")) show(view);
      });
    });

    section.addEventListener("pointerleave", () => {
      if (!section.contains(document.activeElement)) show(first);
    });
    section.addEventListener("focusout", (event: FocusEvent) => {
      const next = event.relatedTarget;
      if (!(next instanceof Node) || !section.contains(next)) show(first);
    });
    // A page restored from the back/forward cache shows the first album again.
    window.addEventListener("pageshow", (event: PageTransitionEvent) => {
      if (event.persisted) show(first);
    });
  };

  document
    .querySelectorAll<HTMLElement>("[data-album-preview]")
    .forEach(setUpPreview);
}
