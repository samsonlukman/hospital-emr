import { useState } from "react";
import {
  RADIOGRAPHY_GROUP,
  ULTRASOUND_GROUP,
  findRadiologyService,
  radiologyMenuByGroup,
  resolveRadiologyOrderConcept,
  type RadiologyMenuGroup,
} from "../config/radiologyMenu";
import { PatientAccountRequestError } from "../services/patientAccount";
import { createRadiologyOrders, newRadiologyRequestId } from "../services/radiologyBilling";
import { VISIT_NOT_STARTED_MESSAGE, visitHasStarted } from "../services/openmrs/visitWindow";
import { Alert } from "./Alert";
import { Button } from "./Button";
import "./RadiologyOrderPanel.css";

interface RadiologyOrderPanelProps {
  patientUuid: string;
  visitUuid?: string;
  visitStartDatetime?: string;
  encounterUuid?: string;
  locationUuid: string;
  canEdit: boolean;
  blockedReason?: string;
  onSaved: (encounterUuid?: string) => void;
}

export function RadiologyOrderPanel({
  patientUuid,
  visitUuid,
  visitStartDatetime,
  encounterUuid,
  locationUuid,
  canEdit,
  blockedReason = "Start an open visit before ordering imaging.",
  onSaved,
}: RadiologyOrderPanelProps) {
  const [group, setGroup] = useState<RadiologyMenuGroup | "">("");
  const [serviceId, setServiceId] = useState("");
  const [optionId, setOptionId] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const services = group ? radiologyMenuByGroup(group) : [];
  const selected = findRadiologyService(serviceId);
  const concept = resolveRadiologyOrderConcept(selected, optionId);
  const orderable = Boolean(visitUuid && concept);

  const submit = async () => {
    if (!visitUuid || !selected || !concept || submitting) {
      return;
    }
    if (!visitHasStarted(visitStartDatetime)) {
      setError(VISIT_NOT_STARTED_MESSAGE);
      return;
    }
    setSubmitting(true);
    setError("");
    setMessage("");
    try {
      const saved = await createRadiologyOrders(patientUuid, {
        visitUuid,
        locationUuid,
        encounterUuid,
        requestId: newRadiologyRequestId(),
        services: [{ serviceId: selected.id, conceptUuid: concept.conceptUuid }],
      });
      setServiceId("");
      setOptionId("");
      setMessage(saved.message || "Radiology order created.");
      onSaved(saved.encounterUuid);
    } catch (reason) {
      setError(
        reason instanceof PatientAccountRequestError
          ? reason.message
          : "The imaging order could not be saved.",
      );
    } finally {
      setSubmitting(false);
    }
  };

  if (!canEdit) {
    return (
      <p className="rad-order-panel__hint">{blockedReason}</p>
    );
  }

  return (
    <div className="rad-order-panel">
      <div className="rad-order-panel__fields">
        <label htmlFor="rad-order-group">Imaging group</label>
        <select
          id="rad-order-group"
          value={group}
          onChange={(event) => {
            setGroup(event.target.value as RadiologyMenuGroup | "");
            setServiceId("");
            setOptionId("");
            setMessage("");
            setError("");
          }}
        >
          <option value="">Choose</option>
          <option value={ULTRASOUND_GROUP}>{ULTRASOUND_GROUP}</option>
          <option value={RADIOGRAPHY_GROUP}>{RADIOGRAPHY_GROUP}</option>
        </select>
      </div>

      {group ? (
        <div className="rad-order-panel__fields">
          <label htmlFor="rad-order-service">Examination</label>
          <select
            id="rad-order-service"
            value={serviceId}
            onChange={(event) => {
              setServiceId(event.target.value);
              setOptionId("");
              setMessage("");
              setError("");
            }}
          >
            <option value="">Choose</option>
            {services.map((service) => (
              <option key={service.id} value={service.id}>
                {service.hospitalName}
              </option>
            ))}
          </select>
        </div>
      ) : null}

      {selected?.options?.length ? (
        <div className="rad-order-panel__fields">
          <label htmlFor="rad-order-option">{selected.optionPrompt || "Details"}</label>
          <select
            id="rad-order-option"
            value={optionId}
            onChange={(event) => {
              setOptionId(event.target.value);
              setMessage("");
              setError("");
            }}
          >
            <option value="">Choose</option>
            {selected.options.map((option) => (
              <option key={option.id} value={option.id}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
      ) : null}

      <p className="rad-order-panel__hint">
        This creates the imaging request. Radiology sets the fee. Payment is collected at Accounts.
      </p>

      {error ? (
        <Alert tone="danger" title="Could not save the imaging order">
          <p>{error}</p>
        </Alert>
      ) : null}
      {message ? (
        <Alert tone="success" title="Radiology order created">
          <p>{message}</p>
        </Alert>
      ) : null}

      <Button
        onClick={() => void submit()}
        busy={submitting}
        busyLabel="Saving order…"
        disabled={!orderable}
      >
        Submit imaging order
      </Button>
    </div>
  );
}
