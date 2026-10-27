const STATE_NAMES = [
  "Alabama",
  "Alaska",
  "Arizona",
  "Arkansas",
  "California",
  "Colorado",
  "Connecticut",
  "Delaware",
  "Florida",
  "Georgia",
  "Hawaii",
  "Idaho",
  "Illinois",
  "Indiana",
  "Iowa",
  "Kansas",
  "Kentucky",
  "Louisiana",
  "Maine",
  "Maryland",
  "Massachusetts",
  "Michigan",
  "Minnesota",
  "Mississippi",
  "Missouri",
  "Montana",
  "Nebraska",
  "Nevada",
  "New Hampshire",
  "New Jersey",
  "New Mexico",
  "New York",
  "North Carolina",
  "North Dakota",
  "Ohio",
  "Oklahoma",
  "Oregon",
  "Pennsylvania",
  "Rhode Island",
  "South Carolina",
  "South Dakota",
  "Tennessee",
  "Texas",
  "Utah",
  "Vermont",
  "Virginia",
  "Washington",
  "West Virginia",
  "Wisconsin",
  "Wyoming",
  "District of Columbia",
].join("|");

const STATE_NAME_WITH_ZIP_NO_COMMA = new RegExp(`\\b(${STATE_NAMES})\\s(\\d{5}(?:-\\d{4})?)\\b`, "g");

export type NormalizedAddressCandidate = {
  rawAddress: string;
  normalizedForGeocoder: string;
  changed: boolean;
};

export function normalizeAddressForGeocoder(rawAddress: string): NormalizedAddressCandidate {
  const trimmed = rawAddress.trim();
  if (!trimmed) {
    return { rawAddress, normalizedForGeocoder: rawAddress, changed: false };
  }

  const normalized = trimmed.replace(STATE_NAME_WITH_ZIP_NO_COMMA, "$1, $2");
  return {
    rawAddress,
    normalizedForGeocoder: normalized,
    changed: normalized !== trimmed,
  };
}
