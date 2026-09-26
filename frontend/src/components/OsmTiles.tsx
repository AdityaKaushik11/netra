import { TileLayer } from "react-leaflet";

/**
 * OpenStreetMap base layer, darkened via CSS to match the console.
 *
 * OSM's tile usage policy requires a Referer; the site-wide policy is `no-referrer`, so tiles
 * alone send the page's origin (never its path or query) or OSM answers 403 "Access blocked".
 */
export function OsmTiles() {
  return (
    <TileLayer
      attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
      url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
      className="dark-tiles"
      maxZoom={19}
      referrerPolicy="strict-origin"
    />
  );
}
