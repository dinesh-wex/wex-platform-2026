"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import { useParams } from "next/navigation";
import {
  Camera,
  CheckCircle2,
  Loader2,
  AlertTriangle,
  ImagePlus,
  X,
} from "lucide-react";
import { api } from "@/lib/api";

// =============================================================================
// Types
// =============================================================================

type PageState = "loading" | "ready" | "uploading" | "success" | "error";

// =============================================================================
// Component
// =============================================================================

export default function MobileUploadPage() {
  const params = useParams();
  const propertyId = params.propertyId as string;
  const token = params.token as string;

  const [state, setState] = useState<PageState>("loading");
  const [errorMessage, setErrorMessage] = useState("");
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [previewUrls, setPreviewUrls] = useState<string[]>([]);
  const [uploadProgress, setUploadProgress] = useState(0);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // ---- Verify token on mount ----
  useEffect(() => {
    let cancelled = false;

    async function verify() {
      try {
        const result = await api.verifyUploadToken(propertyId, token);
        if (cancelled) return;
        if (result.valid) {
          setState("ready");
        } else {
          setErrorMessage(
            "This upload link has expired. Please scan a new QR code from your dashboard.",
          );
          setState("error");
        }
      } catch {
        if (!cancelled) {
          setErrorMessage(
            "This upload link has expired. Please scan a new QR code from your dashboard.",
          );
          setState("error");
        }
      }
    }

    verify();
    return () => {
      cancelled = true;
    };
  }, [propertyId, token]);

  // ---- Handle file selection ----
  const handleFileChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const files = e.target.files;
      if (!files || files.length === 0) return;

      const validFiles = Array.from(files).filter((f) =>
        /\.(jpe?g|png|heic|webp)$/i.test(f.name),
      );

      setSelectedFiles((prev) => [...prev, ...validFiles]);

      // Generate preview URLs
      const urls = validFiles.map((f) => URL.createObjectURL(f));
      setPreviewUrls((prev) => [...prev, ...urls]);

      // Reset the input so the same file can be re-selected
      e.target.value = "";
    },
    [],
  );

  // ---- Remove a selected file ----
  const handleRemoveFile = useCallback(
    (index: number) => {
      URL.revokeObjectURL(previewUrls[index]);
      setSelectedFiles((prev) => prev.filter((_, i) => i !== index));
      setPreviewUrls((prev) => prev.filter((_, i) => i !== index));
    },
    [previewUrls],
  );

  // ---- Upload ----
  const handleUpload = useCallback(async () => {
    if (selectedFiles.length === 0) return;

    setState("uploading");
    setUploadProgress(0);

    try {
      const formData = new FormData();
      selectedFiles.forEach((f) => formData.append("photos", f));

      // Simulate progress (real progress would use XMLHttpRequest)
      const progressInterval = setInterval(() => {
        setUploadProgress((prev) => {
          if (prev >= 90) {
            clearInterval(progressInterval);
            return 90;
          }
          return prev + 10;
        });
      }, 200);

      await api.uploadPropertyPhotos(propertyId, token, formData);

      clearInterval(progressInterval);
      setUploadProgress(100);

      // Clean up preview URLs
      previewUrls.forEach((url) => URL.revokeObjectURL(url));

      setState("success");
    } catch {
      setState("ready");
      setErrorMessage("Upload failed. Please try again.");
    }
  }, [selectedFiles, previewUrls, propertyId, token]);

  // ---- Clean up URLs on unmount ----
  useEffect(() => {
    return () => {
      previewUrls.forEach((url) => URL.revokeObjectURL(url));
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ===========================================================================
  // Render
  // ===========================================================================

  return (
    <div className="min-h-screen bg-white">
      {/* ---- Header / Branding ---- */}
      <header className="sticky top-0 z-10 border-b border-slate-100 bg-white/90 backdrop-blur-md px-4 py-3">
        <div className="max-w-lg mx-auto flex items-center justify-center">
          <h1 className="text-xl font-bold text-slate-900">
            W<span className="text-emerald-500">Ex</span>
          </h1>
        </div>
      </header>

      <main className="max-w-lg mx-auto px-4 py-8">
        {/* ════════════════════════════════════════════
            Loading state
            ════════════════════════════════════════════ */}
        {state === "loading" && (
          <div className="flex flex-col items-center justify-center py-20">
            <Loader2 className="h-8 w-8 animate-spin text-emerald-500 mb-4" />
            <p className="text-sm text-slate-500">Verifying upload link...</p>
          </div>
        )}

        {/* ════════════════════════════════════════════
            Error state
            ════════════════════════════════════════════ */}
        {state === "error" && (
          <div className="flex flex-col items-center justify-center py-16 text-center">
            <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-amber-50">
              <AlertTriangle className="h-8 w-8 text-amber-500" />
            </div>
            <h2 className="text-lg font-semibold text-slate-900 mb-2">
              Link Expired
            </h2>
            <p className="text-sm text-slate-500 max-w-xs">{errorMessage}</p>
          </div>
        )}

        {/* ════════════════════════════════════════════
            Ready state — file picker + upload
            ════════════════════════════════════════════ */}
        {state === "ready" && (
          <div className="space-y-6">
            <div className="text-center">
              <div className="mb-4 inline-flex h-16 w-16 items-center justify-center rounded-full bg-emerald-50">
                <Camera className="h-8 w-8 text-emerald-600" />
              </div>
              <h2 className="text-xl font-bold text-slate-900">
                Upload Property Photos
              </h2>
              <p className="mt-1 text-sm text-slate-500">
                Take new photos or choose from your gallery
              </p>
            </div>

            {/* Hidden file input */}
            <input
              ref={fileInputRef}
              type="file"
              accept="image/jpeg,image/png,image/heic,image/webp"
              multiple
              capture="environment"
              onChange={handleFileChange}
              className="hidden"
            />

            {/* Take Photo / Choose buttons */}
            <div className="grid grid-cols-2 gap-3">
              <button
                type="button"
                onClick={() => {
                  if (fileInputRef.current) {
                    fileInputRef.current.setAttribute("capture", "environment");
                    fileInputRef.current.click();
                  }
                }}
                className="flex flex-col items-center justify-center gap-2 rounded-xl border-2 border-emerald-200 bg-emerald-50 p-6 text-emerald-700 font-medium transition-colors active:bg-emerald-100"
              >
                <Camera className="h-8 w-8" />
                <span className="text-sm">Take Photo</span>
              </button>

              <button
                type="button"
                onClick={() => {
                  if (fileInputRef.current) {
                    fileInputRef.current.removeAttribute("capture");
                    fileInputRef.current.click();
                  }
                }}
                className="flex flex-col items-center justify-center gap-2 rounded-xl border-2 border-slate-200 bg-slate-50 p-6 text-slate-700 font-medium transition-colors active:bg-slate-100"
              >
                <ImagePlus className="h-8 w-8" />
                <span className="text-sm">Choose from Gallery</span>
              </button>
            </div>

            {/* Inline error */}
            {errorMessage && state === "ready" && (
              <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-center">
                <p className="text-sm text-red-700">{errorMessage}</p>
              </div>
            )}

            {/* Preview grid */}
            {selectedFiles.length > 0 && (
              <div>
                <p className="text-sm font-medium text-slate-700 mb-2">
                  {selectedFiles.length} photo
                  {selectedFiles.length !== 1 ? "s" : ""} selected
                </p>
                <div className="grid grid-cols-3 gap-2">
                  {previewUrls.map((url, i) => (
                    <div
                      key={i}
                      className="relative aspect-square rounded-lg overflow-hidden bg-slate-100"
                    >
                      <img
                        src={url}
                        alt={`Preview ${i + 1}`}
                        className="h-full w-full object-cover"
                      />
                      <button
                        type="button"
                        onClick={() => handleRemoveFile(i)}
                        className="absolute top-1 right-1 flex h-6 w-6 items-center justify-center rounded-full bg-black/50 text-white transition-colors active:bg-black/70"
                      >
                        <X className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Upload button */}
            <button
              type="button"
              disabled={selectedFiles.length === 0}
              onClick={handleUpload}
              className="w-full rounded-xl bg-emerald-600 py-4 text-base font-bold text-white transition-colors active:bg-emerald-700 disabled:bg-slate-200 disabled:text-slate-400 disabled:cursor-not-allowed"
            >
              Upload {selectedFiles.length > 0 ? selectedFiles.length : ""}{" "}
              Photo{selectedFiles.length !== 1 ? "s" : ""}
            </button>

            <p className="text-center text-xs text-slate-400">
              Accepted formats: JPG, PNG, HEIC, WebP
            </p>
          </div>
        )}

        {/* ════════════════════════════════════════════
            Uploading state
            ════════════════════════════════════════════ */}
        {state === "uploading" && (
          <div className="flex flex-col items-center justify-center py-16">
            <Loader2 className="h-10 w-10 animate-spin text-emerald-500 mb-4" />
            <h2 className="text-lg font-semibold text-slate-900 mb-2">
              Uploading...
            </h2>
            <p className="text-sm text-slate-500 mb-6">
              {selectedFiles.length} photo
              {selectedFiles.length !== 1 ? "s" : ""}
            </p>

            {/* Progress bar */}
            <div className="w-full max-w-xs">
              <div className="h-2 w-full overflow-hidden rounded-full bg-slate-200">
                <div
                  className="h-full rounded-full bg-emerald-500 transition-all duration-300 ease-out"
                  style={{ width: `${uploadProgress}%` }}
                />
              </div>
              <p className="mt-2 text-center text-xs text-slate-400">
                {uploadProgress}%
              </p>
            </div>
          </div>
        )}

        {/* ════════════════════════════════════════════
            Success state
            ════════════════════════════════════════════ */}
        {state === "success" && (
          <div className="flex flex-col items-center justify-center py-16 text-center">
            <div className="mb-4 flex h-20 w-20 items-center justify-center rounded-full bg-emerald-50">
              <CheckCircle2 className="h-10 w-10 text-emerald-500" />
            </div>
            <h2 className="text-xl font-bold text-slate-900 mb-2">Done!</h2>
            <p className="text-sm text-slate-500 max-w-xs">
              Photos added to your property. You can close this page or upload
              more.
            </p>

            <button
              type="button"
              onClick={() => {
                setSelectedFiles([]);
                setPreviewUrls([]);
                setErrorMessage("");
                setUploadProgress(0);
                setState("ready");
              }}
              className="mt-6 rounded-xl border-2 border-emerald-200 bg-white px-6 py-3 text-sm font-semibold text-emerald-700 transition-colors active:bg-emerald-50"
            >
              Upload More Photos
            </button>
          </div>
        )}
      </main>
    </div>
  );
}
