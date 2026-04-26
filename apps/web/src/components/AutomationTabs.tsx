export type AutomationTab = "contacts" | "rules" | "suggestions" | "watched" | "imports";

const tabs: Array<{label: string; value: AutomationTab}> = [
  {label: "Contacts", value: "contacts"},
  {label: "Rules", value: "rules"},
  {label: "Suggestions", value: "suggestions"},
  {label: "Watched Folders", value: "watched"},
  {label: "Import Status", value: "imports"},
];

export function AutomationTabs({
  activeTab,
  onChange,
}: {
  activeTab: AutomationTab;
  onChange: (tab: AutomationTab) => void;
}) {
  return (
    <div className="automation-tabs" role="tablist" aria-label="Automation sections">
      {tabs.map((tab) => (
        <button
          type="button"
          key={tab.value}
          role="tab"
          aria-selected={activeTab === tab.value}
          className={activeTab === tab.value ? "active" : undefined}
          onClick={() => onChange(tab.value)}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}
