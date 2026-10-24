// Scroll the horizontal strips with a regular mouse wheel, as on the reference site.

function scrollSidewaysOnWheel(strip: HTMLElement): void {
  strip.addEventListener(
    "wheel",
    (event: WheelEvent) => {
      const isVerticalWheel = Math.abs(event.deltaY) > Math.abs(event.deltaX);
      const canScroll = strip.scrollWidth > strip.clientWidth;
      if (!isVerticalWheel || !canScroll || event.ctrlKey) return;
      event.preventDefault();
      strip.scrollLeft += event.deltaY;
    },
    { passive: false },
  );
}

document
  .querySelectorAll<HTMLElement>("[data-horizontal-scroll]")
  .forEach(scrollSidewaysOnWheel);
