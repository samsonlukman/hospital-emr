import { Fragment, useEffect, useState } from "react";
import { Alert } from "../../components/Alert";
import { Button } from "../../components/Button";
import { Card } from "../../components/Card";
import { LoadingState } from "../../components/LoadingState";
import { SectionHeader } from "../../components/SectionHeader";
import {
  collectLaboratorySample,
  deleteLaboratoryOrder,
  fetchLaboratoryWorkflow,
  newLaboratoryRequestId,
  saveLaboratoryResults,
  validateLaboratoryResults,
} from "../../services/laboratoryBilling";
import { PatientAccountRequestError } from "../../services/patientAccount";
import type {
  LaboratoryWorkflowPayload,
  LaboratoryWorkflowTest,
} from "../../types/laboratoryCatalogue";
import { enteredLaboratoryResult, resultIsNumeric } from "./laboratoryView";

interface LaboratoryWorkflowPanelProps {
  orderUuid: string;
  patientUuid?: string;
  visitUuid?: string;
}

function errorMessage(error: unknown): string {
  return error instanceof PatientAccountRequestError
    ? error.message
    : "The laboratory step could not be completed. Try again.";
}

function optionValue(option: LaboratoryWorkflowTest["options"][number]): string {
  return typeof option === "string" ? option : option.value;
}

function optionLabel(option: LaboratoryWorkflowTest["options"][number]): string {
  return typeof option === "string" ? option : option.label || option.value;
}

function workflowKey(test: LaboratoryWorkflowTest, index: number): string {
  return `${test.orderedAs || test.name}-${test.testId || test.name}-${test.analysisId || index}`;
}

function highResultFlag(flag: string | undefined): boolean {
  return flag === "H" || flag === "C" || flag === "A";
}

function numericFlag(
  value: string,
  low: string,
  high: string,
  lowInclusive = true,
  highInclusive = true,
): "L" | "H" | "" | null {
  const result = Number(value.replace(/,/g, ""));
  if (!value.trim() || !Number.isFinite(result)) return null;
  const floor = Number(low.replace(/,/g, ""));
  const ceiling = Number(high.replace(/,/g, ""));
  const hasLow = low.trim() !== "" && Number.isFinite(floor);
  const hasHigh = high.trim() !== "" && Number.isFinite(ceiling);
  if (!hasLow && !hasHigh) return null;
  if (hasLow && (lowInclusive ? result < floor : result <= floor)) return "L";
  if (hasHigh && (highInclusive ? result > ceiling : result >= ceiling)) return "H";
  return "";
}

