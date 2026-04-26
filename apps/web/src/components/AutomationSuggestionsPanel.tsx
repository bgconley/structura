import type {FilingSuggestion} from "../types";
import {formatAction, formatCondition} from "./automationFormatting";

export function AutomationSuggestionsPanel({
  suggestions,
  onAccept,
  onReject,
  onDefer,
}: {
  suggestions: FilingSuggestion[];
  onAccept: (suggestion: FilingSuggestion) => Promise<void>;
  onReject: (suggestion: FilingSuggestion) => Promise<void>;
  onDefer: (suggestion: FilingSuggestion) => Promise<void>;
}) {
  return (
    <section className="automation-card">
      <h2>Suggested filing</h2>
      {suggestions.map((suggestion) => (
        <article key={suggestion.runId} className="suggestion-row">
          <div>
            <strong>{suggestion.documentTitle}</strong>
            <span>{suggestion.ruleName} · {suggestion.proposedActions.length} proposed actions</span>
            <section className="automation-mini-panel" aria-label="Suggestion explanation">
              <h3>Suggestion explanation</h3>
              <ActionList title="Proposed actions" actions={suggestion.proposedActions} />
              <ActionList title="Blocked actions" actions={suggestion.blockedActions} />
              <ConditionList explanation={suggestion.explanation} />
            </section>
          </div>
          <div className="suggestion-actions">
            <button type="button" onClick={() => void onAccept(suggestion)}>
              Accept suggestion
            </button>
            <button type="button" onClick={() => void onReject(suggestion)}>
              Reject
            </button>
            <button type="button" onClick={() => void onDefer(suggestion)}>
              Defer
            </button>
          </div>
        </article>
      ))}
      {!suggestions.length ? <p>No pending filing suggestions.</p> : null}
    </section>
  );
}

function ActionList({
  title,
  actions,
}: {
  title: string;
  actions: Array<Record<string, unknown>>;
}) {
  return (
    <div>
      <h4>{title}</h4>
      {actions.length ? (
        <ul className="action-list">
          {actions.map((action, index) => <li key={index}>{formatAction(action)}</li>)}
        </ul>
      ) : <p>None</p>}
    </div>
  );
}

function ConditionList({explanation}: {explanation: Record<string, unknown>}) {
  const conditions = Array.isArray(explanation.conditions)
    ? explanation.conditions as Array<Record<string, unknown>>
    : [];
  return conditions.length ? (
    <div>
      <h4>Conditions</h4>
      {conditions.map((condition, index) => <code key={index}>{formatCondition(condition)}</code>)}
    </div>
  ) : null;
}
