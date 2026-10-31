/** One place for what the site says about itself: the pages (landing, /about, /contact), the
 * share card, and the footer all read from here. */
export const SITE = {
  name: "Vandal",
  tagline: "Security for AI finance agents",
  /** The one-sentence answer to "what is it". */
  what: "Vandal is the control layer for companies handing accounts payable to AI agents. It checks every action before money moves, and it keeps attacking its own checks so they get stronger with every change.",
  url: "https://frontend-dusky-eight-92.vercel.app",
  github: "https://github.com/angadsingharora/vandal",
  /** Where a pilot or demo request goes. Set in one place so it is easy to change. */
  email: "angadsingharora@gmail.com",
  founders: [
    { name: "Angad Arora", link: "https://github.com/angadsingharora" },
    { name: "Mohith Ram Narendra Babu", link: null },
  ],
  docs: [
    { label: "README", href: "https://github.com/angadsingharora/vandal#readme", what: "what is built, what is real, the scorecard from an actual run" },
    { label: "DESIGN.md", href: "https://github.com/angadsingharora/vandal/blob/main/docs/DESIGN.md", what: "the twin, the invariants, search, synthesis, verification" },
    { label: "SPEC.md", href: "https://github.com/angadsingharora/vandal/blob/main/docs/SPEC.md", what: "the original product brief" },
  ],
} as const;

export const NAV = [
  { href: "/", label: "Product" },
  { href: "/about", label: "About" },
  { href: "/contact", label: "Contact" },
] as const;