export function LaboratoryWorkflowPanel({
  orderUuid,
  patientUuid,
  visitUuid,
}: LaboratoryWorkflowPanelProps) {
  const [workflow, setWorkflow] = useState<LaboratoryWorkflowPayload | null>(null);
  const [sampleTypeId, setSampleTypeId] = useState("341");
  const [sampleSourceId, setSampleSourceId] = useState("2");
  const [resultValues, setResultValues] = useState<Record<string, string>>({});
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [units, setUnits] = useState<Record<string, string>>({});
  const [rangeLows, setRangeLows] = useState<Record<string, string>>({});
  const [rangeHighs, setRangeHighs] = useState<Record<string, string>>({});
  const [flags, setFlags] = useState<Record<string, string>>({});
  const [validationDecision, setValidationDecision] = useState<"accept" | "reject">("accept");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [removeTarget, setRemoveTarget] = useState<{ orderUuid: string; name: string } | null>(null);
  const [removeReason, setRemoveReason] = useState("");

  const applyWorkflow = (value: LaboratoryWorkflowPayload) => {
    setWorkflow(value);
    setSampleTypeId(value.sample.sampleTypeId || "341");
    setSampleSourceId(value.sample.sampleSourceId || "2");
    setResultValues(
      Object.fromEntries(
        value.tests.map((test, index) => [
          workflowKey(test, index),
          enteredLaboratoryResult(test.resultValue || test.qualifiedResultValue, test.options),
        ]),
      ),
    );
    setNotes(Object.fromEntries(value.tests.map((test, index) => [workflowKey(test, index), test.note])));
    setUnits(Object.fromEntries(value.tests.map((test, index) => [workflowKey(test, index), test.unit || ""])));
    setRangeLows(Object.fromEntries(value.tests.map((test, index) => [workflowKey(test, index), test.referenceLow || ""])));
    setRangeHighs(Object.fromEntries(value.tests.map((test, index) => [workflowKey(test, index), test.referenceHigh || ""])));
    setFlags(Object.fromEntries(value.tests.map((test, index) => [workflowKey(test, index), test.flag || ""])));
  };

  const load = () => {
    setLoading(true);
    fetchLaboratoryWorkflow(orderUuid, patientUuid, visitUuid)
      .then((value) => {
        applyWorkflow(value);
        setError("");
      })
      .catch((reason) => setError(errorMessage(reason)))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
    // The workflow is intentionally reloaded only when the order identity changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [orderUuid, patientUuid, visitUuid]);

  useEffect(() => {
    if (!workflow) return;
    setFlags((current) => {
      let changed = false;
      const next = { ...current };
      workflow.tests.forEach((test, index) => {
        const key = workflowKey(test, index);
        const computed = numericFlag(
          resultValues[key] || "",
          rangeLows[key] ?? test.referenceLow ?? "",
          rangeHighs[key] ?? test.referenceHigh ?? "",
          test.referenceLowInclusive !== false,
          test.referenceHighInclusive !== false,
        );
        if (computed === null) return;
        const existing = current[key] || "";
        if (existing === "C") return;
        if (existing === "A" && computed === "") return;
        if (existing !== computed) {
          next[key] = computed;
          changed = true;
        }
      });
      return changed ? next : current;
    });
  }, [workflow, resultValues, rangeLows, rangeHighs]);

  if (loading) {
    return <LoadingState variant="board" label="Loading laboratory workflow…" />;
  }
  if (!workflow) {
    return <Alert tone="danger" title="Laboratory workflow unavailable"><p>{error}</p></Alert>;
  }

  const canCollect = workflow.sample.status !== "collected";
  const canValidate = workflow.validation.status !== "validated" || !workflow.validation.validatedBy;
  const tests = workflow.tests;
  const entered = tests.flatMap((test, index) => {
    const key = workflowKey(test, index);
    if (!(resultValues[key] || "").trim()) {
      return [];
    }
    return [{ test, index, key }];
  });

  const collect = () => {
    setSaving("collect");
    setMessage("");
    collectLaboratorySample(orderUuid, {
      requestId: newLaboratoryRequestId(),
      patientUuid,
      sampleTypeId,
      sampleSourceId,
      testIds: tests.map((test) => test.testId).filter(Boolean),
    })
      .then((value) => {
        applyWorkflow(value);
        setMessage(value.message || "Sample collected.");
        setError("");
      })
      .catch((reason) => setError(errorMessage(reason)))
      .finally(() => setSaving(""));
  };

  const saveResults = () => {
    setSaving("results");
    setMessage("");
    saveLaboratoryResults(orderUuid, {
      patientUuid,
      accession: workflow.sample.accession,
      requestId: newLaboratoryRequestId(),
      results: entered.map(({ test, key }) => ({
          testId: test.testId,
          testName: test.name,
          orderedAs: test.orderedAs || test.name,
          analysisId: test.analysisId,
          resultId: test.resultId,
          resultType: test.resultType,
          resultValue: resultValues[key] || "",
          qualifiedResultValue: resultValues[key] || "",
          resultLabel: optionLabel(
            test.options.find((option) => optionValue(option) === resultValues[key]) || "",
          ),
          note: notes[key] || "",
          unit: units[key] || test.unit || "",
          referenceLow: rangeLows[key] ?? test.referenceLow ?? "",
          referenceHigh: rangeHighs[key] ?? test.referenceHigh ?? "",
          referenceLowInclusive: test.referenceLowInclusive !== false,
          referenceHighInclusive: test.referenceHighInclusive !== false,
          flag: flags[key] || "",
        })),
    })
      .then((value) => {
        applyWorkflow(value);
        setMessage(value.message || "Results saved.");
        setError("");
      })
      .catch((reason) => setError(errorMessage(reason)))
      .finally(() => setSaving(""));
  };

  const removeOrder = () => {
    if (!removeTarget || removeReason.trim().length < 3) {
      setError("Enter why this test is being removed.");
      return;
    }
    setSaving("remove");
    setError("");
    deleteLaboratoryOrder({
      orderUuid: removeTarget.orderUuid,
      reason: removeReason.trim(),
      patientUuid,
    })
      .then(() => {
        setRemoveTarget(null);
        setRemoveReason("");
        setMessage("That test was removed from this order.");
        load();
      })
      .catch((reason) => setError(errorMessage(reason)))
      .finally(() => setSaving(""));
  };

  const validate = () => {
    setSaving("validate");
    setMessage("");
    validateLaboratoryResults(orderUuid, {
      patientUuid,
      accession: workflow.sample.accession,
      requestId: newLaboratoryRequestId(),
      testName: workflow.order.testName,
      decision: validationDecision,
      results: entered.map(({ test, key }) => ({
          testId: test.testId,
          testName: test.name,
          orderedAs: test.orderedAs || test.name,
          analysisId: test.analysisId,
          resultId: test.resultId,
          resultValue: resultValues[key] || "",
          resultLabel: optionLabel(
            test.options.find((option) => optionValue(option) === resultValues[key]) || "",
          ),
          note: notes[key] || "",
          flag: flags[key] || "",
        })),
    })
      .then((value) => {
        applyWorkflow(value);
        setMessage(value.message || "Results validated.");
        setError("");
      })
      .catch((reason) => setError(errorMessage(reason)))
      .finally(() => setSaving(""));
  };

  return (
    <Card className="lab-workflow">
      <SectionHeader
        title="Laboratory process"
        description="Complete each step in order. The result is released only after validation."
      />
      <ol className="lab-workflow__progress" aria-label="Laboratory process steps">
        <li className={canCollect ? "is-current" : "is-done"}>
          <span>1</span>
          <strong>Collect</strong>
        </li>
        <li className={canCollect ? "" : "is-current"}>
          <span>2</span>
          <strong>Result</strong>
        </li>
        <li className={canValidate ? "" : "is-done"}>
          <span>3</span>
          <strong>Validate</strong>
        </li>
      </ol>
      {error ? <Alert tone="danger" title="Unable to complete step"><p>{error}</p></Alert> : null}
      {message ? <Alert tone="success" title="Saved"><p>{message}</p></Alert> : null}

      <div className={`lab-workflow__stage ${canCollect ? "is-current" : "is-done"}`}>
        <div className="lab-workflow__stage-heading">
          <div>
            <span className="lab-workflow__eyebrow">Step 1</span>
            <h3>Collect sample</h3>
          </div>
          <span className="lab-workflow__status">
            {canCollect ? "Waiting" : "Complete"}
          </span>
        </div>
        <p className="lab-workflow__hint">
          {canCollect
            ? "Confirm the specimen and where it was received."
            : `Accession ${workflow.sample.accession || "assigned"}`}
        </p>
        {canCollect ? (
          <div className="lab-workflow__fields">
            <label>
              Sample type
              <select value={sampleTypeId} onChange={(event) => setSampleTypeId(event.target.value)}>
                <option value="341">Blood specimen</option>
                <option value="342">Urine</option>
                      <option value="345">Serum</option>
                      <option value="112">Sputum</option>
              </select>
            </label>
            <label>
              Collection location
              <select value={sampleSourceId} onChange={(event) => setSampleSourceId(event.target.value)}>
                <option value="2">Outpatient department</option>
                <option value="1">Inpatient ward</option>
                <option value="3">Emergency</option>
                <option value="7">Registration desk</option>
              </select>
            </label>
            {tests.length === 0 || tests.every((test) => !test.testId) ? (
              <p className="lab-workflow__hint">
                This test is not on the laboratory list yet, so the sample cannot be collected.
              </p>
            ) : null}
            <Button onClick={collect} disabled={saving !== "" || tests.length === 0 || tests.every((test) => !test.testId)}>
              {saving === "collect" ? "Collecting…" : "Collect sample"}
            </Button>
          </div>
        ) : null}
      </div>

      <div className={`lab-workflow__stage ${!canCollect ? "is-current" : "is-locked"}`}>
        <div className="lab-workflow__stage-heading">
          <div>
            <span className="lab-workflow__eyebrow">Step 2</span>
            <h3>Enter result</h3>
          </div>
          <span className="lab-workflow__status">{canCollect ? "Locked" : "Ready"}</span>
        </div>
        {tests.length === 0 ? (
          <p className="lab-workflow__hint">Result fields will appear after the sample is received.</p>
        ) : (
          <>
            <p className="lab-workflow__hint">
              Choose Positive or Negative when the test offers those answers. The low and high are filled from the range for this patient's age and sex. Change them if this result should use different limits. Below the low is marked Low, and above the high is marked High. Mark Critical yourself when the result needs urgent attention. Leave a test blank if it is not needed. Only tests with a result are saved.
            </p>
            <div className="lab-workflow__table-wrap">
              <table className="lab-workflow__table">
                <thead>
                  <tr>
                    <th>Parameter</th>
                    <th>Result</th>
                    <th>Unit</th>
                    <th>Reference range</th>
                    <th>Flag</th>
                    <th>Note</th>
                  </tr>
                </thead>
                <tbody>
                  {tests.map((test, index) => {
                    const key = workflowKey(test, index);
                    const numeric = resultIsNumeric(test);
                    const editableRange = numeric || Boolean(test.referenceLow || test.referenceHigh);
                    const group = test.orderedAs || test.name;
                    const previousGroup = index > 0 ? tests[index - 1].orderedAs || tests[index - 1].name : "";
                    const groupSize = tests.filter((row) => (row.orderedAs || row.name) === group).length;
                    const showGroup = groupSize > 1 && group !== previousGroup;
                    const orderIds = [...new Set(tests.map((item) => item.orderUuid).filter(Boolean))];
                    const firstOfOrder =
                      tests.findIndex((item) => item.orderUuid && item.orderUuid === test.orderUuid) === index;
                    return (
                      <Fragment key={key}>
                      {showGroup ? (
                        <tr className="lab-workflow__group">
                          <th colSpan={6} scope="colgroup">
                            <span className="lab-workflow__name">
                              <span>{group}</span>
                              {orderIds.length > 1 && firstOfOrder && test.orderUuid ? (
                                <button
                                  type="button"
                                  className="lab-workflow__remove"
                                  aria-label={`Remove ${group}`}
                                  title={`Remove ${group}`}
                                  onClick={() => {
                                    setRemoveTarget({ orderUuid: test.orderUuid || "", name: group });
                                    setRemoveReason("");
                                  }}
                                >
                                  <span aria-hidden="true">×</span>
                                </button>
                              ) : null}
                            </span>
                          </th>
                        </tr>
                      ) : null}
                      <tr>
                        <th scope="row">
                          <span className="lab-workflow__name">
                            <span>{test.name}</span>
                            {orderIds.length > 1 && firstOfOrder && test.orderUuid && !showGroup ? (
                              <button
                                type="button"
                                className="lab-workflow__remove"
                                aria-label={`Remove ${test.orderedAs || test.name}`}
                                title={`Remove ${test.orderedAs || test.name}`}
                                onClick={() => {
                                  setRemoveTarget({ orderUuid: test.orderUuid || "", name: test.orderedAs || test.name });
                                  setRemoveReason("");
                                }}
                              >
                                <span aria-hidden="true">×</span>
                              </button>
                            ) : null}
                          </span>
                        </th>
                        <td>
                          {test.options.length > 0 ? (
                            <select
                              aria-label={`Result for ${test.name}`}
                              className={highResultFlag(flags[key]) ? "is-flag-high" : undefined}
                              value={resultValues[key] || ""}
                              disabled={canCollect}
                              onChange={(event) =>
                                setResultValues((current) => ({ ...current, [key]: event.target.value }))
                              }
                            >
                              <option value="">Select result</option>
                              {test.options.map((option) => (
                                <option key={optionValue(option)} value={optionValue(option)}>
                                  {optionLabel(option)}
                                </option>
                              ))}
                            </select>
                          ) : (
                            <textarea
                              aria-label={`Result for ${test.name}`}
                              className={highResultFlag(flags[key]) ? "is-flag-high" : undefined}
                              rows={3}
                              value={resultValues[key] || ""}
                              disabled={canCollect}
                              onChange={(event) =>
                                setResultValues((current) => ({ ...current, [key]: event.target.value }))
                              }
                            />
                          )}
                        </td>
                        <td>
                          {numeric && !test.referenceText ? (
                            <input
                              aria-label={`Unit for ${test.name}`}
                              value={units[key] || ""}
                              disabled={canCollect}
                              onChange={(event) =>
                                setUnits((current) => ({ ...current, [key]: event.target.value }))
                              }
                            />
                          ) : numeric ? (
                            <span>{test.unit || units[key] || ""}</span>
                          ) : null}
                        </td>
                        <td>
                          {editableRange ? (
                            <div className="lab-workflow__range-read">
                              <div className="lab-workflow__range-pair">
                                <input
                                  aria-label={`Low for ${test.name}`}
                                  value={rangeLows[key] ?? ""}
                                  disabled={canCollect}
                                  onChange={(event) =>
                                    setRangeLows((current) => ({ ...current, [key]: event.target.value }))
                                  }
                                />
                                <span aria-hidden="true">–</span>
                                <input
                                  aria-label={`High for ${test.name}`}
                                  value={rangeHighs[key] ?? ""}
                                  disabled={canCollect}
                                  onChange={(event) =>
                                    setRangeHighs((current) => ({ ...current, [key]: event.target.value }))
                                  }
                                />
                                {test.unit || units[key] ? <span>{test.unit || units[key]}</span> : null}
                              </div>
                              {test.referenceSource &&
                              (test.referencePublisher || test.referenceUrl || test.referenceLimitations || test.referenceMethod) ? (
                                <details>
                                  <summary>Source</summary>
                                  <p>{test.referenceSource}</p>
                                  {test.referencePublisher ? <p>{test.referencePublisher}</p> : null}
                                  {test.referenceVersion ? <p>{test.referenceVersion}</p> : null}
                                  {test.referenceMethod ? <p>{test.referenceMethod}</p> : null}
                                  {test.referenceLimitations ? <p>{test.referenceLimitations}</p> : null}
                                  {test.referenceUrl ? (
                                    <p>
                                      <a href={test.referenceUrl} target="_blank" rel="noreferrer">
                                        Source page
                                      </a>
                                    </p>
                                  ) : null}
                                </details>
                              ) : !(rangeLows[key] || rangeHighs[key]) ? (
                                <span className="lab-workflow__range-missing">
                                  {test.referenceNote || "No approved reference range."}
                                </span>
                              ) : null}
                            </div>
                          ) : (
                            <span className="lab-workflow__range-missing">
                              {test.referenceText || test.referenceNote || ""}
                            </span>
                          )}
                        </td>
                        <td>
                          {editableRange ? (
                            <select
                              aria-label={`Flag for ${test.name}`}
                              className={highResultFlag(flags[key]) ? "is-flag-high" : undefined}
                              value={flags[key] || ""}
                              disabled={canCollect}
                              onChange={(event) => setFlags((current) => ({ ...current, [key]: event.target.value }))}
                            >
                              <option value="">No flag</option>
                              <option value="L">Low</option>
                              <option value="H">High</option>
                              <option value="A">Abnormal</option>
                              <option value="C">Critical</option>
                            </select>
                          ) : null}
                        </td>
                        <td>
                          <textarea
                            aria-label={`Note for ${test.name}`}
                            rows={3}
                            value={notes[key] || ""}
                            disabled={canCollect}
                            onChange={(event) => setNotes((current) => ({ ...current, [key]: event.target.value }))}
                          />
                        </td>
                      </tr>
                      </Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </>
        )}
        {!canCollect ? (
          <Button
            variant="secondary"
            onClick={saveResults}
            disabled={saving !== "" || entered.length === 0}
          >
            {saving === "results" ? "Saving…" : "Save results"}
          </Button>
        ) : null}
      </div>

      <div className={`lab-workflow__stage ${canValidate ? "is-current" : "is-done"} ${canCollect ? "is-locked" : ""}`}>
        <div className="lab-workflow__stage-heading">
          <div>
            <span className="lab-workflow__eyebrow">Step 3</span>
            <h3>Validate result</h3>
          </div>
          <span className="lab-workflow__status">{canValidate ? "Awaiting" : "Complete"}</span>
        </div>
        <p className="lab-workflow__hint">
          {workflow.validation.validatedBy
            ? `Validated by ${workflow.validation.validatedBy}.`
            : canValidate
              ? "Accept and release to put your name on the result sheet. Printing does not add a name."
              : "Review the entered result before releasing it."}
        </p>
        {!canValidate ? null : (
          <>
            <label className="lab-workflow__decision">
              Validation decision
              <select
                value={validationDecision}
                onChange={(event) => setValidationDecision(event.target.value as "accept" | "reject")}
                disabled={saving !== ""}
              >
                <option value="accept">Accept and release</option>
                <option value="reject">Reject and return for correction</option>
              </select>
            </label>
            <Button
              onClick={validate}
              disabled={saving !== "" || canCollect || (validationDecision === "accept" && entered.length === 0)}
            >
              {saving === "validate"
                ? "Saving decision…"
                : validationDecision === "reject"
                  ? "Reject result"
                  : "Accept and release result"}
            </Button>
          </>
        )}
      </div>
      {removeTarget ? (
        <div className="abikan-dialog" role="dialog" aria-modal="true" aria-labelledby="lab-remove-test-title">
          <div className="abikan-dialog__panel cashier-confirm">
            <h2 id="lab-remove-test-title">Remove this test</h2>
            <p>{removeTarget.name} will be taken off this order.</p>
            <label>
              Why is this test being removed?
              <textarea
                value={removeReason}
                onChange={(event) => setRemoveReason(event.target.value)}
              />
            </label>
            <div className="cashier-confirm__actions">
              <Button onClick={removeOrder} disabled={saving !== "" || removeReason.trim().length < 3}>
                {saving === "remove" ? "Removing…" : "Remove test"}
              </Button>
              <Button variant="ghost" onClick={() => setRemoveTarget(null)} disabled={saving !== ""}>
                Cancel
              </Button>
            </div>
          </div>
        </div>
      ) : null}
    </Card>
  );
}
