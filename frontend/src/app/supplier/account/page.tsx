"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import {
  User,
  Lock,
  Bell,
  CreditCard,
  ChevronRight,
  Users,
  Save,
  AlertTriangle,
  Check,
  X,
} from "lucide-react";
import { api } from "@/lib/api";
import { useSupplier } from "@/components/supplier/SupplierAuthProvider";
import { demoNotificationPrefs } from "@/lib/supplier-demo-data";
import type { NotificationPrefs } from "@/types/supplier";

/* ------------------------------------------------------------------ */
/*  Toast                                                              */
/* ------------------------------------------------------------------ */

interface Toast {
  message: string;
  type: "success" | "error";
}

function ToastBanner({ toast, onDismiss }: { toast: Toast; onDismiss: () => void }) {
  useEffect(() => {
    const t = setTimeout(onDismiss, 4000);
    return () => clearTimeout(t);
  }, [onDismiss]);

  return (
    <motion.div
      initial={{ opacity: 0, y: -20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -20 }}
      className={`fixed top-4 right-4 z-50 flex items-center gap-2 rounded-lg px-4 py-3 text-sm font-medium shadow-lg ${
        toast.type === "success"
          ? "bg-emerald-600 text-white"
          : "bg-red-600 text-white"
      }`}
    >
      {toast.type === "success" ? <Check className="w-4 h-4" /> : <X className="w-4 h-4" />}
      {toast.message}
      <button onClick={onDismiss} className="ml-2 opacity-70 hover:opacity-100">
        <X className="w-3.5 h-3.5" />
      </button>
    </motion.div>
  );
}

/* ------------------------------------------------------------------ */
/*  Toggle Switch                                                      */
/* ------------------------------------------------------------------ */

