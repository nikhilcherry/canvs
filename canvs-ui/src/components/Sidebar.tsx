import { useState } from "react";
import { History } from "./History";
import { Palette } from "./Palette";

type SidebarTab = "palette" | "history";

export function Sidebar() {
  const [tab, setTab] = useState<SidebarTab>("palette");

  return (
    <div className="sidebar">
      <div className="sidebar-tabs">
        <button className={tab === "palette" ? "active" : ""} onClick={() => setTab("palette")}>
          Palette
        </button>
        <button className={tab === "history" ? "active" : ""} onClick={() => setTab("history")}>
          History
        </button>
      </div>
      <div className="sidebar-content">{tab === "palette" ? <Palette /> : <History />}</div>
    </div>
  );
}
