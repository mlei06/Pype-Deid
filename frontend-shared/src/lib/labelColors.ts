/**
 * PHI label colors — grouped into semantic families so the eye can filter by category:
 * identities (blues/purples), geography (greens), temporality (oranges/ambers), contact (corals), etc.
 */

export type LabelSemanticFamily =
  | 'identity'
  | 'geography'
  | 'temporal'
  | 'contact'
  | 'identifier'
  | 'clinical'
  | 'other';

const FAMILY_COLORS: Record<
  LabelSemanticFamily,
  { bg: string; text: string; border: string }
> = {
  identity: { bg: '#dbeafe', text: '#1e3a8a', border: '#60a5fa' },
  geography: { bg: '#d1fae5', text: '#065f46', border: '#34d399' },
  temporal: { bg: '#ffedd5', text: '#9a3412', border: '#fb923c' },
  contact: { bg: '#fce7f3', text: '#9d174d', border: '#f472b6' },
  identifier: { bg: '#ede9fe', text: '#5b21b6', border: '#a78bfa' },
  clinical: { bg: '#fef3c7', text: '#854d0e', border: '#fbbf24' },
  other: { bg: '#f3f4f6', text: '#374151', border: '#9ca3af' },
};

/** Map canonical PHI labels to a semantic family (for consistent coloring). */
export function labelSemanticFamily(label: string): LabelSemanticFamily {
  const u = label.toUpperCase();
  if (
    /NAME|PATIENT|DOCTOR|STAFF|HCW|PERSON|ORGANIZATION/i.test(u) ||
    u === 'BIOMETRIC' ||
    u === 'PHOTO'
  ) {
    return 'identity';
  }
  if (
    /ADDRESS|LOCATION|CITY|STATE|COUNTRY|ZIP|POSTAL|HOSPITAL/i.test(u)
  ) {
    return 'geography';
  }
  if (/DATE|TIME/i.test(u)) {
    return 'temporal';
  }
  if (/PHONE|FAX|EMAIL|URL|IP/i.test(u)) {
    return 'contact';
  }
  if (/SSN|MRN|ID|ACCOUNT|LICENSE|VEHICLE|DEVICE|OHIP|SIN|IDNUM/i.test(u)) {
    return 'identifier';
  }
  if (/AGE|DOCTOR|STAFF/i.test(u)) {
    return 'clinical';
  }
  return 'other';
}

export function labelFamilySwatch(family: LabelSemanticFamily): {
  bg: string;
  text: string;
  border: string;
} {
  return FAMILY_COLORS[family];
}

export function labelFamilyLegend(): { family: LabelSemanticFamily; title: string }[] {
  return [
    { family: 'identity', title: 'Names & people' },
    { family: 'geography', title: 'Places & facilities' },
    { family: 'temporal', title: 'Dates & times' },
    { family: 'contact', title: 'Phone, email, web' },
    { family: 'identifier', title: 'IDs & numbers' },
    { family: 'clinical', title: 'Clinical / age' },
    { family: 'other', title: 'Other' },
  ];
}

/** Build per-label colors from semantic families. */
function buildKnown(): Record<string, { bg: string; text: string; border: string }> {
  const m: Record<string, { bg: string; text: string; border: string }> = {};
  const labels = [
    'NAME',
    'FIRST_NAME',
    'LAST_NAME',
    'PATIENT',
    'DOCTOR',
    'STAFF',
    'HCW',
    'PERSON',
    'ORGANIZATION',
    'ADDRESS',
    'LOCATION',
    'CITY',
    'STATE',
    'COUNTRY',
    'ZIP_CODE',
    'ZIP_CODE_US',
    'POSTAL_CODE',
    'HOSPITAL',
    'DATE',
    'DATE_TIME',
    'PHONE',
    'FAX',
    'EMAIL',
    'URL',
    'IP_ADDRESS',
    'SSN',
    'MRN',
    'ID',
    'ACCOUNT',
    'LICENSE',
    'VEHICLE_ID',
    'DEVICE_ID',
    'OHIP',
    'SIN',
    'IDNUM',
    'AGE',
    'BIOMETRIC',
    'PHOTO',
    'OTHER',
  ];
  for (const lab of labels) {
    const fam = labelSemanticFamily(lab);
    m[lab] = { ...FAMILY_COLORS[fam] };
  }
  return m;
}

const COMPUTED_KNOWN = buildKnown();

const PALETTE = [
  { bg: '#fae8ff', text: '#86198f', border: '#e879f9' },
  { bg: '#e0f2fe', text: '#075985', border: '#7dd3fc' },
  { bg: '#ecfccb', text: '#3f6212', border: '#bef264' },
];

function hashStr(s: string): number {
  let h = 0;
  for (let i = 0; i < s.length; i++) {
    h = ((h << 5) - h + s.charCodeAt(i)) | 0;
  }
  return Math.abs(h);
}

export function labelColor(label: string): { bg: string; text: string; border: string } {
  const upper = label.toUpperCase();
  if (COMPUTED_KNOWN[upper]) return COMPUTED_KNOWN[upper];
  const fam = labelSemanticFamily(upper);
  return FAMILY_COLORS[fam] ?? PALETTE[hashStr(upper) % PALETTE.length];
}
