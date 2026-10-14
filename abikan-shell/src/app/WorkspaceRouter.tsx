import { useEffect } from "react";
import { AppShell } from "../layouts/AppShell";
import { navGroupsForWorkplace } from "../config/departmentNav";
import { canOpenAccommodationSettings, canOpenAccountant, canOpenAdministration, canOpenDoctor, canOpenHmo, canOpenLaboratory, canOpenNursing, canOpenPatientAccount, canOpenPharmacy, canOpenRadiology, canOpenRegistration, hasAnyHospital EMRWorkplace } from "../config/workspaceMap";
import type { WorkspaceContext, WorkspaceId } from "../types";
import { resolveDefaultWorkplace, resolveRouteForUser, workplaceFromRoute, workplaceLabel, type WorkplaceId } from "../config/workplaces";
import { AccessDeniedWorkspace } from "../workspaces/AccessDenied/AccessDeniedWorkspace";
import { PageUnavailableWorkspace } from "../workspaces/AccessDenied/PageUnavailableWorkspace";
import { ClinicalHomeWorkspace } from "../workspaces/ClinicalHome/ClinicalHomeWorkspace";
import { ComingSoonWorkspace } from "../workspaces/ComingSoon/ComingSoonWorkspace";
import { ConsultationWorkspace } from "../workspaces/Doctor/ConsultationWorkspace";
import { DoctorWorkspace } from "../workspaces/Doctor/DoctorWorkspace";
import { LaboratoryExternalPatientView } from "../workspaces/Laboratory/LaboratoryExternalPatientView";
import { LaboratoryOrderWorkspace } from "../workspaces/Laboratory/LaboratoryOrderWorkspace";
import { LaboratoryPatientWorkspace } from "../workspaces/Laboratory/LaboratoryPatientWorkspace";
import { LaboratoryWorkspace } from "../workspaces/Laboratory/LaboratoryWorkspace";
import { RadiologyOrderWorkspace } from "../workspaces/Radiology/RadiologyOrderWorkspace";
import { RadiologyExternalStudyView } from "../workspaces/Radiology/RadiologyExternalStudyView";
import { RadiologyPatientWorkspace } from "../workspaces/Radiology/RadiologyPatientWorkspace";
import { RadiologyWorkspace } from "../workspaces/Radiology/RadiologyWorkspace";
import { PharmacyPrescriptionWorkspace } from "../workspaces/Pharmacy/PharmacyPrescriptionWorkspace";
import { PharmacyPatientWorkspace } from "../workspaces/Pharmacy/PharmacyPatientWorkspace";
import { PharmacyWorkspace } from "../workspaces/Pharmacy/PharmacyWorkspace";
import { AccountantPatientWorkspace } from "../workspaces/Accountant/AccountantPatientWorkspace";
import { AccountantWorkspace } from "../workspaces/Accountant/AccountantWorkspace";
import { PatientAccountInvoiceWorkspace } from "../workspaces/PatientAccount/PatientAccountInvoiceWorkspace";
import { PatientAccountWorkspace } from "../workspaces/PatientAccount/PatientAccountWorkspace";
import { NursingPatientWorkspace } from "../workspaces/Nursing/NursingPatientWorkspace";
import { NursingTreatmentVisitWorkspace } from "../workspaces/Nursing/NursingTreatmentVisitWorkspace";
import { NursingWorkspace } from "../workspaces/Nursing/NursingWorkspace";
import { RegistrationDeskWorkspace } from "../workspaces/RegistrationDesk/RegistrationDeskWorkspace";
import { CreateVisitWorkspace } from "../workspaces/RegistrationDesk/CreateVisitWorkspace";
import { AntenatalRegistrationWorkspace } from "../workspaces/RegistrationDesk/AntenatalRegistrationWorkspace";
import { RegistrationPatientWorkspace } from "../workspaces/RegistrationDesk/RegistrationPatientWorkspace";
import { RegisterPatientWorkspace } from "../workspaces/RegistrationDesk/RegisterPatientWorkspace";
import { FamilyListWorkspace } from "../workspaces/RegistrationDesk/FamilyListWorkspace";
import { FamilyDetailWorkspace } from "../workspaces/RegistrationDesk/FamilyDetailWorkspace";
import { AccommodationSettingsWorkspace } from "../workspaces/Accommodation/AccommodationSettingsWorkspace";
import { DepartmentAccessWorkspace } from "../workspaces/Admin/DepartmentAccessWorkspace";
import { StaffAccountsWorkspace } from "../workspaces/Admin/StaffAccountsWorkspace";
import { AdminAnalyticsWorkspace } from "../workspaces/Admin/AdminAnalyticsWorkspace";
import { AdminAuditWorkspace } from "../workspaces/Admin/AdminAuditWorkspace";
import { AdminExportWorkspace } from "../workspaces/Admin/AdminExportWorkspace";
import { AdminStaffLogWorkspace } from "../workspaces/Admin/AdminStaffLogWorkspace";
import { AdminCertificatesWorkspace } from "../workspaces/Admin/AdminCertificatesWorkspace";
import { AdminHmoBillsWorkspace } from "../workspaces/Admin/AdminHmoBillsWorkspace";
import { PatientDirectoryWorkspace } from "../workspaces/PatientDirectory/PatientDirectoryWorkspace";
import { PatientRecordWorkspace } from "../workspaces/PatientDirectory/PatientRecordWorkspace";
import { MessagesWorkspace } from "../workspaces/Messages/MessagesWorkspace";
import { SystemSettingsWorkspace } from "../workspaces/SystemSettings/SystemSettingsWorkspace";
import { HmoWorkspace } from "../workspaces/Hmo/HmoWorkspace";
import {
  openConsultation,
  openLaboratoryPatient,
  openNursingPatient,
  openRadiologyPatient,
  openAccountantPatient,
  openPatientAccount,
  openPharmacyPatient,
  openPatientRecord,
  readConsultationPatientUuid,
  readConsultationVisitUuid,
  readLaboratoryExternalId,
  readLaboratoryOrderUuid,
  readLaboratoryOrderExpectedIdentity,
  readLaboratoryPatientUuid,
  readNursingPatientUuid,
  readRadiologyOrderExpectedIdentity,
  readRadiologyOrderUuid,
  readRadiologyExternalStudyId,
  readRadiologyPatientUuid,
  readAccountantPatientUuid,
  readPatientAccountInvoiceId,
  readPatientAccountUuid,
  readPatientAccountVisitUuid,
  readPharmacyPatientUuid,
  readPharmacyPrescriptionUuid,
  readCreateVisitPatientUuid,
  readAntenatalPatientUuid,
  readRegistrationEditUuid,
  readRegistrationPatientUuid,
  readReceptionFamilyId,
  readPatientRecordUuid,
  readHashSection,
  readHashNavItemId,
  readNursingTreatmentVisitUuid,
  type ShellRoute,
} from "./hashRoute";

