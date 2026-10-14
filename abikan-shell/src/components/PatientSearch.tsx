import { useEffect, useState } from "react";
import { BAHMNI_ROUTES, bahmniUrl } from "../config/appConfig";
import { searchPatients } from "../services/openmrs/patients";
import { fetchInpatientBoard } from "../services/inpatient";
import type { PatientSearchHit } from "../types";
import { AppIcon } from "./icons";
import "./PatientSearch.css";

interface PatientSearchProps {
  onSelect?: (patientUuid: string) => void;
  showAdmissionStatus?: boolean;
  hospitalNumberSearch?: boolean;
}

function admissionLabel(
  uuid: string,
  occupied: Map<string, string>,
  awaiting: Set<string>,
): string | null {
  const location = occupied.get(uuid);
  if (location) {
    return location;
  }
  if (awaiting.has(uuid)) {
    return "Admit requested";
  }
  return "Not admitted";
}

export function PatientSearch({
  onSelect,
  showAdmissionStatus = false,
  hospitalNumberSearch = false,
}: PatientSearchProps) {
  const stayInHospital EMR = showAdmissionStatus || hospitalNumberSearch;
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<PatientSearchHit[]>([]);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const [occupied, setOccupied] = useState<Map<string, string>>(new Map());
  const [awaiting, setAwaiting] = useState<Set<string>>(new Set());
  const [boardReady, setBoardReady] = useState(false);

  useEffect(() => {
    if (!showAdmissionStatus) {
      setBoardReady(false);
      return;
    }
    let cancelled = false;
    void fetchInpatientBoard()
      .then((board) => {
        if (cancelled) {
          return;
        }
        const nextOccupied = new Map<string, string>();
        for (const area of board.areas) {
          for (const bed of area.beds) {
            if (bed.patientUuid) {
              nextOccupied.set(bed.patientUuid, `${area.name} · ${bed.bedNumber}`);
            }
          }
        }
        setOccupied(nextOccupied);
        setAwaiting(new Set(board.awaiting.map((row) => row.patientUuid)));
        setBoardReady(true);
      })
      .catch(() => {
        if (!cancelled) {
          setBoardReady(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [showAdmissionStatus]);

  useEffect(() => {
    if (query.trim().length < 2) {
      setHits([]);
      setSearching(false);
      setSearchError(null);
      return;
    }
    setSearching(false);
    const handle = window.setTimeout(() => {
      setSearching(true);
      void searchPatients(query)
        .then((results) => {
          setHits(results);
          setSearchError(null);
          setOpen(true);
        })
        .catch((error) => {
          console.error("Patient search failed", error);
          setHits([]);
          setSearchError("Unable to search patients.");
          setOpen(true);
        })
        .finally(() => setSearching(false));
    }, 250);
    return () => window.clearTimeout(handle);
  }, [query]);

  const goToBahmniSearch = () => {
    window.location.assign(bahmniUrl(BAHMNI_ROUTES.findPatient));
  };

  return (
    <form
      className="abikan-search"
      role="search"
      onSubmit={(event) => {
        event.preventDefault();
        if (onSelect && hits[0]) {
          onSelect(hits[0].uuid);
          setOpen(false);
        } else if (!onSelect) {
          goToBahmniSearch();
        }
      }}
    >
      <label className="abikan-search__label" htmlFor="global-patient-search">
        Search patient
      </label>
      <div className="abikan-search__field">
        <span className="abikan-search__icon">
          <AppIcon name="search" size={18} />
        </span>
        <input
          id="global-patient-search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          onFocus={() => setOpen(hits.length > 0 || searching || Boolean(searchError))}
          onBlur={() => window.setTimeout(() => setOpen(false), 150)}
          placeholder={
            stayInHospital EMR
              ? "Search by name, hospital number, or phone"
              : "Search patient by name, ID or phone..."
          }
        />
      </div>
      {open && (hits.length > 0 || searching || searchError) ? (
        <ul className="abikan-search__results">
          {searching ? (
            <li className="abikan-search__status" role="status">
              Searching…
            </li>
          ) : null}
          {searchError && !searching ? (
            <li className="abikan-search__status" role="alert">
              {searchError}
            </li>
          ) : null}
          {!searching && !searchError && hits.length === 0 && query.trim().length >= 2 ? (
            <li className="abikan-search__status">No matching patient</li>
          ) : null}
          {hits.map((hit) => {
            const status =
              showAdmissionStatus && boardReady
                ? admissionLabel(hit.uuid, occupied, awaiting)
                : null;
            return (
              <li key={hit.uuid}>
                {onSelect ? (
                  <button
                    type="button"
                    onMouseDown={(event) => {
                      event.preventDefault();
                      onSelect(hit.uuid);
                      setOpen(false);
                    }}
                  >
                    <span>{hit.display}</span>
                    {status ? <small>{status}</small> : null}
                  </button>
                ) : (
                  <a href={bahmniUrl(BAHMNI_ROUTES.viewPatient(hit.uuid))}>
                    <span>{hit.display}</span>
                    {status ? <small>{status}</small> : null}
                  </a>
                )}
              </li>
            );
          })}
        </ul>
      ) : null}
    </form>
  );
}
