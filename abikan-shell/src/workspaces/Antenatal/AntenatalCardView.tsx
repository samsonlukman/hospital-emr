import { useEffect, useMemo, useState } from "react";
import { Alert } from "../../components/Alert";
import { Badge } from "../../components/Badge";
import { Button } from "../../components/Button";
import { Card } from "../../components/Card";
import { LoadingState } from "../../components/LoadingState";
import { SectionHeader } from "../../components/SectionHeader";
import {
  enrollAncPatient,
  fetchAncSummary,
  recordAncVisit,
  updateAncPregnancy,
} from "../../services/antenatal";
import { PatientAccountRequestError } from "../../services/patientAccount";
import type {
  AncPatientSummary,
  AncPregnancy,
  AncPregnancyCardFields,
  AncVisitFields,
  AncVisitRecord,
} from "../../types/antenatal";
import {
  displayAncField,
  formatBloodPressure,
  formatMeasurement,
} from "./antenatalView";
import "./AntenatalCardView.css";

export interface AntenatalCardViewProps {
  patientUuid: string;
  patientName?: string;
  patientMrn?: string;
  patientDob?: string;
  openmrsVisitUuid?: string;
  canEdit?: boolean;
  /** Called whenever the antenatal summary is loaded or updated (e.g. after enroll). */
  onSummaryChange?: (summary: AncPatientSummary | null) => void;
}

type AncPanel = "card" | "visit" | "history";

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

function emptyVisitDraft(): AncVisitFields {
  return {
    visitDate: todayIso(),
    gestationalAgeWeeks: "",
    weightKg: "",
    systolic: "",
    diastolic: "",
    pulse: "",
    temperatureC: "",
    fundalHeightCm: "",
    fetalHeartRate: "",
    presentation: "",
    urinalysis: "",
    laboratoryFindings: "",
    ultrasoundFindings: "",
    supplements: "",
    vaccinations: "",
    keyFindings: "",
    treatment: "",
    nextAppointment: "",
    clinician: "",
  };
}

function cardFromPregnancy(pregnancy: AncPregnancy | null): AncPregnancyCardFields {
  const card = pregnancy?.card || {};
  return {
    gravida: card.gravida ?? "",
    para: card.para ?? "",
    abortions: card.abortions ?? "",
    livingChildren: card.livingChildren ?? "",
    previousPregnancyHistory: card.previousPregnancyHistory ?? "",
    lmp: card.lmp ?? "",
    edd: card.edd ?? "",
    gestationalAgeWeeks: card.gestationalAgeWeeks ?? "",
    previousCaesarean: card.previousCaesarean ?? "",
    significantObstetricHistory: card.significantObstetricHistory ?? "",
    bloodGroup: card.bloodGroup ?? "",
    genotype: card.genotype ?? "",
    occupation: card.occupation ?? "",
    nextOfKin: card.nextOfKin ?? "",
    nextOfKinPhone: card.nextOfKinPhone ?? "",
    bookingDate: card.bookingDate ?? "",
    gestationalAgeAtBooking: card.gestationalAgeAtBooking ?? "",
    heightCm: card.heightCm ?? "",
    notes: card.notes ?? "",
  };
}

function cleanVisitPayload(draft: AncVisitFields): AncVisitFields {
  const result: AncVisitFields = {};
  (Object.keys(draft) as (keyof AncVisitFields)[]).forEach((key) => {
    const value = draft[key];
    if (value === "" || value === undefined || value === null) {
      return;
    }
    (result as Record<string, string | number | null | undefined>)[key] = value;
  });
  return result;
}

