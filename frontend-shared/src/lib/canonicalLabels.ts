/**
 * Canonical label list for the default clinical_phi pack (align with `clinical_deid.labels.CLINICAL_PHI`).
 *
 * All pipeline outputs should normalize to these labels so that
 * redaction/surrogate logic works consistently.
 */
export const CANONICAL_LABELS = [
  // HIPAA #1 — Names
  'NAME', 'FIRST_NAME', 'LAST_NAME', 'PATIENT', 'DOCTOR', 'STAFF', 'HCW',
  // HIPAA #2 — Geographic
  'ADDRESS', 'LOCATION', 'CITY', 'STATE', 'COUNTRY', 'ZIP_CODE', 'POSTAL_CODE',
  // HIPAA #3 — Dates
  'DATE', 'DATE_TIME',
  // HIPAA #4-5 — Phone/Fax
  'PHONE', 'FAX',
  // HIPAA #6 — Email
  'EMAIL',
  // HIPAA #7 — SSN
  'SSN',
  // HIPAA #8 — MRN
  'MRN',
  // HIPAA #9-11 — ID types
  'ID', 'ACCOUNT', 'LICENSE',
  // HIPAA #12-13 — Vehicle/Device
  'VEHICLE_ID', 'DEVICE_ID',
  // HIPAA #14-15 — Web/IP
  'URL', 'IP_ADDRESS',
  // HIPAA #16-17 — Biometric/Photo
  'BIOMETRIC', 'PHOTO',
  // Clinical additions
  'AGE', 'ORGANIZATION', 'HOSPITAL', 'IDNUM', 'OHIP', 'SIN', 'PERSON',
  // Catch-all
  'OTHER',
] as const;

export type CanonicalLabel = (typeof CANONICAL_LABELS)[number];