function Toggle({
  enabled,
  onChange,
  disabled,
}: {
  enabled: boolean;
  onChange: (val: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={enabled}
      disabled={disabled}
      onClick={() => onChange(!enabled)}
      className={`relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:ring-offset-2 ${
        enabled ? "bg-emerald-600" : "bg-slate-200"
      } ${disabled ? "opacity-50 cursor-not-allowed" : ""}`}
    >
      <span
        className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${
          enabled ? "translate-x-5" : "translate-x-0"
        }`}
      />
    </button>
  );
}

/* ------------------------------------------------------------------ */
/*  Section wrapper                                                    */
/* ------------------------------------------------------------------ */

function Section({
  title,
  icon: Icon,
  delay,
  children,
}: {
  title: string;
  icon: React.ElementType;
  delay: number;
  children: React.ReactNode;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay }}
      className="bg-white rounded-xl shadow-sm p-6"
    >
      <div className="flex items-center gap-2 mb-6">
        <Icon className="w-5 h-5 text-slate-600" />
        <h2 className="text-lg font-semibold text-slate-900">{title}</h2>
      </div>
      {children}
    </motion.div>
  );
}

/* ------------------------------------------------------------------ */
/*  Notification preference row definition                             */
/* ------------------------------------------------------------------ */

interface NotifRow {
  label: string;
  smsKey?: keyof NotificationPrefs;
  emailKey?: keyof NotificationPrefs;
}

const NOTIFICATION_ROWS: NotifRow[] = [
  { label: "New inquiries", smsKey: "deal_pings_sms", emailKey: "deal_pings_email" },
  { label: "Tour requests", smsKey: "tour_requests_sms", emailKey: "tour_requests_email" },
  { label: "Agreement ready", emailKey: "agreement_ready_email" },
  { label: "Payment deposited", emailKey: "payment_deposited_email" },
  { label: "Profile suggestions", emailKey: "profile_suggestions_email" },
  { label: "Monthly summary", emailKey: "monthly_summary_email" },
];

/* ------------------------------------------------------------------ */
/*  Page Component                                                     */
/* ------------------------------------------------------------------ */

export default function AccountPage() {
  const { supplier } = useSupplier();

  const [toast, setToast] = useState<Toast | null>(null);
  const showToast = (message: string, type: "success" | "error") =>
    setToast({ message, type });

  // ---- Profile form ----
  const [profileForm, setProfileForm] = useState({
    name: "",
    email: "",
    phone: "",
    company: "",
  });
  const [profileSaving, setProfileSaving] = useState(false);

  useEffect(() => {
    if (supplier) {
      setProfileForm({
        name: supplier.name || "",
        email: supplier.email || "",
        phone: supplier.phone || "",
        company: supplier.company || "",
      });
    }
  }, [supplier]);

  const handleProfileSave = async () => {
    setProfileSaving(true);
    try {
      await api.updateAccount({
        name: profileForm.name,
        email: profileForm.email,
        phone: profileForm.phone,
        company: profileForm.company,
      });
      showToast("Profile updated successfully.", "success");
    } catch {
      showToast("Failed to update profile. Please try again.", "error");
    } finally {
      setProfileSaving(false);
    }
  };

  // ---- Password form ----
  const [passwordForm, setPasswordForm] = useState({
    current_password: "",
    new_password: "",
    confirm_password: "",
  });
  const [passwordSaving, setPasswordSaving] = useState(false);

  const handlePasswordChange = async () => {
    if (passwordForm.new_password !== passwordForm.confirm_password) {
      showToast("New passwords do not match.", "error");
      return;
    }
    if (passwordForm.new_password.length < 8) {
      showToast("Password must be at least 8 characters.", "error");
      return;
    }
    setPasswordSaving(true);
    try {
      await api.changePassword({
        current_password: passwordForm.current_password,
        new_password: passwordForm.new_password,
      });
      showToast("Password changed successfully.", "success");
      setPasswordForm({ current_password: "", new_password: "", confirm_password: "" });
    } catch {
      showToast("Failed to change password. Check your current password.", "error");
    } finally {
      setPasswordSaving(false);
    }
  };

  // ---- Notification prefs ----
  const [notifPrefs, setNotifPrefs] = useState<NotificationPrefs>(demoNotificationPrefs);
  const [smsWarning, setSmsWarning] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const prefs = await api.getNotificationPrefs();
        if (prefs) setNotifPrefs(prefs);
      } catch {
        setNotifPrefs(demoNotificationPrefs);
      }
    })();
  }, []);

  const handleNotifToggle = async (key: keyof NotificationPrefs, value: boolean) => {
    // Warning for disabling deal pings SMS
    if (key === "deal_pings_sms" && !value) {
      setSmsWarning(true);
      return;
    }

    const updated = { ...notifPrefs, [key]: value };
    setNotifPrefs(updated);
    try {
      await api.updateNotificationPrefs({ [key]: value });
    } catch {
      // Revert on failure
      setNotifPrefs(notifPrefs);
      showToast("Failed to update notification preference.", "error");
    }
  };

  const confirmDisableDealPingSms = async () => {
    setSmsWarning(false);
    const updated = { ...notifPrefs, deal_pings_sms: false };
    setNotifPrefs(updated);
    try {
      await api.updateNotificationPrefs({ deal_pings_sms: false });
    } catch {
      setNotifPrefs(notifPrefs);
      showToast("Failed to update notification preference.", "error");
    }
  };

  // ---- Input helper ----
  const inputClass =
    "w-full rounded-lg border border-slate-200 px-3 py-2.5 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent";

  return (
    <div className="min-h-screen bg-slate-50">
      {toast && <ToastBanner toast={toast} onDismiss={() => setToast(null)} />}

      {/* SMS Warning Modal */}
      {smsWarning && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4">
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className="bg-white rounded-xl shadow-xl max-w-md w-full p-6"
          >
            <div className="flex items-center gap-3 mb-4">
              <div className="flex items-center justify-center w-10 h-10 rounded-full bg-amber-100">
                <AlertTriangle className="w-5 h-5 text-amber-600" />
              </div>
              <h3 className="text-lg font-semibold text-slate-900">
                Disable Inquiry SMS?
              </h3>
            </div>
            <p className="text-sm text-slate-600 mb-6">
              New inquiries have a 12-hour response window. SMS ensures you
              don&apos;t miss opportunities. Are you sure you want to disable
              SMS notifications for new inquiries?
            </p>
            <div className="flex justify-end gap-3">
              <button
                onClick={() => setSmsWarning(false)}
                className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 transition-colors"
              >
                Keep Enabled
              </button>
              <button
                onClick={confirmDisableDealPingSms}
                className="rounded-lg bg-red-600 text-white px-4 py-2 text-sm font-medium hover:bg-red-700 transition-colors"
              >
                Disable Anyway
              </button>
            </div>
          </motion.div>
        </div>
      )}

      <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
        {/* ---- Header ---- */}
        <motion.div
          initial={{ opacity: 0, y: -12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
        >
          <h1 className="text-2xl sm:text-3xl font-bold text-slate-900">
            Account Settings
          </h1>
          <p className="text-slate-500 mt-1">
            Manage your profile, security, and preferences.
          </p>
        </motion.div>

        {/* ---- Profile Section ---- */}
        <Section title="Profile" icon={User} delay={0.05}>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">
                Name
              </label>
              <input
                type="text"
                value={profileForm.name}
                onChange={(e) => setProfileForm((f) => ({ ...f, name: e.target.value }))}
                className={inputClass}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">
                Email
              </label>
              <input
                type="email"
                value={profileForm.email}
                onChange={(e) => setProfileForm((f) => ({ ...f, email: e.target.value }))}
                className={inputClass}
              />
              <p className="text-xs text-slate-400 mt-1">
                Changing email requires verification.
              </p>
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">
                Phone
              </label>
              <input
                type="tel"
                value={profileForm.phone}
                onChange={(e) => setProfileForm((f) => ({ ...f, phone: e.target.value }))}
                className={inputClass}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">
                Company Name
              </label>
              <input
                type="text"
                value={profileForm.company}
                onChange={(e) => setProfileForm((f) => ({ ...f, company: e.target.value }))}
                className={inputClass}
              />
            </div>
          </div>
          <div className="mt-6 flex justify-end">
            <button
              onClick={handleProfileSave}
              disabled={profileSaving}
              className="inline-flex items-center gap-2 rounded-lg bg-emerald-600 text-white px-5 py-2.5 text-sm font-medium hover:bg-emerald-700 transition-colors disabled:opacity-50"
            >
              <Save className="w-4 h-4" />
              {profileSaving ? "Saving..." : "Save Changes"}
            </button>
          </div>
        </Section>

        {/* ---- Change Password Section ---- */}
        <Section title="Change Password" icon={Lock} delay={0.1}>
          <div className="space-y-4 max-w-sm">
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">
                Current Password
              </label>
              <input
                type="password"
                value={passwordForm.current_password}
                onChange={(e) =>
                  setPasswordForm((f) => ({ ...f, current_password: e.target.value }))
                }
                className={inputClass}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">
                New Password
              </label>
              <input
                type="password"
                value={passwordForm.new_password}
                onChange={(e) =>
                  setPasswordForm((f) => ({ ...f, new_password: e.target.value }))
                }
                className={inputClass}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">
                Confirm New Password
              </label>
              <input
                type="password"
                value={passwordForm.confirm_password}
                onChange={(e) =>
                  setPasswordForm((f) => ({ ...f, confirm_password: e.target.value }))
                }
                className={inputClass}
              />
            </div>
          </div>
          <div className="mt-6 flex justify-end">
            <button
              onClick={handlePasswordChange}
              disabled={passwordSaving}
              className="inline-flex items-center gap-2 rounded-lg bg-emerald-600 text-white px-5 py-2.5 text-sm font-medium hover:bg-emerald-700 transition-colors disabled:opacity-50"
            >
              <Lock className="w-4 h-4" />
              {passwordSaving ? "Changing..." : "Change Password"}
            </button>
          </div>
        </Section>

        {/* ---- Notification Preferences Section ---- */}
        <Section title="Notification Preferences" icon={Bell} delay={0.15}>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-slate-100">
                  <th className="text-left text-xs font-medium text-slate-500 uppercase tracking-wide py-3 pr-4">
                    Notification
                  </th>
                  <th className="text-center text-xs font-medium text-slate-500 uppercase tracking-wide py-3 px-4">
                    SMS
                  </th>
                  <th className="text-center text-xs font-medium text-slate-500 uppercase tracking-wide py-3 pl-4">
                    Email
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {NOTIFICATION_ROWS.map((row) => (
                  <tr key={row.label}>
                    <td className="py-3 pr-4 text-sm text-slate-700">{row.label}</td>
                    <td className="py-3 px-4 text-center">
                      {row.smsKey ? (
                        <Toggle
                          enabled={notifPrefs[row.smsKey]}
                          onChange={(val) => handleNotifToggle(row.smsKey!, val)}
                        />
                      ) : (
                        <span className="text-slate-300">&mdash;</span>
                      )}
                    </td>
                    <td className="py-3 pl-4 text-center">
                      {row.emailKey ? (
                        <Toggle
                          enabled={notifPrefs[row.emailKey]}
                          onChange={(val) => handleNotifToggle(row.emailKey!, val)}
                        />
                      ) : (
                        <span className="text-slate-300">&mdash;</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Section>

        {/* ---- Payment Info Section ---- */}
        <Section title="Payment Information" icon={CreditCard} delay={0.2}>
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-slate-700">
                Bank Account: <span className="font-mono font-medium">****4521</span>
              </p>
              <p className="text-xs text-slate-400 mt-0.5">
                Deposits are sent to this account on the 15th of each month.
              </p>
            </div>
            <button
              onClick={() =>
                alert(
                  "Contact support@wex.com to update bank information."
                )
              }
              className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 transition-colors"
            >
              Update Bank Info
            </button>
          </div>
        </Section>

        {/* ---- Team Management Link ---- */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, delay: 0.25 }}
        >
          <Link
            href="/supplier/account/team"
            className="flex items-center justify-between bg-white rounded-xl shadow-sm p-6 hover:shadow-md transition-shadow group"
          >
            <div className="flex items-center gap-3">
              <Users className="w-5 h-5 text-slate-600" />
              <div>
                <p className="text-sm font-semibold text-slate-900">
                  Team Management
                </p>
                <p className="text-xs text-slate-500">
                  Manage your team members and permissions.
                </p>
              </div>
            </div>
            <ChevronRight className="w-5 h-5 text-slate-400 group-hover:text-slate-600 transition-colors" />
          </Link>
        </motion.div>
      </div>
    </div>
  );
}