function cleanCardPayload(draft: AncPregnancyCardFields): AncPregnancyCardFields {
  const result: AncPregnancyCardFields = {};
  (Object.keys(draft) as (keyof AncPregnancyCardFields)[]).forEach((key) => {
    const value = draft[key];
    if (value === "" || value === undefined) {
      return;
    }
    if (key === "previousCaesarean") {
      if (value === true || value === "true" || value === "yes" || value === "Yes") {
        result.previousCaesarean = true;
      } else if (value === false || value === "false" || value === "no" || value === "No") {
        result.previousCaesarean = false;
      }
      return;
    }
    (result as Record<string, string | number | boolean | null | undefined>)[key] = value as
      | string
      | number
      | boolean
      | null
      | undefined;
  });
  return result;
}

function errorMessage(reason: unknown, fallback: string): string {
  return reason instanceof PatientAccountRequestError || reason instanceof Error
    ? reason.message
    : fallback;
}

function caesareanSelectValue(value: boolean | string | null | undefined): string {
  if (value === true || value === "true" || value === "yes" || value === "Yes") {
    return "yes";
  }
  if (value === false || value === "false" || value === "no" || value === "No") {
    return "no";
  }
  return "";
}

export function AntenatalCardView({
  patientUuid,
  patientName,
  patientMrn,
  patientDob,
  openmrsVisitUuid,
  canEdit = true,
  onSummaryChange,
}: AntenatalCardViewProps) {
  const [summary, setSummary] = useState<AncPatientSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [panel, setPanel] = useState<AncPanel>("card");
  const [cardDraft, setCardDraft] = useState<AncPregnancyCardFields>(cardFromPregnancy(null));
  const [visitDraft, setVisitDraft] = useState<AncVisitFields>(emptyVisitDraft);
  const [savingCard, setSavingCard] = useState(false);
  const [savingVisit, setSavingVisit] = useState(false);
  const [startingPregnancy, setStartingPregnancy] = useState(false);

  const applySummary = (payload: AncPatientSummary | null) => {
    setSummary(payload);
    onSummaryChange?.(payload);
  };

  const active = summary?.activePregnancy || null;
  const latest = active?.latestVisit || null;
  const visits = useMemo(() => {
    const list = active?.visits || [];
    return [...list].reverse();
  }, [active]);

  const load = (keepNotice = false) => {
    setLoading(true);
    setError("");
    if (!keepNotice) {
      setNotice("");
    }
    fetchAncSummary(patientUuid)
      .then((payload) => {
        applySummary(payload);
        setCardDraft(cardFromPregnancy(payload.activePregnancy));
      })
      .catch((reason) => {
        applySummary(null);
        setError(errorMessage(reason, "Antenatal records could not be loaded."));
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
    setVisitDraft(emptyVisitDraft());
    setPanel("card");
  }, [patientUuid]);

  const setCardField = <K extends keyof AncPregnancyCardFields>(
    key: K,
    value: AncPregnancyCardFields[K],
  ) => {
    setCardDraft((current) => ({ ...current, [key]: value }));
  };

  const setVisitField = <K extends keyof AncVisitFields>(key: K, value: AncVisitFields[K]) => {
    setVisitDraft((current) => ({ ...current, [key]: value }));
  };

  const saveCard = async () => {
    if (!canEdit || savingCard || !active) {
      return;
    }
    setSavingCard(true);
    setError("");
    setNotice("");
    try {
      const response = await updateAncPregnancy(patientUuid, active.pregnancyId, cleanCardPayload(cardDraft));
      setSummary((current) => {
        const next = current
          ? {
              ...current,
              enrolled: current.enrolled || response.pregnancy.status === "active",
              hasAnc: true,
              activePregnancy:
                response.pregnancy.status === "active" ? response.pregnancy : current.activePregnancy,
              pregnancies: current.pregnancies.map((item) =>
                item.pregnancyId === response.pregnancy.pregnancyId ? response.pregnancy : item,
              ),
            }
          : current;
        onSummaryChange?.(next);
        return next;
      });
      setCardDraft(cardFromPregnancy(response.pregnancy));
      setNotice("Antenatal card saved.");
    } catch (reason) {
      setError(errorMessage(reason, "The antenatal card could not be saved."));
    } finally {
      setSavingCard(false);
    }
  };

  const saveVisit = async () => {
    if (!canEdit || savingVisit) {
      return;
    }
    setSavingVisit(true);
    setError("");
    setNotice("");
    try {
      const body = {
        ...cleanVisitPayload(visitDraft),
        pregnancyId: active?.pregnancyId,
        openmrsVisitUuid: openmrsVisitUuid || undefined,
      };
      await recordAncVisit(patientUuid, body);
      setVisitDraft(emptyVisitDraft());
      setNotice("Today's antenatal visit was recorded.");
      setPanel("history");
      load(true);
    } catch (reason) {
      setError(errorMessage(reason, "The antenatal visit could not be saved."));
    } finally {
      setSavingVisit(false);
    }
  };

  const createCard = async () => {
    if (!canEdit || startingPregnancy || active || summary?.hasAnc) {
      return;
    }
    setStartingPregnancy(true);
    setError("");
    setNotice("");
    try {
      const response = await enrollAncPatient(patientUuid, {
        bookingDate: todayIso(),
        ...cleanCardPayload(cardDraft),
      });
      const nextSummary =
        response.summary ||
        ({
          status: "ok" as const,
          hasAnc: true,
          enrolled: Boolean(response.pregnancy?.status === "active"),
          activePregnancy: response.pregnancy,
          pregnancies: [
            response.pregnancy,
            ...(summary?.pregnancies || []).filter(
              (item) => item.pregnancyId !== response.pregnancy.pregnancyId,
            ),
          ],
          defaultFeeAmount: summary?.defaultFeeAmount ?? 2000,
        } satisfies AncPatientSummary);
      applySummary(nextSummary);
      setCardDraft(cardFromPregnancy(response.pregnancy));
      setNotice(
        response.created === false
          ? response.message || "This patient already has an antenatal card."
          : response.message || "Antenatal card is ready.",
      );
      setPanel("card");
      if (response.created !== false) {
        load(true);
      }
    } catch (reason) {
      setError(errorMessage(reason, "Antenatal registration could not be started."));
    } finally {
      setStartingPregnancy(false);
    }
  };

  return (
    <div className="anc-card">
      <div className="anc-card__intro">
        <div>
          <h2 className="anc-card__title">Antenatal card</h2>
          <p className="anc-card__subtitle">
            Pregnancy enrollment for this patient. Creating the card is not an ANC visit.
          </p>
        </div>
        {active ? (
          <div className="anc-card__badges">
            <Badge tone={active.status === "active" ? "success" : "neutral"}>
              {active.status === "active" ? "Card on file" : active.status}
            </Badge>
            {active.status === "active" ? (
              <Badge tone={active.cardEnabled ? "success" : "danger"}>
                {active.cardEnabled ? "Card enabled" : "Card disabled"}
              </Badge>
            ) : null}
          </div>
        ) : null}
      </div>

      {loading ? <LoadingState variant="board" label="Loading antenatal card…" /> : null}
      {error ? (
        <Alert tone="danger" title="Antenatal card">
          {error}
        </Alert>
      ) : null}
      {notice ? (
        <Alert tone="success" title="Saved">
          {notice}
        </Alert>
      ) : null}

      {!loading ? (
        <>
          <Card className="anc-card__patient">
            <SectionHeader title="Patient" description="From the hospital record." />
            <dl className="anc-card__facts">
              <div>
                <dt>Name</dt>
                <dd>{patientName || "—"}</dd>
              </div>
              <div>
                <dt>Hospital number</dt>
                <dd>{patientMrn || "—"}</dd>
              </div>
              <div>
                <dt>Date of birth</dt>
                <dd>{patientDob || "—"}</dd>
              </div>
              <div>
                <dt>Visits recorded</dt>
                <dd>{active?.visitCount ?? 0}</dd>
              </div>
              {active?.createdAt ? (
                <div>
                  <dt>ANC card created</dt>
                  <dd>{active.createdAt.replace("T", " · ").replace(/\+00:00$/, " UTC")}</dd>
                </div>
              ) : null}
              {active?.expiresAtLabel ? (
                <div>
                  <dt>{active.cardEnabled ? "Enabled until" : "Expired"}</dt>
                  <dd>{active.expiresAtLabel}</dd>
                </div>
              ) : null}
            </dl>
          </Card>

          {active?.cardExpired ? (
            <Alert tone="warning" title="Antenatal card disabled">
              <p>
                This card expired after one year. Enable the card below. That creates a new fee.
                Collect payment at Accountant to enable it again.
              </p>
            </Alert>
          ) : null}

          {latest ? <LatestMeasurements visit={latest} /> : null}

          <nav className="anc-card__tabs" aria-label="Antenatal sections">
            <button
              type="button"
              className={panel === "card" ? "is-active" : ""}
              onClick={() => setPanel("card")}
            >
              Pregnancy card
            </button>
            <button
              type="button"
              className={panel === "visit" ? "is-active" : ""}
              onClick={() => setPanel("visit")}
              disabled={!active && !canEdit}
            >
              Today's visit
            </button>
            <button
              type="button"
              className={panel === "history" ? "is-active" : ""}
              onClick={() => setPanel("history")}
            >
              Visit history
            </button>
          </nav>

          {panel === "card" ? (
            <Card>
              <SectionHeader
                title="Obstetric information"
                description="Gravida, para, and other pregnancy details on this card."
              />
              {!summary?.hasAnc && !active ? (
                <Alert tone="info" title="Create the antenatal card">
                  Fill what you know (gravida, LMP, blood group), then choose Create antenatal card.
                  You can add more details later.
                </Alert>
              ) : null}
              <div className="anc-card__grid">
                <Field
                  label="Gravida"
                  value={String(cardDraft.gravida ?? "")}
                  onChange={(value) => setCardField("gravida", value)}
                  disabled={!canEdit}
                />
                <Field
                  label="Para"
                  value={String(cardDraft.para ?? "")}
                  onChange={(value) => setCardField("para", value)}
                  disabled={!canEdit}
                />
                <Field
                  label="Abortions"
                  value={String(cardDraft.abortions ?? "")}
                  onChange={(value) => setCardField("abortions", value)}
                  disabled={!canEdit}
                />
                <Field
                  label="Living children"
                  value={String(cardDraft.livingChildren ?? "")}
                  onChange={(value) => setCardField("livingChildren", value)}
                  disabled={!canEdit}
                />
                <Field
                  label="LMP"
                  type="date"
                  value={String(cardDraft.lmp ?? "")}
                  onChange={(value) => setCardField("lmp", value)}
                  disabled={!canEdit}
                />
                <Field
                  label="EDD"
                  type="date"
                  value={String(cardDraft.edd ?? "")}
                  onChange={(value) => setCardField("edd", value)}
                  disabled={!canEdit}
                />
                <Field
                  label="Gestational age (weeks)"
                  value={String(cardDraft.gestationalAgeWeeks ?? "")}
                  onChange={(value) => setCardField("gestationalAgeWeeks", value)}
                  disabled={!canEdit}
                />
                <label className="anc-card__field">
                  <span>Previous caesarean</span>
                  <select
                    value={caesareanSelectValue(cardDraft.previousCaesarean)}
                    disabled={!canEdit}
                    onChange={(event) =>
                      setCardField(
                        "previousCaesarean",
                        event.target.value === ""
                          ? ""
                          : event.target.value === "yes",
                      )
                    }
                  >
                    <option value="">Not recorded</option>
                    <option value="yes">Yes</option>
                    <option value="no">No</option>
                  </select>
                </label>
                <Field
                  label="Blood group"
                  value={String(cardDraft.bloodGroup ?? "")}
                  onChange={(value) => setCardField("bloodGroup", value)}
                  disabled={!canEdit}
                />
                <Field
                  label="Genotype"
                  value={String(cardDraft.genotype ?? "")}
                  onChange={(value) => setCardField("genotype", value)}
                  disabled={!canEdit}
                />
                <Field
                  label="Height (cm)"
                  value={String(cardDraft.heightCm ?? "")}
                  onChange={(value) => setCardField("heightCm", value)}
                  disabled={!canEdit}
                />
                <Field
                  label="Occupation"
                  value={String(cardDraft.occupation ?? "")}
                  onChange={(value) => setCardField("occupation", value)}
                  disabled={!canEdit}
                />
                <Field
                  label="Booking date"
                  type="date"
                  value={String(cardDraft.bookingDate ?? "")}
                  onChange={(value) => setCardField("bookingDate", value)}
                  disabled={!canEdit}
                />
                <Field
                  label="GA at booking (weeks)"
                  value={String(cardDraft.gestationalAgeAtBooking ?? "")}
                  onChange={(value) => setCardField("gestationalAgeAtBooking", value)}
                  disabled={!canEdit}
                />
                <Field
                  label="Next of kin"
                  value={String(cardDraft.nextOfKin ?? "")}
                  onChange={(value) => setCardField("nextOfKin", value)}
                  disabled={!canEdit}
                />
                <Field
                  label="Next of kin phone"
                  value={String(cardDraft.nextOfKinPhone ?? "")}
                  onChange={(value) => setCardField("nextOfKinPhone", value)}
                  disabled={!canEdit}
                />
              </div>
              <label className="anc-card__field anc-card__field--wide">
                <span>Previous pregnancy history</span>
                <textarea
                  rows={2}
                  value={String(cardDraft.previousPregnancyHistory ?? "")}
                  disabled={!canEdit}
                  onChange={(event) => setCardField("previousPregnancyHistory", event.target.value)}
                />
              </label>
              <label className="anc-card__field anc-card__field--wide">
                <span>Significant obstetric history</span>
                <textarea
                  rows={2}
                  value={String(cardDraft.significantObstetricHistory ?? "")}
                  disabled={!canEdit}
                  onChange={(event) => setCardField("significantObstetricHistory", event.target.value)}
                />
              </label>
              <label className="anc-card__field anc-card__field--wide">
                <span>Notes</span>
                <textarea
                  rows={2}
                  value={String(cardDraft.notes ?? "")}
                  disabled={!canEdit}
                  onChange={(event) => setCardField("notes", event.target.value)}
                />
              </label>
              {canEdit ? (
                <div className="anc-card__actions">
                  {!active && !summary?.hasAnc ? (
                    <Button
                      onClick={() => void createCard()}
                      busy={startingPregnancy}
                      busyLabel="Creating card…"
                    >
                      Create antenatal card
                    </Button>
                  ) : (
                    <Button onClick={() => void saveCard()} busy={savingCard} busyLabel="Saving…">
                      Save card
                    </Button>
                  )}
                </div>
              ) : null}
            </Card>
          ) : null}

          {panel === "visit" ? (
            <Card>
              <SectionHeader
                title="Record today's visit"
                description="Enter the measurements taken today. Only fill what was checked."
              />
              {!active ? (
                <Alert tone="warning" title="No antenatal card">
                  Create the antenatal card before recording a visit.
                </Alert>
              ) : (
                <>
                  <div className="anc-card__grid">
                    <Field
                      label="Visit date"
                      type="date"
                      value={String(visitDraft.visitDate ?? "")}
                      onChange={(value) => setVisitField("visitDate", value)}
                      disabled={!canEdit}
                    />
                    <Field
                      label="Gestational age (weeks)"
                      value={String(visitDraft.gestationalAgeWeeks ?? "")}
                      onChange={(value) => setVisitField("gestationalAgeWeeks", value)}
                      disabled={!canEdit}
                    />
                    <Field
                      label="Weight (kg)"
                      value={String(visitDraft.weightKg ?? "")}
                      onChange={(value) => setVisitField("weightKg", value)}
                      disabled={!canEdit}
                    />
                    <Field
                      label="Systolic"
                      value={String(visitDraft.systolic ?? "")}
                      onChange={(value) => setVisitField("systolic", value)}
                      disabled={!canEdit}
                    />
                    <Field
                      label="Diastolic"
                      value={String(visitDraft.diastolic ?? "")}
                      onChange={(value) => setVisitField("diastolic", value)}
                      disabled={!canEdit}
                    />
                    <Field
                      label="Pulse"
                      value={String(visitDraft.pulse ?? "")}
                      onChange={(value) => setVisitField("pulse", value)}
                      disabled={!canEdit}
                    />
                    <Field
                      label="Temperature (°C)"
                      value={String(visitDraft.temperatureC ?? "")}
                      onChange={(value) => setVisitField("temperatureC", value)}
                      disabled={!canEdit}
                    />
                    <Field
                      label="Fundal height (cm)"
                      value={String(visitDraft.fundalHeightCm ?? "")}
                      onChange={(value) => setVisitField("fundalHeightCm", value)}
                      disabled={!canEdit}
                    />
                    <Field
                      label="Fetal heart rate"
                      value={String(visitDraft.fetalHeartRate ?? "")}
                      onChange={(value) => setVisitField("fetalHeartRate", value)}
                      disabled={!canEdit}
                    />
                    <Field
                      label="Presentation"
                      value={String(visitDraft.presentation ?? "")}
                      onChange={(value) => setVisitField("presentation", value)}
                      disabled={!canEdit}
                    />
                    <Field
                      label="Next appointment"
                      type="date"
                      value={String(visitDraft.nextAppointment ?? "")}
                      onChange={(value) => setVisitField("nextAppointment", value)}
                      disabled={!canEdit}
                    />
                    <Field
                      label="Clinician"
                      value={String(visitDraft.clinician ?? "")}
                      onChange={(value) => setVisitField("clinician", value)}
                      disabled={!canEdit}
                    />
                  </div>
                  <div className="anc-card__grid anc-card__grid--text">
                    <label className="anc-card__field">
                      <span>Urinalysis</span>
                      <textarea
                        rows={2}
                        value={String(visitDraft.urinalysis ?? "")}
                        disabled={!canEdit}
                        onChange={(event) => setVisitField("urinalysis", event.target.value)}
                      />
                    </label>
                    <label className="anc-card__field">
                      <span>Laboratory findings</span>
                      <textarea
                        rows={2}
                        value={String(visitDraft.laboratoryFindings ?? "")}
                        disabled={!canEdit}
                        onChange={(event) => setVisitField("laboratoryFindings", event.target.value)}
                      />
                    </label>
                    <label className="anc-card__field">
                      <span>Ultrasound findings</span>
                      <textarea
                        rows={2}
                        value={String(visitDraft.ultrasoundFindings ?? "")}
                        disabled={!canEdit}
                        onChange={(event) => setVisitField("ultrasoundFindings", event.target.value)}
                      />
                    </label>
                    <label className="anc-card__field">
                      <span>Supplements</span>
                      <textarea
                        rows={2}
                        value={String(visitDraft.supplements ?? "")}
                        disabled={!canEdit}
                        onChange={(event) => setVisitField("supplements", event.target.value)}
                      />
                    </label>
                    <label className="anc-card__field">
                      <span>Vaccinations</span>
                      <textarea
                        rows={2}
                        value={String(visitDraft.vaccinations ?? "")}
                        disabled={!canEdit}
                        onChange={(event) => setVisitField("vaccinations", event.target.value)}
                      />
                    </label>
                    <label className="anc-card__field">
                      <span>Key findings</span>
                      <textarea
                        rows={2}
                        value={String(visitDraft.keyFindings ?? "")}
                        disabled={!canEdit}
                        onChange={(event) => setVisitField("keyFindings", event.target.value)}
                      />
                    </label>
                    <label className="anc-card__field anc-card__field--wide">
                      <span>Treatment</span>
                      <textarea
                        rows={2}
                        value={String(visitDraft.treatment ?? "")}
                        disabled={!canEdit}
                        onChange={(event) => setVisitField("treatment", event.target.value)}
                      />
                    </label>
                  </div>
                  {canEdit ? (
                    <div className="anc-card__actions">
                      <Button onClick={() => void saveVisit()} busy={savingVisit} busyLabel="Saving…">
                        Save today's visit
                      </Button>
                    </div>
                  ) : null}
                </>
              )}
            </Card>
          ) : null}

          {panel === "history" ? (
            <Card>
              <SectionHeader title="Visit history" description="Earlier antenatal visits on this pregnancy." />
              {visits.length === 0 ? (
                <p className="anc-card__muted">No antenatal visits recorded yet.</p>
              ) : (
                <div className="anc-card__table-wrap">
                  <table className="anc-card__table">
                    <thead>
                      <tr>
                        <th>Date</th>
                        <th>GA</th>
                        <th>Weight</th>
                        <th>BP</th>
                        <th>FH</th>
                        <th>FHR</th>
                        <th>Findings</th>
                        <th>Next visit</th>
                      </tr>
                    </thead>
                    <tbody>
                      {visits.map((visit) => (
                        <tr key={visit.visitId}>
                          <td>{displayAncField(visit.visitDate || visit.createdAt?.slice(0, 10))}</td>
                          <td>{displayAncField(visit.gestationalAgeWeeks)}</td>
                          <td>
                            {formatMeasurement(visit.weightKg)
                              ? `${formatMeasurement(visit.weightKg)} kg`
                              : "—"}
                          </td>
                          <td>{formatBloodPressure(visit.systolic, visit.diastolic)}</td>
                          <td>{displayAncField(visit.fundalHeightCm)}</td>
                          <td>{displayAncField(visit.fetalHeartRate)}</td>
                          <td>{displayAncField(visit.keyFindings)}</td>
                          <td>{displayAncField(visit.nextAppointment)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Card>
          ) : null}
        </>
      ) : null}
    </div>
  );
}

function LatestMeasurements({ visit }: { visit: AncVisitRecord }) {
  return (
    <Card className="anc-card__latest">
      <SectionHeader
        title="Latest measurements"
        description={`From ${displayAncField(visit.visitDate || visit.createdAt?.slice(0, 10))}`}
      />
      <dl className="anc-card__metrics">
        <div>
          <dt>Weight</dt>
          <dd>
            {formatMeasurement(visit.weightKg) ? `${formatMeasurement(visit.weightKg)} kg` : "—"}
          </dd>
        </div>
        <div>
          <dt>Blood pressure</dt>
          <dd>{formatBloodPressure(visit.systolic, visit.diastolic)}</dd>
        </div>
        <div>
          <dt>Fundal height</dt>
          <dd>
            {formatMeasurement(visit.fundalHeightCm)
              ? `${formatMeasurement(visit.fundalHeightCm)} cm`
              : "—"}
          </dd>
        </div>
        <div>
          <dt>Fetal heart rate</dt>
          <dd>{displayAncField(visit.fetalHeartRate)}</dd>
        </div>
        <div>
          <dt>GA (weeks)</dt>
          <dd>{displayAncField(visit.gestationalAgeWeeks)}</dd>
        </div>
        <div>
          <dt>Next appointment</dt>
          <dd>{displayAncField(visit.nextAppointment)}</dd>
        </div>
      </dl>
    </Card>
  );
}

function Field({
  label,
  value,
  onChange,
  disabled,
  type = "text",
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
  type?: string;
}) {
  return (
    <label className="anc-card__field">
      <span>{label}</span>
      <input
        type={type}
        value={value}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  );
}
