"use client";
import { FormEvent, useEffect, useState } from "react";

type Api = <T>(path: string, options?: RequestInit, token?: string) => Promise<T>;
export function EducationCohortDelete({ api, token, cohort, onDeleted }: { api: Api; token: string; cohort: { id: string; name: string; version: number }; onDeleted: () => void }) {
  const [configured, setConfigured] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    api<{ configured: boolean }>("v1/pm/founder-delete-password/status", { signal: controller.signal }, token)
      .then((result) => { if (!controller.signal.aborted) setConfigured(result.configured); })
      .catch((cause) => { if (!controller.signal.aborted) setError(cause.message || "无法读取删除密码状态"); });
    return () => controller.abort();
  }, [api, token]);
  async function configure(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (busy) return;
    const form = event.currentTarget;
    const values = Object.fromEntries(new FormData(form));
    if (values.new_password !== values.confirm_password) { setError("两次输入的删除密码不一致"); return; }
    setBusy(true); setError("");
    try {
      await api("v1/pm/founder-delete-password", { method: "PATCH", body: JSON.stringify({ current_login_password: values.current_login_password, new_password: values.new_password }), signal: AbortSignal.timeout(20000) }, token);
      form.reset(); setConfigured(true); setMessage("删除密码已设置，与项目删除共用。");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "密码设置失败"); }
    finally { setBusy(false); }
  }
  async function remove(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (busy) return;
    const form = event.currentTarget;
    const values = Object.fromEntries(new FormData(form));
    if (String(values.confirm_name).trim() !== cohort.name) { setError("请完整输入当前班期名称"); return; }
    if (!window.confirm(`确认删除班期“${cohort.name}”？该班期及其学员、费用、人员和评估将退出日常页面及教培汇总，历史记录保留供追溯。`)) return;
    setBusy(true); setError("");
    try {
      await api(`v1/pm/education/cohorts/${cohort.id}/founder-delete`, { method: "POST", body: JSON.stringify({ ...values, version: cohort.version }), signal: AbortSignal.timeout(20000) }, token);
      form.reset(); onDeleted();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "删除失败，请刷新核对后重试"); }
    finally { setBusy(false); }
  }
  return <details className="educationCohortDelete"><summary>创始人权限 · 删除班期</summary>
    <p className="educationHint">删除后该班期及关联资料不再显示，也不再计入教培汇总。底层记录和审计保留，不会删除登录账号。本页面不提供恢复按钮，请谨慎操作。</p>
    {error && <p role="alert" className="educationError">{error}</p>}{message && <p role="status">{message}</p>}
    {configured === null && <p>正在读取删除密码状态…</p>}
    {configured && <form className="educationForm" autoComplete="off" onSubmit={(event) => void remove(event)}>
      <label>确认班期名称<input name="confirm_name" required maxLength={120} autoComplete="off" placeholder={cohort.name} /></label>
      <label>删除密码<input name="deletion_password" type="password" required maxLength={200} autoComplete="off" /></label>
      <label className="educationWide">删除原因<input name="reason" required minLength={2} maxLength={1000} /></label>
      <button className="primaryButton" disabled={busy}>{busy ? "正在处理…" : "验证密码并删除班期"}</button>
    </form>}
    {configured === false && <form className="educationForm" onSubmit={(event) => void configure(event)}>
      <p className="educationWide">首次使用请设置独立删除密码，不能与登录密码相同；已设置过项目删除密码的账号直接共用，无需重复设置。</p>
      <label>当前登录密码<input name="current_login_password" type="password" required maxLength={200} autoComplete="current-password" /></label>
      <label>新删除密码<input name="new_password" type="password" required minLength={8} maxLength={200} autoComplete="new-password" /></label>
      <label>再次输入删除密码<input name="confirm_password" type="password" required minLength={8} maxLength={200} autoComplete="new-password" /></label>
      <button className="primaryButton" disabled={busy}>设置删除密码</button>
    </form>}
  </details>;
}
