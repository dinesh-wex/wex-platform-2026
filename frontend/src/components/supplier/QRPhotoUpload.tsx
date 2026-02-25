"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { QRCodeSVG } from "qrcode.react";
import { Camera, Loader2, CheckCircle2, AlertCircle } from "lucide-react";
import { api } from "@/lib/api";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface QRPhotoUploadProps {
  propertyId: string;
  onPhotosUploaded?: () => void;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function QRPhotoUpload({
  propertyId,
  onPhotosUploaded,
}: QRPhotoUploadProps) {
  const [token, setToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [photoCount, setPhotoCount] = useState<number>(0);
  const [newPhotosDetected, setNewPhotosDetected] = useState(false);
  const initialCountRef = useRef<number | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // ---- Fetch upload token on mount ----
  useEffect(() => {
    let cancelled = false;

    async function fetchToken() {
      try {
        const result = await api.getUploadToken(propertyId);
        if (cancelled) return;
        setToken(result.token);
        setError(false);
      } catch {
        if (!cancelled) setError(true);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    fetchToken();
    return () => {
      cancelled = true;
    };
  }, [propertyId]);

  // ---- Fetch initial photo count ----
  useEffect(() => {
    async function fetchInitialCount() {
      try {
        const photos = await api.getPropertyPhotos(propertyId);
        const count = Array.isArray(photos) ? photos.length : 0;
        initialCountRef.current = count;
        setPhotoCount(count);
      } catch {
        initialCountRef.current = 0;
        setPhotoCount(0);
      }
    }

    fetchInitialCount();
  }, [propertyId]);

  // ---- Poll for new photos every 5 seconds ----
  const checkForNewPhotos = useCallback(async () => {
    try {
      const photos = await api.getPropertyPhotos(propertyId);
      const count = Array.isArray(photos) ? photos.length : 0;

      if (
        initialCountRef.current !== null &&
        count > initialCountRef.current
      ) {
        setNewPhotosDetected(true);
        setPhotoCount(count);
        onPhotosUploaded?.();

        // Update the baseline so we detect the *next* batch too
        initialCountRef.current = count;
      }
    } catch {
      // Silently ignore poll failures
    }
  }, [propertyId, onPhotosUploaded]);

  useEffect(() => {
    if (!token) return;

    pollRef.current = setInterval(checkForNewPhotos, 5000);

    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [token, checkForNewPhotos]);

  // ---- Clear "new photos" indicator after 4 seconds ----
  useEffect(() => {
    if (!newPhotosDetected) return;
    const t = setTimeout(() => setNewPhotosDetected(false), 4000);
    return () => clearTimeout(t);
  }, [newPhotosDetected]);

  // ---- Build the upload URL ----
  const uploadUrl =
    typeof window !== "undefined" && token
      ? `${window.location.origin}/upload/${propertyId}/${token}`
      : "";

  // ---- Loading ----
  if (loading) {
    return (
      <div className="flex items-center justify-center py-8">
        <Loader2 className="h-5 w-5 animate-spin text-slate-400" />
      </div>
    );
  }

  // ---- Error / fallback ----
  if (error || !token) {
    return (
      <div className="rounded-xl border border-slate-200 bg-white p-6 text-center">
        <AlertCircle className="mx-auto mb-2 h-6 w-6 text-amber-500" />
        <p className="text-sm text-slate-600">
          Could not generate a mobile upload link.
        </p>
        <p className="mt-1 text-xs text-slate-400">
          Upload from desktop using the drag-and-drop area instead.
        </p>
      </div>
    );
  }

  // ---- QR Code ----
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-6">
      <div className="flex flex-col items-center text-center">
        {/* QR Code */}
        <div className="rounded-lg border border-slate-100 bg-white p-3 shadow-sm">
          <QRCodeSVG
            value={uploadUrl}
            size={160}
            level="M"
            includeMargin={false}
            bgColor="#ffffff"
            fgColor="#0f172a"
          />
        </div>

        {/* Instructions */}
        <div className="mt-4 flex items-center gap-2 text-sm font-medium text-slate-700">
          <Camera className="h-4 w-4 text-emerald-500" />
          Scan to take photos from your phone
        </div>
        <p className="mt-1 text-xs text-slate-400">
          Link expires in 30 minutes
        </p>

        {/* New photos notification */}
        {newPhotosDetected && (
          <div className="mt-4 flex items-center gap-2 rounded-full bg-emerald-50 px-4 py-2 text-sm font-medium text-emerald-700">
            <CheckCircle2 className="h-4 w-4" />
            New photos received! ({photoCount} total)
          </div>
        )}
      </div>
    </div>
  );
}
