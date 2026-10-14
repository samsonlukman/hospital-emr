import { useEffect, useRef, useState } from "react";
import { Alert } from "./Alert";
import { Badge } from "./Badge";
import { Button } from "./Button";
import { PatientAccountRequestError } from "../services/patientAccount";
import {
  createLaboratoryOrders,
  fetchLaboratoryCatalogue,
  newLaboratoryRequestId,
} from "../services/laboratoryBilling";
import { VISIT_NOT_STARTED_MESSAGE, visitHasStarted } from "../services/openmrs/visitWindow";
import type { LaboratoryCatalogueTest, LaboratoryOrderDraftItem } from "../types/laboratoryCatalogue";
import { canSelectLabTest, labCatalogueHitDetails } from "../workspaces/Laboratory/laboratoryView";
import "./LabOrderPanel.css";

interface LabOrderPanelProps {
  patientUuid: string;
  visitUuid?: string;
  visitStartDatetime?: string;
  encounterUuid?: string;
  locationUuid: string;
  canEdit: boolean;
  blockedReason?: string;
  onSaved: (encounterUuid?: string) => void;
}

function addTest(
  draft: LaboratoryOrderDraftItem[],
  test: LaboratoryCatalogueTest,
): LaboratoryOrderDraftItem[] {
  if (!test.conceptUuid || draft.some((item) => item.conceptUuid === test.conceptUuid)) {
    return draft;
  }
  return [
    ...draft,
    {
      conceptUuid: test.conceptUuid,
      name: test.name,
      type: test.type,
      specimen: test.specimen,
      price: test.price,
      outsourced: test.outsourced,
    },
  ];
}

function addUnlistedTest(
  draft: LaboratoryOrderDraftItem[],
  name: string,
): LaboratoryOrderDraftItem[] {
  const trimmed = name.trim();
  if (
    !trimmed ||
    draft.some((item) => item.unlisted && item.name.toLowerCase() === trimmed.toLowerCase())
  ) {
    return draft;
  }
  return [
    ...draft,
    {
      conceptUuid: "__unlisted__",
      name: trimmed,
      unlisted: true,
      price: null,
      outsourced: false,
    },
  ];
}

