import { useEffect, useState } from "react";
import { App } from "./App";
import { Landing } from "./Landing";
import { Onboarding } from "./Onboarding";
import { ProductPage, CustomersPage, PricingPage, NowPage, ContactPage } from "./Pages";

// Client-side router for the whole SPA: one React app owns /, /signup and /app.
// pushState navigation keeps it a true single-page app; back/forward work.
export function Root() {
  const [path, setPath] = useState(() => location.pathname);
  useEffect(() => {
    const onpop = () => setPath(location.pathname);
    window.addEventListener("popstate", onpop);
    return () => window.removeEventListener("popstate", onpop);
  }, []);
  const go = (to: string) => {
    if (to === path) return;
    history.pushState({}, "", to);
    setPath(to);
    window.scrollTo(0, 0);
  };

  const marketing = path === "/" || path === "/signup" || path === "/onboarding" || path in {"/product":1,"/customers":1,"/pricing":1,"/now":1,"/contact":1};
  useEffect(() => {
    // Landing and onboarding are dark by brand; the app respects the user's
    // theme toggle (managed inside App/useTheme).
    if (marketing) document.documentElement.classList.add("dk");
  }, [marketing]);

  const pages: Record<string, (p: { go: (x: string) => void }) => JSX.Element> = {
    "/product": ProductPage, "/customers": CustomersPage, "/pricing": PricingPage,
    "/now": NowPage, "/contact": ContactPage,
  };
  const Page = pages[path];
  if (Page) return <Page go={go} />;
  if (path === "/signup" || path === "/onboarding") return <Onboarding go={go} />;
  if (path === "/app" || path.startsWith("/app")) return <App />;
  return <Landing go={go} />;
}
