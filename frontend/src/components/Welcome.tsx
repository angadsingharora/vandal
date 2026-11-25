"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { cx } from "@/lib/format";
import { useWarRoom } from "@/lib/store";
import { SITE } from "@/lib/site";
import { SiteFooter, SiteHeader } from "./site/SiteShell";
import { Button } from "./ui";

/** Every page load lands on the welcome screen, except the two places it opens: the recorded
 * loop (`?mock=1`) and the workspace (`?workspace=1`). `?welcome` forces it even then. */
export function wantsWelcome(): boolean {
  if (typeof window === "undefined") return false;
  const params = new URLSearchParams(window.location.search);
  return params.has("welcome") || (params.get("mock") !== "1" && params.get("workspace") !== "1");
}

/** `?workspace=1`: the war room as a product, with nothing scripted. */
export function wantsWorkspace(): boolean {
  if (typeof window === "undefined") return false;
  return new URLSearchParams(window.location.search).get("workspace") === "1";
}

/** Keep (or drop) `?workspace=1` in the address bar, so a reload lands where the visitor chose. */
function markUrl(workspace: boolean) {
  const url = new URL(window.location.href);
  if (workspace) url.searchParams.set("workspace", "1");
  else url.searchParams.delete("workspace");
  url.searchParams.delete("welcome");
  window.history.replaceState(null, "", url.pathname + (url.search || ""));
}

/** A block that rises in after `delay` ms (globals.css `.rise`): the landing's entrance. */
function Rise({ delay, className, children }: { delay: number; className?: string; children: ReactNode }) {
  return (
    <div className={cx("rise", className)} style={{ animationDelay: `${delay}ms` }}>
      {children}
    </div>
  );
}

/** The landing: what Vandal is, and two ways in. The workspace opens on connecting an agent or
 * your books; the demo is the guided seven-step loop on a simulated company. The first button
 * needs neither: /check replays a month of payables and reports what Guard would have done. */
export function Welcome({ onClose, onWorkspace }: { onClose: () => void; onWorkspace: () => void }) {
  const s = useWarRoom();
  const [entering, setEntering] = useState(false);
  const [leaving, setLeaving] = useState(false);
  const mock = s.api?.mode === "mock";
  const router = useRouter();

  // Fade out, then unmount.
  useEffect(() => {
    if (!leaving) return;
    const t = setTimeout(onClose, 210);
    return () => clearTimeout(t);
  }, [leaving, onClose]);

  const workspace = () => {
    if (entering || !s.ready) return;
    s.setMode("workspace");
    markUrl(true);
    setLeaving(true);
    onWorkspace();
  };

  const demo = async () => {
    if (entering || !s.ready) return;
    setEntering(true);
    s.setMode("demo");
    markUrl(false);
    try {
      await s.reset("v0");
    } finally {
      setEntering(false);
      setLeaving(true);
    }
  };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Enter" && (mock ? demo() : router.push("/check"));
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  const link = mock
    ? { dot: "bg-warn", text: "Recorded loop: replaying in the browser." }
    : s.ready
      ? { dot: "bg-ok", text: "Live." }
      : s.waking
        ? { dot: "bg-warn live-dot", text: "Waking the server. It sleeps when idle and takes about a minute." }
        : s.error
          ? { dot: "bg-bad", text: "The server is not answering." }
          : { dot: "bg-faint live-dot", text: "Connecting…" };

  return (
    <div className={cx("fixed inset-0 z-50 overflow-y-auto bg-bg", leaving && "welcome-leave")}>
      <div role="dialog" aria-modal aria-labelledby="welcome-title" className="mx-auto flex min-h-full w-full max-w-6xl flex-col px-6 py-8 sm:px-10">
        <Rise delay={0}>
          <SiteHeader current="/" />
        </Rise>

        <main className="my-auto py-16">
          <Rise delay={80}>
            <h1 id="welcome-title" className="text-[2.4rem] font-bold leading-[1.05] tracking-tight text-ink sm:text-5xl xl:text-6xl">
              {/* Each sentence starts its own line. */}
              {SITE.headline.split(/(?<=\.) /).map((line) => (
                <span key={line} className="block">
                  {line.split(/\b/).map((word, i) =>
                    SITE.headlineTones[word] ? (
                      <span key={i} className={SITE.headlineTones[word] === "red" ? "text-red" : "text-blue"}>
                        {word}
                      </span>
                    ) : (
                      word
                    ),
                  )}
                </span>
              ))}
            </h1>
          </Rise>
          <Rise delay={200}>
            <p className="mt-6 max-w-xl text-[15px] leading-relaxed text-dim">
              <span className="text-ink">Your books can balance while the money goes to the wrong person.</span> {SITE.what}
            </p>
          </Rise>

          <Rise delay={320}>
            <div className="mt-10 flex flex-wrap items-center gap-3">
              {!mock && (
                <Link href="/check" className="inline-flex h-11 items-center rounded border border-blue/60 bg-blue/15 px-6 text-sm font-semibold text-blue hover:bg-blue/25">
                  Check a month of payments
                </Link>
              )}
              {!mock && (
                <Button onClick={workspace} disabled={!s.ready} className="h-11 px-6 text-sm font-semibold">
                  {s.ready ? "Open the workspace" : s.waking ? "Waking the server…" : "Connecting…"}
                </Button>
              )}
              {mock ? (
                <Button onClick={demo} busy={entering} disabled={!s.ready} className="h-11 px-6 text-sm font-semibold">
                  Watch the demo
                </Button>
              ) : (
                <button type="button" onClick={demo} disabled={!s.ready || entering} className="h-11 px-2 text-sm text-dim underline-offset-4 hover:text-ink hover:underline disabled:opacity-50">
                  {entering ? "Starting the demo…" : "or watch the demo"}
                </button>
              )}
            </div>
            <p className="mt-3 max-w-xl text-xs leading-relaxed text-faint">
No agent yet? The check replays a month of payables and shows what Vandal would have stopped. Have one? The workspace puts Vandal in front of it.
            </p>
            <p role="status" className="mt-6 flex items-center gap-2 text-xs text-dim">
              <span className={cx("inline-block size-1.5 rounded-full", link.dot)} />
              {link.text}
            </p>
          </Rise>
        </main>

        <Rise delay={460}>
          <SiteFooter />
        </Rise>
      </div>
    </div>
  );
}