export function LabOrderPanel({
  patientUuid,
  visitUuid,
  visitStartDatetime,
  encounterUuid,
  locationUuid,
  canEdit,
  blockedReason = "Start an open visit before ordering laboratory tests.",
  onSaved,
}: LabOrderPanelProps) {
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<LaboratoryCatalogueTest[]>([]);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState("");
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<LaboratoryOrderDraftItem[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const boxRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    const needle = query.trim();
    if (needle.length < 2) {
      setHits([]);
      setSearching(false);
      setSearchError("");
      return;
    }
    setSearching(true);
    const timer = window.setTimeout(() => {
      fetchLaboratoryCatalogue(needle)
        .then((payload) => {
          if (cancelled) {
            return;
          }
          setHits(payload.tests.filter(canSelectLabTest));
          setSearchError("");
        })
        .catch(() => {
          if (!cancelled) {
            setHits([]);
            setSearchError("Laboratory tests could not be loaded.");
          }
        })
        .finally(() => {
          if (!cancelled) {
            setSearching(false);
          }
        });
    }, 220);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [query]);

  useEffect(() => {
    const onPointer = (event: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", onPointer);
    return () => document.removeEventListener("mousedown", onPointer);
  }, []);

  const submit = async () => {
    if (!visitUuid || draft.length === 0 || submitting) {
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
      const saved = await createLaboratoryOrders(patientUuid, {
        visitUuid,
        locationUuid,
        encounterUuid,
        requestId: newLaboratoryRequestId(),
        tests: draft.map((item) => ({
          conceptUuid: item.conceptUuid,
          name: item.name,
          unlisted: item.unlisted,
        })),
      });
      setDraft([]);
      setQuery("");
      setMessage(
        saved.message || "Laboratory order saved. The laboratory submits the bill.",
      );
      onSaved(saved.encounterUuid);
    } catch (reason) {
      setError(
        reason instanceof PatientAccountRequestError
          ? reason.message
          : "The laboratory order could not be saved.",
      );
    } finally {
      setSubmitting(false);
    }
  };

  if (!canEdit) {
    return (
      <p className="lab-order-panel__hint">{blockedReason}</p>
    );
  }

  return (
    <div className="lab-order-panel">
      <div className="lab-order-panel__composer" ref={boxRef}>
        <label className="lab-order-panel__search-label" htmlFor="lab-order-search">
          Add Laboratory Test
        </label>
        <input
          id="lab-order-search"
          type="search"
          value={query}
          placeholder="Search tests..."
          autoComplete="off"
          onFocus={() => setOpen(true)}
          onChange={(event) => {
            setQuery(event.target.value);
            setOpen(true);
          }}
        />
        {searching ? <p className="lab-order-panel__status">Searching…</p> : null}
        {searchError ? <p className="lab-order-panel__status is-error">{searchError}</p> : null}
        {open ? (
          <ul className="lab-order-panel__hits">
            {query.trim().length < 2 ? (
              <li className="lab-order-panel__empty">
                Type at least 2 letters to search the hospital laboratory catalogue.
              </li>
            ) : hits.length === 0 && !searching ? (
              <>
                <li className="lab-order-panel__empty">
                  No matching hospital test in the catalogue.
                </li>
                <li>
                  <button
                    type="button"
                    onClick={() => {
                      setDraft((current) => addUnlistedTest(current, query));
                      setQuery("");
                      setOpen(false);
                    }}
                  >
                    <strong>Request “{query.trim()}” as an unlisted test</strong>
                    <span>The laboratory will review it before processing. No fee is created yet.</span>
                  </button>
                </li>
              </>
            ) : (
              hits.slice(0, 12).map((hit) => (
                <li key={hit.conceptUuid || hit.id}>
                  <button
                    type="button"
                    onClick={() => {
                      setDraft((current) => addTest(current, hit));
                    }}
                  >
                    <strong>{hit.name}</strong>
                    <span>
                      {draft.some((item) => item.conceptUuid === hit.conceptUuid)
                        ? "Added to this order"
                        : labCatalogueHitDetails(hit)}
                    </span>
                  </button>
                </li>
              ))
            )}
          </ul>
        ) : null}
      </div>

      {draft.length > 0 ? (
        <>
        <p className="lab-order-panel__hint">
          {draft.length === 1 ? "1 test on this order" : `${draft.length} tests on this order`}
        </p>
        <ul className="lab-order-panel__draft">
          {draft.map((item) => (
            <li key={item.unlisted ? `${item.conceptUuid}:${item.name}` : item.conceptUuid}>
              <div>
                <strong>{item.name}</strong>
                <span>
                  {item.unlisted ? "Pending laboratory review" : item.price?.formatted || "Price not set"}
                  {item.outsourced ? " · Outsourced" : ""}
                </span>
              </div>
              {item.unlisted ? <Badge tone="warning">Unlisted</Badge> : null}
              {item.outsourced ? <Badge tone="warning">Outsourced</Badge> : null}
              <button
                type="button"
                className="lab-order-panel__remove"
                onClick={() =>
                  setDraft((current) =>
                    current.filter((row) =>
                      item.unlisted
                        ? !(row.unlisted && row.name === item.name)
                        : row.conceptUuid !== item.conceptUuid,
                    ),
                  )
                }
              >
                Remove
              </button>
            </li>
          ))}
        </ul>
        </>
      ) : (
        <p className="lab-order-panel__hint">Search and add one or more tests, then submit the order.</p>
      )}

      <p className="lab-order-panel__hint">
        Catalogue tests send a fee to Accounts. Unlisted tests are sent for laboratory review without a fee.
      </p>

      {error ? (
        <Alert tone="danger" title="Could not save the laboratory order">
          <p>{error}</p>
        </Alert>
      ) : null}
      {message ? (
        <Alert tone="success" title="Laboratory order saved">
          <p>{message}</p>
        </Alert>
      ) : null}

      <Button
        onClick={() => void submit()}
        busy={submitting}
        busyLabel="Saving order…"
        disabled={draft.length === 0}
      >
        {draft.length > 1 ? `Send ${draft.length} tests` : "Send test"}
      </Button>
    </div>
  );
}
