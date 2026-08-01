import { useEffect, useRef, useState } from "react";

import { AppNav, type AppSection } from "./components/shell/AppNav";
import {
  focusFromCase,
  type AgencySituationFocus,
} from "./lib/agencySituation";
import {
  historyStateFromLocation,
  normalizeHistoryState,
  pushAppHistory,
  replaceAppHistory,
  sameHistoryState,
  type AppHistoryState,
  type HistoryConsultStep,
} from "./lib/navigationHistory";
import { AgenciesPage } from "./pages/AgenciesPage";
import { HomePageAlt, type IntakeMode } from "./pages/HomePageAlt";
import { ProductHomePage } from "./pages/ProductHomePage";
import { TrackedCasesPage } from "./pages/TrackedCasesPage";

function buildHistoryState(input: {
  section: AppSection;
  intakeMode: IntakeMode;
  consultStep: HistoryConsultStep;
  demoSceneIndex: number;
}): AppHistoryState {
  return {
    v: 1,
    section: input.section,
    mode: input.section === "consult" ? input.intakeMode : "live",
    consultStep:
      input.section === "consult" && input.intakeMode === "live"
        ? input.consultStep
        : "landing",
    demoSceneIndex:
      input.section === "consult" && input.intakeMode === "demo"
        ? input.demoSceneIndex
        : 0,
  };
}

export default function App() {
  const initial = historyStateFromLocation();
  const [section, setSection] = useState<AppSection>(initial.section);
  const [intakeMode, setIntakeMode] = useState<IntakeMode>(
    initial.section === "consult" ? initial.mode : "live",
  );
  const [consultStep, setConsultStep] = useState<HistoryConsultStep>(
    initial.consultStep,
  );
  const [demoSceneIndex, setDemoSceneIndex] = useState(initial.demoSceneIndex);
  const [historyConsultStep, setHistoryConsultStep] =
    useState<HistoryConsultStep | null>(
      initial.section === "consult" && initial.mode === "live"
        ? initial.consultStep
        : null,
    );
  const [historyDemoSceneIndex, setHistoryDemoSceneIndex] = useState<
    number | null
  >(
    initial.section === "consult" && initial.mode === "demo"
      ? initial.demoSceneIndex
      : null,
  );
  const [agencyFocus, setAgencyFocus] = useState<AgencySituationFocus | null>(
    null,
  );
  const [trackingHighlight, setTrackingHighlight] = useState<string | null>(
    null,
  );

  const skipPushRef = useRef(true);
  const stateRef = useRef({
    section,
    intakeMode,
    consultStep,
    demoSceneIndex,
  });
  stateRef.current = { section, intakeMode, consultStep, demoSceneIndex };

  useEffect(() => {
    const next = buildHistoryState({
      section,
      intakeMode,
      consultStep,
      demoSceneIndex,
    });
    if (skipPushRef.current) {
      skipPushRef.current = false;
      replaceAppHistory(next);
      return;
    }
    pushAppHistory(next);
  }, [section, intakeMode, consultStep, demoSceneIndex]);

  useEffect(() => {
    function onPopState(event: PopStateEvent) {
      const next = event.state
        ? normalizeHistoryState(event.state)
        : historyStateFromLocation();
      const current = buildHistoryState(stateRef.current);
      if (sameHistoryState(current, next)) {
        return;
      }
      skipPushRef.current = true;
      setSection(next.section);
      setIntakeMode(next.section === "consult" ? next.mode : "live");
      setConsultStep(next.consultStep);
      setDemoSceneIndex(next.demoSceneIndex);
      if (next.section === "consult" && next.mode === "live") {
        setHistoryConsultStep(next.consultStep);
      } else {
        setHistoryConsultStep(null);
      }
      if (next.section === "consult" && next.mode === "demo") {
        setHistoryDemoSceneIndex(next.demoSceneIndex);
      } else {
        setHistoryDemoSceneIndex(null);
      }
      if (next.section !== "agencies") {
        setAgencyFocus(null);
      }
      if (next.section !== "tracking") {
        setTrackingHighlight(null);
      }
    }
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  function goHome() {
    setSection("home");
    setIntakeMode("live");
    setConsultStep("landing");
    setDemoSceneIndex(0);
    setHistoryConsultStep(null);
    setHistoryDemoSceneIndex(null);
    setAgencyFocus(null);
    setTrackingHighlight(null);
  }

  function goConsult() {
    setIntakeMode("live");
    setSection("consult");
    setConsultStep("landing");
    setHistoryConsultStep("landing");
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
            if (section !== "consult") {
              setConsultStep("landing");
              setHistoryConsultStep("landing");
            }
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
          historyConsultStep={historyConsultStep}
          historyDemoSceneIndex={historyDemoSceneIndex}
          onConsultStepChange={(step) => {
            setConsultStep(step);
            setHistoryConsultStep(null);
          }}
          onDemoSceneIndexChange={(index) => {
            setDemoSceneIndex(index);
            setHistoryDemoSceneIndex(null);
          }}
          onToggleMode={() =>
            setIntakeMode((current) => {
              const next = current === "live" ? "demo" : "live";
              if (next === "demo") {
                setDemoSceneIndex(0);
                setHistoryDemoSceneIndex(0);
              } else {
                setConsultStep("landing");
                setHistoryConsultStep("landing");
              }
              return next;
            })
          }
          onExitDemo={() => {
            setIntakeMode("live");
            setConsultStep("landing");
            setHistoryConsultStep("landing");
            setDemoSceneIndex(0);
            setHistoryDemoSceneIndex(null);
          }}
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
