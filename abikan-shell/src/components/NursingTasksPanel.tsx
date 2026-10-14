import { useEffect, useState, type MouseEvent } from "react";
import { ClinicalSection } from "./ClinicalSection";
import { EmptyState } from "./EmptyState";
import { fetchMar, fetchNursingNotes, fetchVitals } from "../services/inpatient";
import type { InpatientStay } from "../types/inpatient";
import { nursingTasksFromState, stayIsOccupied, stayNeedsBed } from "../workspaces/Nursing/nursingTasks";
import "./NursingTasksPanel.css";

interface Props {
  patientUuid: string;
  stay: InpatientStay | null;
}

export function NursingTasksPanel({ patientUuid, stay }: Props) {
  const [tasks, setTasks] = useState(nursingTasksFromState({
    stay,
    admissionEncounterUuid: "",
    vitals: [],
    notes: [],
    mar: null,
  }));
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    if (!stay) {
      setTasks([]);
      setLoading(false);
      return;
    }
    if (!stayIsOccupied(stay) && !stayNeedsBed(stay)) {
      setTasks([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    Promise.allSettled([
      fetchVitals(patientUuid),
      fetchNursingNotes(patientUuid),
      fetchMar(patientUuid),
    ]).then(([vitals, notes, mar]) => {
      if (cancelled) {
        return;
      }
      const vitalsValue = vitals.status === "fulfilled" ? vitals.value : null;
      const notesValue = notes.status === "fulfilled" ? notes.value : null;
      const marValue = mar.status === "fulfilled" ? mar.value : null;
      setTasks(
        nursingTasksFromState({
          stay,
          admissionEncounterUuid:
            notesValue?.activeAdmissionEncounterUuid ||
            vitalsValue?.admissionEncounterUuid ||
            marValue?.admissionEncounterUuid ||
            "",
          vitals: vitalsValue?.readings || [],
          notes: notesValue?.notes || [],
          mar: marValue,
        }),
      );
      setLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, [patientUuid, stay]);

  const openSection = (event: MouseEvent<HTMLAnchorElement>) => {
    event.preventDefault();
    const target = event.currentTarget.getAttribute("href")?.slice(1);
    if (target) {
      document.getElementById(target)?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  };

  return (
    <ClinicalSection
      id="tasks"
      title="Nursing tasks"
      description="These come from this admission: a bed still to assign, first vitals, a due scheduled dose, a dose outside the window, or the first nursing note. Completing the work in that section clears the task."
    >
      {loading ? (
        <p className="nursing-tasks__muted">Checking the ward record…</p>
      ) : tasks.length === 0 ? (
        <EmptyState
          title="No nursing tasks waiting"
          description={
            stayIsOccupied(stay)
              ? "First vitals, the first nursing note, and any due scheduled doses for this admission are complete. Later vitals, notes, and medicines still belong in their own sections."
              : stayNeedsBed(stay)
                ? "Assign a bed in Admission to continue ward work."
                : "Ward tasks appear after the patient is admitted."
          }
        />
      ) : (
        <ul className="nursing-tasks">
          {tasks.map((task) => (
            <li key={task.id}>
              <a href={task.href} onClick={openSection}>
                <strong>{task.title}</strong>
                <span>{task.detail}</span>
                <span>{task.action}</span>
              </a>
            </li>
          ))}
        </ul>
      )}
    </ClinicalSection>
  );
}
