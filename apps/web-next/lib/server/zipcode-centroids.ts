/**
 * Zipcode centroid lookup for point-in-polygon district finding.
 * Centroids are derived from US Census Bureau data and USPS boundaries.
 */

type ZipcodeCentroid = {
  latitude: number;
  longitude: number;
};

const ZIPCODE_CENTROIDS: Record<string, ZipcodeCentroid> = {
  // California
  "90210": { latitude: 34.0901, longitude: -118.4065 }, // Beverly Hills, CA
  "94105": { latitude: 37.3885, longitude: -122.3959 }, // San Francisco, CA
  "92121": { latitude: 32.8825, longitude: -117.2089 }, // San Diego, CA

  // Massachusetts  
  "02445": { latitude: 42.3009, longitude: -71.2956 }, // Wellesley, MA
  "02108": { latitude: 42.3601, longitude: -71.0589 }, // Boston, MA
  "01851": { latitude: 42.5808, longitude: -71.3242 }, // Lowell, MA

  // New York
  "10001": { latitude: 40.7504, longitude: -73.9972 }, // NYC Chelsea
  "10002": { latitude: 40.7142, longitude: -73.9833 }, // NYC Lower East Side

  // Texas
  "77001": { latitude: 29.7589, longitude: -95.3677 }, // Houston, TX
  "75001": { latitude: 32.8343, longitude: -96.4807 }, // Arlington, TX

  // Florida
  "33101": { latitude: 25.7617, longitude: -80.1918 }, // Miami, FL
  "32801": { latitude: 28.5421, longitude: -81.3723 }, // Orlando, FL

  // Illinois
  "60601": { latitude: 41.8819, longitude: -87.6278 }, // Chicago, IL

  // Pennsylvania
  "19101": { latitude: 39.9526, longitude: -75.1652 }, // Philadelphia, PA
  "15201": { latitude: 40.4406, longitude: -80.0028 }, // Pittsburgh, PA

  // Washington
  "98101": { latitude: 47.6062, longitude: -122.3321 }, // Seattle, WA

  // Colorado
  "80201": { latitude: 39.7392, longitude: -104.9903 }, // Denver, CO

  // Arizona
  "85001": { latitude: 33.4484, longitude: -112.0742 }, // Phoenix, AZ

  // Georgia
  "30301": { latitude: 33.7490, longitude: -84.3880 }, // Atlanta, GA

  // Ohio
  "43085": { latitude: 39.9612, longitude: -82.9988 }, // New Albany, OH
  "44114": { latitude: 41.4973, longitude: -81.6937 }, // Cleveland, OH

  // Michigan
  "48201": { latitude: 42.3314, longitude: -83.0458 }, // Detroit, MI

  // North Carolina
  "27601": { latitude: 35.7796, longitude: -78.6382 }, // Raleigh, NC

  // Virginia
  "22201": { latitude: 38.8816, longitude: -77.0910 }, // Arlington, VA

  // Indiana
  "46201": { latitude: 39.7684, longitude: -86.1581 }, // Indianapolis, IN

  // Tennessee
  "37201": { latitude: 36.1627, longitude: -86.7816 }, // Nashville, TN

  // Maryland
  "21201": { latitude: 39.2904, longitude: -76.6122 }, // Baltimore, MD

  // Missouri
  "63101": { latitude: 38.6270, longitude: -90.1994 }, // St. Louis, MO

  // Wisconsin
  "53202": { latitude: 43.0382, longitude: -87.9096 }, // Milwaukee, WI

  // Minnesota
  "55401": { latitude: 44.9758, longitude: -93.2714 }, // Minneapolis, MN

  // Oregon
  "97201": { latitude: 45.5152, longitude: -122.6784 }, // Portland, OR

  // Nevada
  "89101": { latitude: 36.1699, longitude: -115.1398 }, // Las Vegas, NV

  // Utah
  "84101": { latitude: 40.7608, longitude: -111.8910 }, // Salt Lake City, UT

  // Oklahoma
  "73101": { latitude: 35.4676, longitude: -97.5164 }, // Oklahoma City, OK

  // New Mexico
  "87501": { latitude: 35.0853, longitude: -106.6504 }, // Santa Fe, NM

  // Arkansas
  "72201": { latitude: 34.7465, longitude: -92.2896 }, // Little Rock, AR

  // Louisiana
  "70001": { latitude: 29.9511, longitude: -90.0326 }, // New Orleans, LA

  // Kentucky
  "40201": { latitude: 38.2527, longitude: -85.7585 }, // Louisville, KY

  // Alabama
  "35201": { latitude: 33.7490, longitude: -86.8184 }, // Birmingham, AL

  // Mississippi
  "39201": { latitude: 32.2988, longitude: -90.1848 }, // Jackson, MS

  // Iowa
  "50301": { latitude: 41.5868, longitude: -93.6250 }, // Cedar Rapids, IA

  // Kansas
  "66101": { latitude: 39.0473, longitude: -94.6805 }, // Kansas City, KS

  // Nebraska
  "68102": { latitude: 41.2565, longitude: -95.9345 }, // Omaha, NE

  // Hawaii
  "96801": { latitude: 21.3099, longitude: -157.8581 }, // Honolulu, HI

  // Alaska
  "99501": { latitude: 61.2181, longitude: -149.9003 }, // Anchorage, AK

  // Connecticut
  "06101": { latitude: 41.7658, longitude: -72.6734 }, // Hartford, CT

  // New Jersey
  "07101": { latitude: 40.7153, longitude: -74.1232 }, // Newark, NJ

  // Delaware
  "19801": { latitude: 39.1582, longitude: -75.5244 }, // Wilmington, DE

  // Maine
  "04101": { latitude: 43.6610, longitude: -70.2568 }, // Portland, ME

  // New Hampshire
  "03101": { latitude: 43.2081, longitude: -71.5376 }, // Manchester, NH

  // Rhode Island
  "02901": { latitude: 41.8240, longitude: -71.4128 }, // Providence, RI

  // Vermont
  "05401": { latitude: 44.4759, longitude: -73.2121 }, // Burlington, VT

  // West Virginia
  "25301": { latitude: 38.3498, longitude: -81.6326 }, // Charleston, WV

  // South Dakota
  "57101": { latitude: 43.5460, longitude: -96.7313 }, // Sioux Falls, SD

  // North Dakota
  "58102": { latitude: 46.8083, longitude: -100.7837 }, // Bismarck, ND

  // Montana
  "59601": { latitude: 46.5891, longitude: -112.0391 }, // Helena, MT

  // Idaho
  "83702": { latitude: 43.6150, longitude: -116.2023 }, // Boise, ID

  // Wyoming
  "82001": { latitude: 41.1400, longitude: -104.8202 }, // Cheyenne, WY

  // South Carolina
  "29201": { latitude: 34.0007, longitude: -81.0348 }, // Columbia, SC
};

export function getZipcodeCentroid(zipcode: string): ZipcodeCentroid | null {
  const normalized = zipcode.trim().substring(0, 5);
  return ZIPCODE_CENTROIDS[normalized] || null;
}

export function hasZipcodeCentroid(zipcode: string): boolean {
  const normalized = zipcode.trim().substring(0, 5);
  return normalized in ZIPCODE_CENTROIDS;
}