interface WorkspaceRouterProps {
  context: WorkspaceContext;
  workspaceId: WorkspaceId;
  route: ShellRoute;
  hash: string;
  onWorkplaceChange: (workplaceId: WorkplaceId) => void;
  onSignOut: () => void;
}

export function WorkspaceRouter({
  context,
  route: requestedRoute,
  hash,
  onWorkplaceChange,
  onSignOut,
}: WorkspaceRouterProps) {
  const route = resolveRouteForUser(requestedRoute, context);
  const section = readHashSection();
  const navItemId = readHashNavItemId();
  const showUnavailable = requestedRoute === "unavailable" && route === "unavailable";

  useEffect(() => {
    if (!section) {
      return;
    }
    const frame = window.requestAnimationFrame(() => {
      document.getElementById(section)?.scrollIntoView({ block: "start" });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [route, section, hash]);
  const patientUuid = readConsultationPatientUuid();
  const selectedVisitUuid = readConsultationVisitUuid();
  const nursingPatientUuid = readNursingPatientUuid();
  const nursingTreatmentVisitUuid = readNursingTreatmentVisitUuid();
  const laboratoryPatientUuid = readLaboratoryPatientUuid();
  const laboratoryOrderUuid = readLaboratoryOrderUuid();
  const laboratoryOrderExpected = readLaboratoryOrderExpectedIdentity();
  const laboratoryExternalId = readLaboratoryExternalId();
  const radiologyPatientUuid = readRadiologyPatientUuid();
  const radiologyOrderUuid = readRadiologyOrderUuid();
  const radiologyOrderExpected = readRadiologyOrderExpectedIdentity();
  const radiologyExternalStudyId = readRadiologyExternalStudyId();
  const pharmacyPatientUuid = readPharmacyPatientUuid();
  const pharmacyPrescriptionUuid = readPharmacyPrescriptionUuid();
  const patientAccountUuid = readPatientAccountUuid();
  const patientAccountVisitUuid = readPatientAccountVisitUuid();
  const patientAccountInvoiceId = readPatientAccountInvoiceId();
  const accountantPatientUuid = readAccountantPatientUuid();
  const registrationPatientUuid = readRegistrationPatientUuid();
  const patientRecordUuid = readPatientRecordUuid();
  const registrationEditUuid = readRegistrationEditUuid();
  const receptionFamilyId = readReceptionFamilyId();
  const createVisitPatientUuid = readCreateVisitPatientUuid();
  const antenatalPatientUuid = readAntenatalPatientUuid();
  const doctorAllowed = canOpenDoctor(context);
  const nursingAllowed = canOpenNursing(context);
  const laboratoryAllowed = canOpenLaboratory(context);
  const radiologyAllowed = canOpenRadiology(context);
  const pharmacyAllowed = canOpenPharmacy(context);
  const registrationAllowed = canOpenRegistration(context);
  const patientAccountAllowed = canOpenPatientAccount(context);
  const accountantAllowed = canOpenAccountant(context);
  const administrationAllowed = canOpenAdministration(context);
  const hmoAllowed = canOpenHmo(context);
  const messagingAllowed = hasAnyHospital EMRWorkplace(context);
  const accommodationSettingsAllowed = canOpenAccommodationSettings(context);
  const labRoute =
    route === "laboratory" ||
    route === "laboratory-patient" ||
    route === "laboratory-order" ||
    route === "laboratory-external";
  const radRoute =
    route === "radiology" ||
    route === "radiology-patient" ||
    route === "radiology-order" ||
    route === "radiology-external";
  const pharmRoute =
    route === "pharmacy" ||
    route === "pharmacy-patient" ||
    route === "pharmacy-prescription";
  const accountRoute = route === "patient-account" || route === "patient-account-invoice";
  const accountantRoute = route === "accountant" || route === "accountant-patient";
  const showDesk = route === "registration-desk" && registrationAllowed;
  const showRegistrationPatient =
    route === "registration-patient" && registrationAllowed && !!registrationPatientUuid;
  const showRegistrationRegister = route === "registration-register" && registrationAllowed;
  const showAntenatalPatientRegister =
    route === "registration-antenatal-register" && registrationAllowed;
  const showCreateVisit = route === "registration-visit" && registrationAllowed;
  const showAntenatalRegistration = route === "registration-antenatal" && registrationAllowed;
  const showReceptionPatients = route === "registration-patients" && registrationAllowed;
  const showReceptionFamilies = route === "registration-families" && registrationAllowed;
  const showReceptionFamily =
    route === "registration-family" && registrationAllowed && !!receptionFamilyId;
  const showAdminPatients = route === "admin-patients" && administrationAllowed;
  const showReceptionPatientRecord =
    route === "registration-patient-record" && registrationAllowed && !!patientRecordUuid;
  const showAdminPatientRecord =
    route === "admin-patient-record" && administrationAllowed && !!patientRecordUuid;
  const showDoctor = (route === "doctor" || route === "consultation") && doctorAllowed;
  const showNursing = (route === "nursing" || route === "nursing-patient") && nursingAllowed;
  const showLaboratory = labRoute && laboratoryAllowed;
  const showRadiology = radRoute && radiologyAllowed;
  const showPharmacy = pharmRoute && pharmacyAllowed;
  const showPatientAccount = accountRoute && patientAccountAllowed && !!patientAccountUuid;
  const showAccountant = accountantRoute && accountantAllowed;
  const showHmo = route === "hmo" && hmoAllowed;
  const showAccommodationSettings =
    route === "accommodation-settings" && accommodationSettingsAllowed;
  const showMessageCalls = route === "messages" && messagingAllowed && section === "call";
  const showMessages = route === "messages" && messagingAllowed && !showMessageCalls;
  const showSystemSettings = route === "system-settings" && messagingAllowed;
  const showStaffAccounts = route === "staff-accounts" && administrationAllowed;
  const showDepartmentAccess = route === "department-access" && administrationAllowed;
  const showAdminAnalytics = route === "admin-analytics" && administrationAllowed;
  const showAdminAudit = route === "admin-audit" && administrationAllowed;
  const showAdminExport = route === "admin-export" && administrationAllowed;
  const showAdminLog = route === "admin-log" && administrationAllowed;
  const showAdminHmoBills = route === "admin-hmo-bills" && administrationAllowed;
  const showAdminCertificates = route === "admin-certificates" && administrationAllowed;
  const showDoctorDenied = (route === "doctor" || route === "consultation") && !doctorAllowed;
  const showNursingDenied = (route === "nursing" || route === "nursing-patient") && !nursingAllowed;
  const showLaboratoryDenied = labRoute && !laboratoryAllowed;
  const showRadiologyDenied = radRoute && !radiologyAllowed;
  const showPharmacyDenied = pharmRoute && !pharmacyAllowed;
  const showRegistrationDenied =
    (route === "registration-desk" ||
      route === "registration-patient" ||
      route === "registration-register" ||
      route === "registration-visit" ||
      route === "registration-antenatal" ||
      route === "registration-antenatal-register" ||
      route === "registration-patients" ||
      route === "registration-patient-record" ||
      route === "registration-families" ||
      route === "registration-family") &&
    !registrationAllowed;
  const showPatientAccountDenied = accountRoute && !patientAccountAllowed;
  const showAccountantDenied = accountantRoute && !accountantAllowed;
  const showHmoDenied = route === "hmo" && !hmoAllowed;
  const showAccommodationSettingsDenied =
    route === "accommodation-settings" && !accommodationSettingsAllowed;
  const showMessagesDenied = route === "messages" && !messagingAllowed;
  const showSystemSettingsDenied = route === "system-settings" && !messagingAllowed;
  const showStaffAccountsDenied = route === "staff-accounts" && !administrationAllowed;
  const showDepartmentAccessDenied = route === "department-access" && !administrationAllowed;
  const showAdminAnalyticsDenied = route === "admin-analytics" && !administrationAllowed;
  const showAdminAuditDenied = route === "admin-audit" && !administrationAllowed;
  const showAdminExportDenied = route === "admin-export" && !administrationAllowed;
  const showAdminLogDenied = route === "admin-log" && !administrationAllowed;
  const showAdminHmoBillsDenied = route === "admin-hmo-bills" && !administrationAllowed;
  const showAdminCertificatesDenied = route === "admin-certificates" && !administrationAllowed;
  const showAdminPatientsDenied = route === "admin-patients" && !administrationAllowed;
  const showAdminPatientRecordDenied = route === "admin-patient-record" && !administrationAllowed;
  const showDenied =
    showDoctorDenied ||
    showNursingDenied ||
    showLaboratoryDenied ||
    showRadiologyDenied ||
    showPharmacyDenied ||
    showRegistrationDenied ||
    showPatientAccountDenied ||
    showAccountantDenied ||
    showHmoDenied ||
    showStaffAccountsDenied ||
    showDepartmentAccessDenied ||
    showAdminAnalyticsDenied ||
    showAdminAuditDenied ||
    showAdminExportDenied ||
    showAdminLogDenied ||
    showAdminHmoBillsDenied ||
    showAdminCertificatesDenied ||
    showAdminPatientsDenied ||
    showAdminPatientRecordDenied ||
    showAccommodationSettingsDenied ||
    showMessagesDenied ||
    showSystemSettingsDenied;
  const showComingSoon = route === "workspace";
  const showConsultation = showDoctor && route === "consultation" && patientUuid;
  const showNursingPatient = showNursing && route === "nursing-patient" && nursingPatientUuid;
  const showLaboratoryPatient =
    showLaboratory && route === "laboratory-patient" && laboratoryPatientUuid;
  const showLaboratoryOrder =
    showLaboratory && route === "laboratory-order" && laboratoryOrderUuid;
  const showLaboratoryExternal =
    showLaboratory && route === "laboratory-external" && laboratoryExternalId;
  const showRadiologyPatient =
    showRadiology && route === "radiology-patient" && radiologyPatientUuid;
  const showRadiologyOrder =
    showRadiology && route === "radiology-order" && radiologyOrderUuid;
  const showRadiologyExternal =
    showRadiology && route === "radiology-external" && radiologyExternalStudyId;
  const showPharmacyPatient =
    showPharmacy && route === "pharmacy-patient" && pharmacyPatientUuid;
  const showPharmacyPrescription =
    showPharmacy && route === "pharmacy-prescription" && pharmacyPrescriptionUuid;

  const currentWorkplaceId = showDenied
    ? resolveDefaultWorkplace(context).id
    : workplaceFromRoute(route) ?? resolveDefaultWorkplace(context).id;
  const departmentLabel = showDenied
    ? resolveDefaultWorkplace(context).label
    : workplaceLabel(context, route);
  const navGroups = navGroupsForWorkplace(currentWorkplaceId);

  const fallbackActiveId = showAccommodationSettings
    ? "accommodation-settings"
    : showStaffAccounts
      ? "users"
      : showDepartmentAccess
        ? "access"
    : showAdminAnalytics
      ? "admin-analytics"
    : showAdminAudit
      ? "admin-audit"
    : showAdminExport
      ? "admin-export"
    : showAdminLog
      ? "admin-log"
    : showAdminHmoBills
      ? "admin-hmo-bills"
    : showAdminCertificates
      ? "admin-certificates"
    : showMessages
      ? "messages"
    : showSystemSettings
      ? "system-settings"
    : showAdminPatients || showAdminPatientRecord
      ? "admin-patients"
    : showReceptionPatients || showReceptionPatientRecord
      ? "patients"
    : showReceptionFamilies || showReceptionFamily
      ? "families"
    : showPatientAccount
      ? currentWorkplaceId === "registration"
        ? "patient-accounts"
        : currentWorkplaceId === "accountant"
          ? "search"
          : "admin-dashboard"
    : showDesk
      ? "home"
      : showRegistrationRegister
        ? "register"
      : showCreateVisit
        ? "create-visit"
      : showAntenatalRegistration || showAntenatalPatientRegister
        ? "antenatal"
      : showConsultation
        ? "queue"
        : showDoctor
          ? "doctor-queue"
          : showNursing
            ? "nursing-dashboard"
            : showLaboratory
              ? "laboratory-dashboard"
              : showRadiology
                ? "radiology-dashboard"
                : showPharmacy
                  ? "pharmacy-dashboard"
                  : showAccountant
                    ? "accountant-cashier"
                    : "admin-dashboard";
  const activeId = navItemId ?? fallbackActiveId;

  // Reception search opens the same patient profile as Patients List (#/reception/record/{uuid}).
  // Visit creation stays available from that profile and dedicated Create Visit entry points.
  const onPatientSelect = showAccountant
    ? openAccountantPatient
    : showPatientAccount
    ? openPatientAccount
    : showCreateVisit ||
        showAntenatalRegistration ||
        showAntenatalPatientRegister ||
        showDesk ||
        showRegistrationPatient ||
        showRegistrationRegister ||
        showReceptionPatients ||
        showReceptionPatientRecord ||
        showReceptionFamilies ||
        showReceptionFamily
      ? (uuid: string) => openPatientRecord(uuid, "reception")
      : showDoctor
        ? openConsultation
        : showNursing
          ? openNursingPatient
          : showLaboratory
            ? openLaboratoryPatient
            : showRadiology
              ? openRadiologyPatient
              : showPharmacy
                ? openPharmacyPatient
                : doctorAllowed
                  ? openConsultation
                  : nursingAllowed
                    ? openNursingPatient
                    : laboratoryAllowed
                      ? openLaboratoryPatient
                      : radiologyAllowed
                        ? openRadiologyPatient
                        : pharmacyAllowed
                          ? openPharmacyPatient
                          : registrationAllowed
                            ? (uuid: string) => openPatientRecord(uuid, "reception")
                            : undefined;

  return (
    <AppShell
      context={context}
      workspaceLabel={departmentLabel}
      pageTitle={
        showDoctor &&
        !showConsultation &&
        section !== "my-patients" &&
        section !== "pharmacy-medicines"
          ? "Today's patients"
          : undefined
      }
      route={route}
      navGroups={navGroups}
      activeId={activeId}
      onWorkplaceChange={onWorkplaceChange}
      onSignOut={onSignOut}
      onPatientSelect={onPatientSelect}
    >
      {showDesk &&
      !showRegistrationPatient &&
      !showRegistrationRegister &&
      !showCreateVisit &&
      !showAntenatalRegistration &&
      !showAntenatalPatientRegister &&
      !showReceptionPatients &&
      !showReceptionFamilies &&
      !showReceptionFamily ? (
        <RegistrationDeskWorkspace />
      ) : null}
      {showReceptionPatients ? <PatientDirectoryWorkspace workplace="reception" /> : null}
      {showReceptionFamilies ? <FamilyListWorkspace /> : null}
      {showReceptionFamily && receptionFamilyId ? (
        <FamilyDetailWorkspace familyId={receptionFamilyId} />
      ) : null}
      {showAdminPatients ? <PatientDirectoryWorkspace workplace="administration" /> : null}
      {showReceptionPatientRecord && patientRecordUuid ? (
        <PatientRecordWorkspace
          key={patientRecordUuid}
          patientUuid={patientRecordUuid}
          workplace="reception"
          context={context}
        />
      ) : null}
      {showAdminPatientRecord && patientRecordUuid ? (
        <PatientRecordWorkspace
          key={patientRecordUuid}
          patientUuid={patientRecordUuid}
          workplace="administration"
          context={context}
        />
      ) : null}
      {showRegistrationRegister ? (
        <RegisterPatientWorkspace patientUuid={registrationEditUuid} />
      ) : null}
      {showAntenatalPatientRegister ? (
        <RegisterPatientWorkspace patientUuid={null} purpose="antenatal" />
      ) : null}
      {showCreateVisit ? <CreateVisitWorkspace patientUuid={createVisitPatientUuid} /> : null}
      {showAntenatalRegistration ? (
        <AntenatalRegistrationWorkspace patientUuid={antenatalPatientUuid} />
      ) : null}
      {showRegistrationPatient && registrationPatientUuid ? (
        <RegistrationPatientWorkspace
          key={registrationPatientUuid}
          patientUuid={registrationPatientUuid}
          context={context}
        />
      ) : null}
      {showDenied ? <AccessDeniedWorkspace context={context} /> : null}
      {showUnavailable ? <PageUnavailableWorkspace context={context} /> : null}
      {showComingSoon ? <ComingSoonWorkspace context={context} /> : null}
      {showConsultation && patientUuid ? (
        <ConsultationWorkspace
          key={`${patientUuid}:${selectedVisitUuid || "none"}`}
          patientUuid={patientUuid}
          selectedVisitUuid={selectedVisitUuid}
          context={context}
        />
      ) : null}
      {showDoctor && !showConsultation ? (
        <DoctorWorkspace context={context} section={section} />
      ) : null}
      {showNursingPatient && nursingPatientUuid ? (
        nursingTreatmentVisitUuid ? (
          <NursingTreatmentVisitWorkspace visitUuid={nursingTreatmentVisitUuid} />
        ) : (
          <NursingPatientWorkspace patientUuid={nursingPatientUuid} context={context} />
        )
      ) : null}
      {showNursing && !showNursingPatient ? <NursingWorkspace context={context} /> : null}
      {showLaboratoryPatient && laboratoryPatientUuid ? (
        <LaboratoryPatientWorkspace patientUuid={laboratoryPatientUuid} context={context} />
      ) : null}
      {showLaboratoryOrder && laboratoryOrderUuid ? (
        <LaboratoryOrderWorkspace
          key={`${laboratoryOrderUuid}:${laboratoryOrderExpected?.visitUuid || ""}`}
          orderUuid={laboratoryOrderUuid}
          expectedPatientUuid={laboratoryOrderExpected?.patientUuid}
          expectedVisitUuid={laboratoryOrderExpected?.visitUuid}
          context={context}
        />
      ) : null}
      {showLaboratoryExternal && laboratoryExternalId ? (
        <LaboratoryExternalPatientView
          key={laboratoryExternalId}
          externalId={laboratoryExternalId}
        />
      ) : null}
      {showLaboratory && !showLaboratoryPatient && !showLaboratoryOrder && !showLaboratoryExternal ? (
        <LaboratoryWorkspace context={context} />
      ) : null}
      {showRadiologyPatient && radiologyPatientUuid ? (
        <RadiologyPatientWorkspace
          key={radiologyPatientUuid}
          patientUuid={radiologyPatientUuid}
          context={context}
        />
      ) : null}
      {showRadiologyOrder && radiologyOrderUuid ? (
        <RadiologyOrderWorkspace
          key={`${radiologyOrderUuid}:${radiologyOrderExpected?.visitUuid || ""}`}
          orderUuid={radiologyOrderUuid}
          expectedPatientUuid={radiologyOrderExpected?.patientUuid}
          expectedVisitUuid={radiologyOrderExpected?.visitUuid}
          context={context}
        />
      ) : null}
      {showRadiologyExternal && radiologyExternalStudyId ? (
        <RadiologyExternalStudyView
          key={radiologyExternalStudyId}
          studyId={radiologyExternalStudyId}
        />
      ) : null}
      {showRadiology && !showRadiologyPatient && !showRadiologyOrder && !showRadiologyExternal ? (
        <RadiologyWorkspace context={context} />
      ) : null}
      {showPharmacyPatient && pharmacyPatientUuid ? (
        <PharmacyPatientWorkspace patientUuid={pharmacyPatientUuid} context={context} />
      ) : null}
      {showPharmacyPrescription && pharmacyPrescriptionUuid ? (
        <PharmacyPrescriptionWorkspace orderUuid={pharmacyPrescriptionUuid} />
      ) : null}
      {showPharmacy && !showPharmacyPatient && !showPharmacyPrescription ? (
        <PharmacyWorkspace context={context} />
      ) : null}
      {showPatientAccount && patientAccountUuid && route === "patient-account-invoice" && patientAccountInvoiceId ? (
        <PatientAccountInvoiceWorkspace
          patientUuid={patientAccountUuid}
          invoiceId={patientAccountInvoiceId}
          context={context}
        />
      ) : null}
      {showPatientAccount && patientAccountUuid && route === "patient-account" ? (
        <PatientAccountWorkspace
          patientUuid={patientAccountUuid}
          selectedVisitUuid={patientAccountVisitUuid}
          context={context}
        />
      ) : null}
      {showAccountant && route === "accountant-patient" && accountantPatientUuid ? (
        <AccountantPatientWorkspace patientUuid={accountantPatientUuid} context={context} />
      ) : null}
      {showAccountant && route === "accountant" ? (
        <AccountantWorkspace context={context} section={section} />
      ) : null}
      {showHmo ? <HmoWorkspace canManage={registrationAllowed || administrationAllowed} /> : null}
      {showStaffAccounts ? <StaffAccountsWorkspace /> : null}
      {showDepartmentAccess ? <DepartmentAccessWorkspace /> : null}
      {showAdminAnalytics ? <AdminAnalyticsWorkspace /> : null}
      {showAdminAudit ? <AdminAuditWorkspace /> : null}
      {showAdminExport ? <AdminExportWorkspace /> : null}
      {showAdminHmoBills ? <AdminHmoBillsWorkspace /> : null}
      {showAdminCertificates ? <AdminCertificatesWorkspace /> : null}
      {showAdminLog ? <AdminStaffLogWorkspace /> : null}
      {showAccommodationSettings ? <AccommodationSettingsWorkspace /> : null}
      {showMessages || showMessageCalls ? (
        <MessagesWorkspace
          context={context}
          callOnly={showMessageCalls}
          conversationId={showMessageCalls ? "" : section || ""}
        />
      ) : null}
      {showSystemSettings ? <SystemSettingsWorkspace /> : null}
      {!showDesk &&
      !showRegistrationPatient &&
      !showRegistrationRegister &&
      !showCreateVisit &&
      !showAntenatalRegistration &&
      !showAntenatalPatientRegister &&
      !showReceptionPatients &&
      !showAdminPatients &&
      !showReceptionPatientRecord &&
      !showAdminPatientRecord &&
      !showDenied &&
      !showUnavailable &&
      !showComingSoon &&
      !showDoctor &&
      !showNursing &&
      !showLaboratory &&
      !showRadiology &&
      !showPharmacy &&
      !showPatientAccount &&
      !showAccountant &&
      !showHmo &&
      !showAdminHmoBills &&
      !showAdminCertificates &&
      !showStaffAccounts &&
      !showDepartmentAccess &&
      !showAdminAnalytics &&
      !showAdminAudit &&
      !showAdminExport &&
      !showAdminLog &&
      !showAccommodationSettings &&
      !showMessages &&
      !showMessageCalls &&
      !showSystemSettings ? (
        <ClinicalHomeWorkspace context={context} />
      ) : null}
    </AppShell>
  );
}
