/** Doctor → Reception patient call API (compat wrappers). */

export {
  createPatientCall,
  newNotificationRequestId as newPatientCallRequestId,
  NotificationRequestError as PatientCallRequestError,
} from "./notifications";
