"use client";

import { useEffect, useRef } from "react";
import maplibregl, { type Map, type StyleSpecification } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

const beninCenter: [number, number] = [2.3158, 9.3077];

const osmEsriStyle: StyleSpecification = {
  version: 8,
  sources: {
    osm: {
      type: "raster",
      tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
      tileSize: 256,
      attribution: "© OpenStreetMap contributors"
    },
    esri: {
      type: "raster",
      tiles: [
        "https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
      ],
      tileSize: 256,
      attribution: "Tiles © Esri"
    }
  },
  layers: [
    { id: "esri-satellite", type: "raster", source: "esri", paint: { "raster-opacity": 0.42 } },
    { id: "osm-streets", type: "raster", source: "osm", paint: { "raster-opacity": 0.78 } }
  ]
};

const sampleParcels: GeoJSON.FeatureCollection<GeoJSON.Polygon> = {
  type: "FeatureCollection",
  features: [
    {
      type: "Feature",
      properties: { name: "Parcelle A", risk: "Faible" },
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            [2.62058, 6.38404],
            [2.62174, 6.38408],
            [2.6217, 6.38506],
            [2.62054, 6.38501],
            [2.62058, 6.38404]
          ]
        ]
      }
    },
    {
      type: "Feature",
      properties: { name: "Parcelle B", risk: "Modéré" },
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            [2.62302, 6.38355],
            [2.62405, 6.38375],
            [2.62386, 6.38477],
            [2.62283, 6.38459],
            [2.62302, 6.38355]
          ]
        ]
      }
    }
  ]
};

export default function ParcelMap() {
  const mapContainer = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<Map | null>(null);

  useEffect(() => {
    if (!mapContainer.current || mapRef.current) {
      return;
    }

    const map = new maplibregl.Map({
      container: mapContainer.current,
      style: osmEsriStyle,
      center: beninCenter,
      zoom: 6,
      attributionControl: false
    });

    map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), "top-right");
    map.addControl(new maplibregl.AttributionControl({ compact: true }), "bottom-right");

    map.on("load", () => {
      map.addSource("parcels", { type: "geojson", data: sampleParcels });
      map.addLayer({
        id: "parcel-fill",
        type: "fill",
        source: "parcels",
        paint: {
          "fill-color": ["match", ["get", "risk"], "Faible", "#16a34a", "Modéré", "#f59e0b", "#dc2626"],
          "fill-opacity": 0.34
        }
      });
      map.addLayer({
        id: "parcel-outline",
        type: "line",
        source: "parcels",
        paint: {
          "line-color": "#064e3b",
          "line-width": 3
        }
      });

      const bounds = new maplibregl.LngLatBounds();
      sampleParcels.features.forEach((feature) => {
        feature.geometry.coordinates[0].forEach((coordinate) => bounds.extend(coordinate as [number, number]));
      });
      map.fitBounds(bounds, { padding: 80, maxZoom: 17 });
    });

    mapRef.current = map;

    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  return (
    <section className="map-panel" aria-labelledby="map-title">
      <div className="map-copy">
        <p className="eyebrow">Visualisation cartographique</p>
        <h2 id="map-title">Polygones GeoJSON sur fond OSM / Esri</h2>
        <p>
          La carte charge MapLibre GL JS côté client, superpose des parcelles GeoJSON en EPSG:4326
          et conserve l’ordre strict des coordonnées [longitude, latitude].
        </p>
      </div>
      <div ref={mapContainer} className="map-container" role="img" aria-label="Carte des parcelles GeoJSON" />
    </section>
  );
}
