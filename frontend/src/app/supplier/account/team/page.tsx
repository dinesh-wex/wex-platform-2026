"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import {
  ArrowLeft,
  UserPlus,
  Shield,
  Trash2,
  Check,
  X,
} from "lucide-react";
import { api } from "@/lib/api";
import { useSupplier } from "@/components/supplier/SupplierAuthProvider";
import StatusBadge from "@/components/supplier/StatusBadge";
import { demoTeam } from "@/lib/supplier-demo-data";
import type { TeamMember, TeamRole } from "@/types/supplier";

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
/*  Role Badge                                                         */
/* ------------------------------------------------------------------ */

function RoleBadge({ role }: { role: TeamRole }) {
  const isAdmin = role === "admin";
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium ${
        isAdmin
          ? "bg-indigo-50 text-indigo-700"
          : "bg-slate-100 text-slate-600"
      }`}
    >
      {isAdmin && <Shield className="w-3 h-3" />}
      {isAdmin ? "Admin" : "Member"}
    </span>
  );
}

/* ------------------------------------------------------------------ */
/*  Page Component                                                     */
/* ------------------------------------------------------------------ */

export default function TeamPage() {
  const { supplier } = useSupplier();

  const [toast, setToast] = useState<Toast | null>(null);
  const showToast = (message: string, type: "success" | "error") =>
    setToast({ message, type });

  const [team, setTeam] = useState<TeamMember[]>(demoTeam);
  const [loading, setLoading] = useState(true);

  // ---- Invite form ----
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState<TeamRole>("member");
  const [inviting, setInviting] = useState(false);

  // ---- Confirm removal ----
  const [removeTarget, setRemoveTarget] = useState<TeamMember | null>(null);

  // ---- Role change tracking ----
  const [changingRoleId, setChangingRoleId] = useState<string | null>(null);

  // ---- Fetch team ----
  const fetchTeam = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.getTeam();
      setTeam(Array.isArray(data) ? data : data.members ?? demoTeam);
    } catch {
      setTeam(demoTeam);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchTeam();
  }, [fetchTeam]);

  // ---- Invite handler ----
  const handleInvite = async () => {
    if (!inviteEmail.trim()) {
      showToast("Please enter an email address.", "error");
      return;
    }
    setInviting(true);
    try {
      const result = await api.inviteTeamMember({ email: inviteEmail, role: inviteRole });
      // Add new member to the local list
      const newMember: TeamMember = result ?? {
        id: `tm-${Date.now()}`,
        name: inviteEmail.split("@")[0],
        email: inviteEmail,
        role: inviteRole,
        status: "invited",
        invited_at: new Date().toISOString(),
      };
      setTeam((prev) => [...prev, newMember]);
      setInviteEmail("");
      setInviteRole("member");
      showToast(`Invitation sent to ${inviteEmail}.`, "success");
    } catch {
      showToast("Failed to send invitation. Please try again.", "error");
    } finally {
      setInviting(false);
    }
  };

  // ---- Remove handler ----
  const handleRemove = async (member: TeamMember) => {
    try {
      await api.removeTeamMember(member.id);
      setTeam((prev) => prev.filter((m) => m.id !== member.id));
      showToast(`${member.name} has been removed.`, "success");
    } catch {
      showToast("Failed to remove team member.", "error");
    } finally {
      setRemoveTarget(null);
    }
  };

  // ---- Role change handler ----
  const handleRoleChange = async (member: TeamMember, newRole: TeamRole) => {
    setChangingRoleId(member.id);
    try {
      await api.updateTeamMember(member.id, { role: newRole });
      setTeam((prev) =>
        prev.map((m) => (m.id === member.id ? { ...m, role: newRole } : m))
      );
      showToast(`${member.name} is now ${newRole === "admin" ? "an Admin" : "a Member"}.`, "success");
    } catch {
      showToast("Failed to change role.", "error");
    } finally {
      setChangingRoleId(null);
    }
  };

  const isCurrentUser = (member: TeamMember) =>
    supplier?.email === member.email;

  return (
    <div className="min-h-screen bg-slate-50">
      {toast && <ToastBanner toast={toast} onDismiss={() => setToast(null)} />}

      {/* Remove Confirmation Modal */}
      {removeTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4">
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className="bg-white rounded-xl shadow-xl max-w-md w-full p-6"
          >
            <h3 className="text-lg font-semibold text-slate-900 mb-2">
              Remove Team Member
            </h3>
            <p className="text-sm text-slate-600 mb-6">
              Are you sure you want to remove{" "}
              <span className="font-medium text-slate-900">{removeTarget.name}</span>?
              They will lose access to the dashboard immediately.
            </p>
            <div className="flex justify-end gap-3">
              <button
                onClick={() => setRemoveTarget(null)}
                className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() => handleRemove(removeTarget)}
                className="rounded-lg bg-red-600 text-white px-4 py-2 text-sm font-medium hover:bg-red-700 transition-colors"
              >
                Remove
              </button>
            </div>
          </motion.div>
        </div>
      )}

      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
        {/* ---- Header ---- */}
        <motion.div
          initial={{ opacity: 0, y: -12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
        >
          <Link
            href="/supplier/account"
            className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-700 transition-colors mb-4"
          >
            <ArrowLeft className="w-4 h-4" />
            Back to Account
          </Link>
          <h1 className="text-2xl sm:text-3xl font-bold text-slate-900">
            Team Management
          </h1>
          <p className="text-slate-500 mt-1">
            Manage who has access to your supplier dashboard.
          </p>
        </motion.div>

        {/* ---- Team Members Table (Desktop) ---- */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, delay: 0.05 }}
          className="hidden md:block bg-white rounded-xl shadow-sm overflow-hidden"
        >
          <table className="w-full">
            <thead>
              <tr className="border-b border-slate-100">
                <th className="text-left text-xs font-medium text-slate-500 uppercase tracking-wide px-6 py-4">
                  Member
                </th>
                <th className="text-left text-xs font-medium text-slate-500 uppercase tracking-wide px-6 py-4">
                  Email
                </th>
                <th className="text-left text-xs font-medium text-slate-500 uppercase tracking-wide px-6 py-4">
                  Role
                </th>
                <th className="text-left text-xs font-medium text-slate-500 uppercase tracking-wide px-6 py-4">
                  Status
                </th>
                <th className="text-right text-xs font-medium text-slate-500 uppercase tracking-wide px-6 py-4">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {loading ? (
                <tr>
                  <td colSpan={5} className="text-center py-12 text-slate-400">
                    Loading...
                  </td>
                </tr>
              ) : (
                team.map((member, i) => {
                  const isSelf = isCurrentUser(member);

                  return (
                    <motion.tr
                      key={member.id}
                      initial={{ opacity: 0, y: 8 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ duration: 0.3, delay: i * 0.04 }}
                      className={`transition-colors ${
                        isSelf ? "bg-emerald-50/30" : "hover:bg-slate-50/50"
                      }`}
                    >
                      <td className="px-6 py-4">
                        <span className="text-sm font-medium text-slate-900">
                          {member.name}
                        </span>
                        {isSelf && (
                          <span className="ml-1.5 text-xs text-emerald-600 font-medium">
                            (you)
                          </span>
                        )}
                      </td>
                      <td className="px-6 py-4 text-sm text-slate-600">
                        {member.email}
                      </td>
                      <td className="px-6 py-4">
                        <RoleBadge role={member.role} />
                      </td>
                      <td className="px-6 py-4">
                        <StatusBadge status={member.status} size="sm" />
                      </td>
                      <td className="px-6 py-4">
                        {!isSelf && (
                          <div className="flex items-center justify-end gap-2">
                            <select
                              value={member.role}
                              onChange={(e) =>
                                handleRoleChange(member, e.target.value as TeamRole)
                              }
                              disabled={changingRoleId === member.id}
                              className="rounded-lg border border-slate-200 px-2 py-1.5 text-xs text-slate-700 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent disabled:opacity-50"
                            >
                              <option value="admin">Admin</option>
                              <option value="member">Member</option>
                            </select>
                            <button
                              onClick={() => setRemoveTarget(member)}
                              className="rounded-lg border border-red-200 p-1.5 text-red-600 hover:bg-red-50 transition-colors"
                              title="Remove member"
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                            </button>
                          </div>
                        )}
                      </td>
                    </motion.tr>
                  );
                })
              )}
            </tbody>
          </table>
        </motion.div>

        {/* ---- Team Members Cards (Mobile) ---- */}
        <div className="md:hidden space-y-3">
          {loading ? (
            <div className="text-center py-12 text-slate-400">Loading...</div>
          ) : (
            team.map((member, i) => {
              const isSelf = isCurrentUser(member);

              return (
                <motion.div
                  key={member.id}
                  initial={{ opacity: 0, y: 12 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.3, delay: i * 0.05 }}
                  className={`bg-white rounded-xl shadow-sm p-4 ${
                    isSelf ? "ring-1 ring-emerald-200" : ""
                  }`}
                >
                  <div className="flex items-start justify-between mb-3">
                    <div>
                      <p className="text-sm font-semibold text-slate-900">
                        {member.name}
                        {isSelf && (
                          <span className="ml-1.5 text-xs text-emerald-600 font-medium">
                            (you)
                          </span>
                        )}
                      </p>
                      <p className="text-xs text-slate-500 mt-0.5">
                        {member.email}
                      </p>
                    </div>
                    <StatusBadge status={member.status} size="sm" />
                  </div>

                  <div className="flex items-center justify-between">
                    <RoleBadge role={member.role} />
                    {!isSelf && (
                      <div className="flex items-center gap-2">
                        <select
                          value={member.role}
                          onChange={(e) =>
                            handleRoleChange(member, e.target.value as TeamRole)
                          }
                          disabled={changingRoleId === member.id}
                          className="rounded-lg border border-slate-200 px-2 py-1.5 text-xs text-slate-700 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent disabled:opacity-50"
                        >
                          <option value="admin">Admin</option>
                          <option value="member">Member</option>
                        </select>
                        <button
                          onClick={() => setRemoveTarget(member)}
                          className="rounded-lg border border-red-200 p-1.5 text-red-600 hover:bg-red-50 transition-colors"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    )}
                  </div>
                </motion.div>
              );
            })
          )}
        </div>

        {/* ---- Invite Member Section ---- */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, delay: 0.1 }}
          className="bg-white rounded-xl shadow-sm p-6"
        >
          <div className="flex items-center gap-2 mb-6">
            <UserPlus className="w-5 h-5 text-slate-600" />
            <h2 className="text-lg font-semibold text-slate-900">
              Invite Team Member
            </h2>
          </div>

          <div className="flex flex-col sm:flex-row gap-3">
            <div className="flex-1">
              <label className="block text-sm font-medium text-slate-700 mb-1">
                Email
              </label>
              <input
                type="email"
                placeholder="colleague@company.com"
                value={inviteEmail}
                onChange={(e) => setInviteEmail(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleInvite()}
                className="w-full rounded-lg border border-slate-200 px-3 py-2.5 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent"
              />
            </div>
            <div className="sm:w-36">
              <label className="block text-sm font-medium text-slate-700 mb-1">
                Role
              </label>
              <select
                value={inviteRole}
                onChange={(e) => setInviteRole(e.target.value as TeamRole)}
                className="w-full rounded-lg border border-slate-200 px-3 py-2.5 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent"
              >
                <option value="admin">Admin</option>
                <option value="member">Member</option>
              </select>
            </div>
            <div className="flex items-end">
              <button
                onClick={handleInvite}
                disabled={inviting}
                className="w-full sm:w-auto inline-flex items-center justify-center gap-2 rounded-lg bg-emerald-600 text-white px-5 py-2.5 text-sm font-medium hover:bg-emerald-700 transition-colors disabled:opacity-50"
              >
                <UserPlus className="w-4 h-4" />
                {inviting ? "Sending..." : "Send Invite"}
              </button>
            </div>
          </div>
        </motion.div>
      </div>
    </div>
  );
}
