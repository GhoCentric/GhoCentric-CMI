# Phase 4F final site gate

Base release source: `5043b0b32935b1ca68ba960c4ef9251e62e8dd31` (`v1.12.0`).

The final website gate verifies:

- package and release claims against repository evidence;
- GhostAPI JSON-safe snapshot, restore, and same-next-event deterministic continuation;
- HTML structure, anchors, assets, link safety, image alt text, and button semantics;
- design-token contrast of at least 4.5:1 against the site background;
- no dead CSS classes and no legacy trace/demo styling;
- live external links;
- Android Chrome responsive overflow at 320, 360, 390, 412, 768, and 1024 CSS pixels;
- git whitespace and mutation scope.

The Phase-4F resume v2 additionally removes the three legacy mobile trace rules
that the first Phase-4F cleanup missed.
