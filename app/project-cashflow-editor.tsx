"use client";

import { FormEvent, useState } from "react";

export type CashflowPlanValues = {
  direction: string;
  due_date: string;
  amount: string;
  counterparty: string | null;
  note: string | null;
};

export function ProjectCashflowEditor({ item, onSave }: {
  item: { id: string; direction: string; due_date: string; amount: string | number | null; counterparty?: string | null; note?: string | null };
  onSave: (id: string, values: CashflowPlanValues) => Promise<void>;
}) {
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    setSaving(true);
    setError("");
    setMessage("");
    try {
      await onSave(item.id, {
        direction: String(data.get("direction")), due_date: String(data.get("due_date")),
        amount: String(data.get("amount")), counterparty: String(data.get("counterparty") || "").trim() || null,
        note: String(data.get("note") || "").trim() || null,
      });
      setEditing(false);
      setMessage("计划已更新");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "保存失败，请重试");
    } finally {
      setSaving(false);
    }
  }

  return <div className="pmCashflowEditor">
    {!editing && <button type="button" className="secondaryButton" onClick={() => { setEditing(true); setMessage(""); setError(""); }}>修改计划</button>}
    {message && <p role="status">{message}</p>}
    {editing && <form className="businessForm" onSubmit={submit}>
      <strong>修改应收／应付计划</strong>
      <label>收付方向<select name="direction" defaultValue={item.direction}><option value="receivable">应收</option><option value="payable">应付</option></select></label>
      <label>计划日期<input name="due_date" type="date" defaultValue={item.due_date} required /></label>
      <label>计划金额（元）<input name="amount" type="number" min="0.01" step="0.01" defaultValue={item.amount ?? ""} required /></label>
      <label>对方单位<input name="counterparty" maxLength={240} defaultValue={item.counterparty || ""} /></label>
      <label>备注<textarea name="note" maxLength={1000} rows={2} defaultValue={item.note || ""} /></label>
      <small>修改计划不改变财务已确认的实际收付款。</small>
      {error && <p className="formError" role="alert">{error}</p>}
      <div className="pmCashflowEditorActions"><button type="submit" disabled={saving}>{saving ? "保存中…" : "保存修改"}</button><button type="button" disabled={saving} onClick={() => setEditing(false)}>取消</button></div>
    </form>}
  </div>;
}
