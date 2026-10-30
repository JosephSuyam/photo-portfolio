// Discourage saving photos: no context menu, dragging, or middle-click new tab on them.
// A determined visitor can still get the files; this only removes the easy ways.

// A block keeps these names out of the global scope shared with the other site scripts.
{
  const PHOTO_MENU_TARGETS = "img, picture, a[data-lightbox], dialog.lightbox";
  const MIDDLE_BUTTON = 1;

  const closestTo = (target: EventTarget | null, selector: string): Element | null =>
    target instanceof Element ? target.closest(selector) : null;

  document.addEventListener("contextmenu", (event: MouseEvent) => {
    if (closestTo(event.target, PHOTO_MENU_TARGETS)) event.preventDefault();
  });

  document.addEventListener("dragstart", (event: DragEvent) => {
    if (closestTo(event.target, "img, a[data-lightbox]")) event.preventDefault();
  });

  document.addEventListener("auxclick", (event: MouseEvent) => {
    if (event.button === MIDDLE_BUTTON && closestTo(event.target, "a[data-lightbox]")) {
      event.preventDefault();
    }
  });
}
