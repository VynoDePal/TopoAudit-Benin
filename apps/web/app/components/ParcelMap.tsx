"use client";

import { useEffect, useId, useRef } from "react";
import maplibregl, { type GeoJSONSource, type Map, type StyleSpecification } from "maplibre-gl";
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

type ParcelMapProps = {
  parcels?: GeoJSON.FeatureCollection<GeoJSON.Polygon>;
  title?: string;
  description?: string;
};

function fitParcelBounds(map: Map, parcels: GeoJSON.FeatureCollection<GeoJSON.Polygon>) {
  const bounds = new maplibregl.LngLatBounds();
  parcels.features.forEach((feature) => {
    feature.geometry.coordinates[0].forEach((coordinate) => bounds.extend(coordinate as [number, number]));
  });

  if (!bounds.isEmpty()) {
    map.fitBounds(bounds, { padding: 80, maxZoom: 17 });
  }
}

export default function ParcelMap({
  parcels = sampleParcels,
  title = "Polygones GeoJSON sur fond OSM / Esri",
  description = "La carte charge MapLibre GL JS côté client, superpose des parcelles GeoJSON en EPSG:4326 et conserve l’ordre strict des coordonnées [longitude, latitude]."
}: ParcelMapProps) {
  const mapContainer = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<Map | null>(null);
  const initialParcelsRef = useRef(parcels);
  const titleId = useId();

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
      const initialParcels = initialParcelsRef.current;
      map.addSource("parcels", { type: "geojson", data: initialParcels });
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

      fitParcelBounds(map, initialParcels);
    });

    mapRef.current = map;

    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    const source = mapRef.current?.getSource("parcels") as GeoJSONSource | undefined;
    if (!source || !mapRef.current) {
      return;
    }

    source.setData(parcels);
    fitParcelBounds(mapRef.current, parcels);
  }, [parcels]);

  return (
    <section className="map-panel" aria-labelledby={titleId}>
      <div className="map-copy">
        <p className="eyebrow">Visualisation cartographique</p>
        <h2 id={titleId}>{title}</h2>
        <p>{description}</p>
      </div>
      <div ref={mapContainer} className="map-container" role="img" aria-label="Carte des parcelles GeoJSON" />
    </section>
  );
}
