import {FormEvent} from "react";

import type {FilingRule, FilingRuleEvaluation, FilingRuleWrite} from "../types";
import {formatAction, formatCondition} from "./automationFormatting";

export function AutomationRulesPanel({
  rules,
  dryRunResults,
  status,
  onSaveRule,
  onDryRun,
}: {
  rules: FilingRule[];
  dryRunResults: FilingRuleEvaluation[];
  status: string | null;
  onSaveRule: (payload: FilingRuleWrite) => Promise<void>;
  onDryRun: (rule: FilingRule) => Promise<void>;
}) {
  async function handleSaveRule(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const name = String(form.get("ruleName") ?? "").trim();
    const conditionField = String(form.get("conditionField") ?? "document_family");
    const conditionOp = String(form.get("conditionOp") ?? "eq");
    const conditionValue = String(form.get("conditionValue") ?? "").trim();
    const actionType = String(form.get("actionType") ?? "add_tag");
    const actionValue = String(form.get("actionValue") ?? "").trim();
    if (!name || !conditionValue || !actionValue) {
      return;
    }
    await onSaveRule({
      name,
      enabled: true,
      priority: 70,
      reviewRequired: Boolean(form.get("reviewRequired")),
      conditions: [{field: conditionField, op: conditionOp, value: conditionValue}],
      actions: [_actionPayload(actionType, actionValue)],
    });
    event.currentTarget.reset();
  }

  const matched = dryRunResults.filter((result) => result.matched).length;
  const firstDryRun = dryRunResults[0];

  return (
    <section className="automation-card">
      <h2>Rules</h2>
      <form className="rule-builder" onSubmit={(event) => void handleSaveRule(event)}>
        <label>
          Rule name
          <input name="ruleName" aria-label="Rule name" placeholder="Medical EOB filing" />
        </label>
        <label>
          Condition field
          <select name="conditionField" aria-label="Condition field" defaultValue="document_family">
            <option value="document_family">document_family</option>
            <option value="tags">tags</option>
            <option value="counterparty">counterparty</option>
            <option value="sensitivity">sensitivity</option>
            <option value="review_status">review_status</option>
          </select>
        </label>
        <label>
          Condition operator
          <select name="conditionOp" aria-label="Condition operator" defaultValue="eq">
            <option value="eq">eq</option>
            <option value="contains">contains</option>
            <option value="in">in</option>
            <option value="exists">exists</option>
          </select>
        </label>
        <label>
          Condition value
          <input name="conditionValue" aria-label="Condition value" placeholder="medical_eob" />
        </label>
        <label>
          Action type
          <select name="actionType" aria-label="Action type" defaultValue="add_tag">
            <option value="add_tag">add_tag</option>
            <option value="set_sensitivity">set_sensitivity</option>
            <option value="set_document_type">set_document_type</option>
            <option value="create_review_task">create_review_task</option>
          </select>
        </label>
        <label>
          Action value
          <input name="actionValue" aria-label="Action value" placeholder="insurance" />
        </label>
        <label className="checkbox-label">
          <input name="reviewRequired" type="checkbox" defaultChecked />
          Review before apply
        </label>
        <button type="submit">Save rule</button>
      </form>
      <div className="automation-list">
        {rules.map((rule) => (
          <article key={rule.id} className="rule-row">
            <div>
              <strong>{rule.name}</strong>
              <span>{rule.enabled ? "Enabled" : "Paused"} · priority {rule.priority ?? 50}</span>
              <span>{rule.conditions.map(formatCondition).join(" · ")}</span>
            </div>
            <div className="row-actions">
              <button type="button" onClick={() => void onSaveRule({...rule, enabled: !rule.enabled})}>
                {rule.enabled ? "Pause rule" : "Resume rule"}
              </button>
              <button type="button" onClick={() => void onDryRun(rule)}>Dry run</button>
            </div>
          </article>
        ))}
      </div>
      {firstDryRun ? (
        <aside className="dry-run-panel" aria-label="Rule dry-run result">
          <h3>Rule dry-run explanation</h3>
          <p>{status ?? `Matched ${matched} document${matched === 1 ? "" : "s"}`}</p>
          <section>
            <h4>Conditions</h4>
            {firstDryRun.conditions.map((condition, index) => (
              <code key={index}>{formatCondition(condition)}</code>
            ))}
          </section>
          <section>
            <h4>Proposed actions</h4>
            <ActionList actions={firstDryRun.proposedActions} emptyLabel="No proposed actions" />
          </section>
          <section>
            <h4>Blocked actions</h4>
            <ActionList actions={firstDryRun.blockedActions} emptyLabel="No blocked actions" />
          </section>
        </aside>
      ) : null}
    </section>
  );
}

function ActionList({
  actions,
  emptyLabel,
}: {
  actions: Array<Record<string, unknown>>;
  emptyLabel: string;
}) {
  return actions.length ? (
    <ul className="action-list">
      {actions.map((action, index) => <li key={index}>{formatAction(action)}</li>)}
    </ul>
  ) : <p>{emptyLabel}</p>;
}

function _actionPayload(actionType: string, actionValue: string): Record<string, unknown> {
  if (actionType === "add_tag") {
    return {type: actionType, tag: actionValue};
  }
  return {type: actionType, value: actionValue};
}
