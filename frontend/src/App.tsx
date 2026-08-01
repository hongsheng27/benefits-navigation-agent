import { useState } from "react";

import { AppNav, type AppSection } from "./components/shell/AppNav";
import {
  focusFromCase,
  type AgencySituationFocus,
} from "./lib/agencySituation";
import { AgenciesPage } from "./pages/AgenciesPage";
import { HomePageAlt, type IntakeMode } from "./pages/HomePageAlt";
import { TrackedCasesPage } from "./pages/TrackedCasesPage";

export default function App() {
  const [section, setSection] = useState<AppSection>("consult");
  const [intakeMode, setIntakeMode] = useState<IntakeMode>("live");
  const [agencyFocus, setAgencyFocus] = useState<AgencySituationFocus | null>(
    null,
  );
  const [trackingHighlight, setTrackingHighlight] = useState<string | null>(
    null,
  );

  return (
    <div className="min-h-screen">
      <AppNav
        active={section}
        onNavigate={(next) => {
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
          onStartConsult={() => {
            setTrackingHighlight(null);
            setIntakeMode("live");
            setSection("consult");
          }}
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
