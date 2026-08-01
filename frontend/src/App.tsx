import { useState } from "react";

import { AppNav, type AppSection } from "./components/shell/AppNav";
import {
  focusFromCase,
  type AgencySituationFocus,
} from "./lib/agencySituation";
import { AgenciesPage } from "./pages/AgenciesPage";
import { HomePageAlt, type IntakeMode } from "./pages/HomePageAlt";
import { ProductHomePage } from "./pages/ProductHomePage";
import { TrackedCasesPage } from "./pages/TrackedCasesPage";

export default function App() {
  const [section, setSection] = useState<AppSection>("home");
  const [intakeMode, setIntakeMode] = useState<IntakeMode>("live");
  const [agencyFocus, setAgencyFocus] = useState<AgencySituationFocus | null>(
    null,
  );
  const [trackingHighlight, setTrackingHighlight] = useState<string | null>(
    null,
  );

  function goHome() {
    setSection("home");
    setIntakeMode("live");
    setAgencyFocus(null);
    setTrackingHighlight(null);
  }

  function goConsult() {
    setIntakeMode("live");
    setSection("consult");
  }

  return (
    <div className="min-h-screen">
      <AppNav
        active={section}
        onNavigate={(next) => {
          if (next === "home") {
            goHome();
            return;
          }
          setSection(next);
          if (next === "consult") {
            setIntakeMode("live");
          }
          if (next !== "agencies") {
            setAgencyFocus(null);
          }
          if (next !== "tracking") {
            setTrackingHighlight(null);
          }
        }}
      />

      {section === "home" ? (
        <ProductHomePage
          onStartConsult={goConsult}
          onOpenTracking={() => setSection("tracking")}
          onOpenAgencies={() => setSection("agencies")}
        />
      ) : null}

      {section === "consult" ? (
        <HomePageAlt
          hideBrandHeader
          mode={intakeMode}
          onToggleMode={() =>
            setIntakeMode((current) => (current === "live" ? "demo" : "live"))
          }
          onExitDemo={() => setIntakeMode("live")}
          onGoToTracking={(lifeEventId) => {
            setTrackingHighlight(lifeEventId);
            setSection("tracking");
          }}
        />
      ) : null}
      {section === "tracking" ? (
        <TrackedCasesPage
          highlightLifeEventId={trackingHighlight}
          onStartConsult={goConsult}
          onViewAgencies={(trackedCase) => {
            setAgencyFocus(focusFromCase(trackedCase));
            setSection("agencies");
          }}
        />
      ) : null}
      {section === "agencies" ? (
        <AgenciesPage
          focus={agencyFocus}
          onClearFocus={() => setAgencyFocus(null)}
        />
      ) : null}
    </div>
  );
}
