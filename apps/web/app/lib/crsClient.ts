// Logique CRS côté client (P0). Seuls ces CRS sont géoréférencés/transformables vers
// WGS84. Tout le reste (LOCAL_ONLY, UNKNOWN_CRS, NEEDS_GEOREFERENCING, "local", inconnu)
// est NON transformable → pas de fond satellite, pas d'appel à toWgs84.

import proj4 from "proj4";

export const TRANSFORMABLE_CRS = new Set(["EPSG:32631", "EPSG_32631", "EPSG:4326", "EPSG_4326"]);

export const isTransformableCrs = (crs: string | null | undefined): boolean =>
  !!crs && TRANSFORMABLE_CRS.has(crs);

const UTM_31N_PROJ = "+proj=utm +zone=31 +datum=WGS84 +units=m +no_defs";

// Transforme une coordonnée vers WGS84. LÈVE si le CRS n'est pas transformable —
// on ne projette JAMAIS implicitement un CRS inconnu comme de l'UTM 31N.
export const toWgs84 = (x: number, y: number, crs: string): [number, number] => {
  if (!isTransformableCrs(crs)) {
    throw new Error(`CRS non transformable vers WGS84 : ${crs}`);
  }
  if (crs === "EPSG:4326" || crs === "EPSG_4326") return [x, y];
  return proj4(UTM_31N_PROJ, "WGS84", [x, y]) as [number, number];
};
