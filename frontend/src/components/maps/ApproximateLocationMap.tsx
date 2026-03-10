"use client";

import { useEffect, useRef } from "react";
import { APIProvider, Map, useMap } from "@vis.gl/react-google-maps";
import { MapPin } from "lucide-react";

/* ------------------------------------------------------------------ */
/*  Silver / Greyscale Map Style (keeps highways + water readable)      */
/* ------------------------------------------------------------------ */

const SILVER_STYLE: google.maps.MapTypeStyle[] = [
  { elementType: "geometry", stylers: [{ color: "#f5f5f5" }] },
  { elementType: "labels.text.fill", stylers: [{ color: "#616161" }] },
  { elementType: "labels.text.stroke", stylers: [{ color: "#f5f5f5" }] },
  { featureType: "poi", stylers: [{ visibility: "off" }] },
  { featureType: "road", elementType: "geometry", stylers: [{ color: "#ffffff" }] },
  {
    featureType: "road.highway",
    elementType: "geometry.fill",
    stylers: [{ color: "#e8e8e8" }],
  },
  {
    featureType: "road.highway",
    elementType: "geometry.stroke",
    stylers: [{ color: "#d4d4d4" }],
  },
  {
    featureType: "road.highway",
    elementType: "labels.text.fill",
    stylers: [{ color: "#616161" }],
  },
  {
    featureType: "transit.line",
    elementType: "geometry",
    stylers: [{ color: "#e0e0e0" }],
  },
  { featureType: "water", elementType: "geometry", stylers: [{ color: "#d4e6f1" }] },
  {
    featureType: "water",
    elementType: "labels.text.fill",
    stylers: [{ color: "#8fabbe" }],
  },
];

/* ------------------------------------------------------------------ */
/*  Location Circle Overlay                                            */
/* ------------------------------------------------------------------ */

function LocationCircle({
  lat,
  lng,
  radius,
}: {
  lat: number;
  lng: number;
  radius: number;
}) {
  const map = useMap();
  const circleRef = useRef<google.maps.Circle | null>(null);

  useEffect(() => {
    if (!map) return;

    circleRef.current = new google.maps.Circle({
      map,
      center: { lat, lng },
      radius,
      fillColor: "#10b981",
      fillOpacity: 0.15,
      strokeColor: "#059669",
      strokeWeight: 2,
      clickable: false,
    });

    return () => {
      circleRef.current?.setMap(null);
      circleRef.current = null;
    };
  }, [map, lat, lng, radius]);

  return null;
}

/* ------------------------------------------------------------------ */
/*  Exported Component                                                 */
/* ------------------------------------------------------------------ */

interface ApproximateLocationMapProps {
  lat: number;
  lng: number;
  radiusMeters?: number;
  label?: string;
}

export default function ApproximateLocationMap({
  lat,
  lng,
  radiusMeters = 800,
  label,
}: ApproximateLocationMapProps) {
  const apiKey = process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY;

  if (!apiKey) {
    return (
      <div className="w-full h-64 rounded-xl bg-slate-100 border border-slate-200 flex items-center justify-center">
        <span className="text-slate-400 text-sm flex items-center gap-2">
          <MapPin className="h-4 w-4" />
          Map unavailable
        </span>
      </div>
    );
  }

  return (
    <div>
      <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-400 mb-3">
        Approximate Location
      </h2>
      <div className="relative rounded-xl overflow-hidden border border-slate-200 shadow-sm">
        <APIProvider apiKey={apiKey}>
          <div style={{ width: "100%", height: "320px" }}>
            <Map
              defaultCenter={{ lat, lng }}
              defaultZoom={13}
              gestureHandling="cooperative"
              disableDefaultUI={true}
              zoomControl={true}
              styles={SILVER_STYLE}
            >
              <LocationCircle lat={lat} lng={lng} radius={radiusMeters} />
            </Map>
          </div>
        </APIProvider>

        {/* Bottom label */}
        <div className="absolute bottom-0 left-0 right-0 bg-white/90 backdrop-blur-sm border-t border-slate-100 px-4 py-2.5 flex items-center gap-2">
          <MapPin className="h-4 w-4 text-emerald-600 shrink-0" />
          <span className="text-xs text-slate-500">
            {label ? `${label} · ` : ""}Exact address provided after booking
          </span>
        </div>
      </div>
    </div>
  );
}
