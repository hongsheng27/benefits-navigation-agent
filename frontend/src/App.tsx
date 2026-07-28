import { HomePage } from "./pages/HomePage";
import { HomePageAlt } from "./pages/HomePageAlt";

// Temporary switch for comparing the two intake designs side by side.
// The current design stays the default; `?ui=alt` shows the alternate one.
// Remove this once a direction is chosen.
export default function App() {
  const isAlt = new URLSearchParams(window.location.search).get("ui") === "alt";

  return isAlt ? <HomePageAlt /> : <HomePage />;
}
