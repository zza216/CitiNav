// CitiNav — shorten a street name for the handlebar display.
//
// The device banner fits 20 chars in the big font and 40 in the small one
// (see draw_banner in citinav_landscape.py), so we abbreviate the usual
// suffixes / directions the way street signs do and fold to plain ASCII
// (the device fonts are ASCII-only):
//
//   "East 15th Street"        -> "E 15th St"
//   "Washington Square North" -> "Washington Sq N"
//   "Avenue of the Americas"  -> "Avenue of the Americas"   (leading type word kept)
//   "South Street"            -> "South St"                  (direction IS the name)
//   "Calle Señor"             -> "Calle Senor"
//
// ':' is the payload separator, so it is always stripped.

const STREET_MAX = 40;   // keep in sync with STREET_MAX in citinav_landscape.py

const STREET_TYPES = {
  street: "St", avenue: "Ave", boulevard: "Blvd", place: "Pl", square: "Sq",
  road: "Rd", drive: "Dr", lane: "Ln", parkway: "Pkwy", expressway: "Expy",
  highway: "Hwy", terrace: "Ter", court: "Ct", plaza: "Plz", bridge: "Br",
  alley: "Aly", circle: "Cir", turnpike: "Tpke",
};
const DIRECTIONS = { north: "N", south: "S", east: "E", west: "W" };

function shortStreet(name, max = STREET_MAX) {
  if (!name) return "";
  const ascii = String(name)
    .normalize("NFKD").replace(/[̀-ͯ]/g, "")    // é -> e
    .replace(/[’‘]/g, "'").replace(/[–—]/g, "-")
    .replace(/[^\x20-\x7e]/g, "")                          // anything else non-ASCII
    .replace(/:/g, " ");
  const words = ascii.split(/\s+/).filter(Boolean);
  const isType = (w) => STREET_TYPES.hasOwnProperty(w.toLowerCase());
  const isDir = (w) => DIRECTIONS.hasOwnProperty(w.toLowerCase());
  // a direction only abbreviates when some other word carries the name
  const hasNameWord = words.some((w) => !isType(w) && !isDir(w));

  const out = words.map((w, i) => {
    const k = w.toLowerCase();
    if (isType(w) && i > 0) return STREET_TYPES[k];
    if (isDir(w) && hasNameWord) return DIRECTIONS[k];
    return w;
  }).join(" ");
  return out.length <= max ? out : out.slice(0, max).trimEnd();
}

if (typeof module !== "undefined") module.exports = { shortStreet, STREET_MAX };
