"use client";

import { FormEvent, useEffect, useRef, useState } from "react";

type Api = <T>(path: string, options?: RequestInit, token?: string) => Promise<T>;
type LedgerRow = { id: string; cohort_id: string; cohort_name: string; name: string; registration_date: string; game: string; course_period: string; study_start: string; study_end: string; receivable: string; received: string; arrears: string; overpayment: string };
type Ledger = { items: LedgerRow[]; summary: { student_count: number; receivable: string; received: string; cost: string; arrears: string; overpayment: string }; has_more: boolean; scope: string };
type Installment = { id: string; label: string; due_on: string; amount: string; paid: string; remaining: string; note: string; active: boolean; version: number };
type Payment = { id: string; direction: "receipt" | "refund"; amount: string; occurred_on: string; method: string; account: string; note: string; installment_id: string | null; creator_name: string; version: number };
type PaymentLedger = { installments: Installment[]; payments: Payment[]; methods: string[]; summary: { receivable: string; net_received: string; arrears: string; overpayment: string; plan_total: string; plan_difference: string } };

const money = (value: string | number) => Number(value).toLocaleString("zh-CN", { style: "currency", currency: "CNY" });
const today = () => new Date().toLocaleDateString("sv-SE");
const periodNames: Record<string, string> = { "8_days": "八天七晚", "1_month": "一个月 29天", "3_months": "三个月 87天" };

export function EducationLedgerOverview({ api, token, cohorts, onOpenCohort }: { api: Api; token: string; cohorts: { id: string; name: string }[]; onOpenCohort: (id: string) => void }) {
  const [data, setData] = useState<Ledger | null>(null);
  const [query, setQuery] = useState({ keyword: "", cohort_id: "", payment_status: "all" });
  const [applied, setApplied] = useState(query);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function load(offset = 0, append = false) {
    setBusy(true); setError("");
    const params = new URLSearchParams({ offset: String(offset), limit: "20", ...applied });
    if (!applied.cohort_id) params.delete("cohort_id");
    try {
      const result = await api<Ledger>(`v1/pm/education/ledger?${params}`, {}, token);
      setData((current) => append && current ? { ...result, items: [...current.items, ...result.items] } : result);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "综合台账加载失败"); }
    finally { setBusy(false); }
  }
  useEffect(() => {
    const controller = new AbortController();
    const params = new URLSearchParams({ offset: "0", limit: "20", ...applied });
    if (!applied.cohort_id) params.delete("cohort_id");
    api<Ledger>(`v1/pm/education/ledger?${params}`, { signal: controller.signal }, token)
      .then((result) => { if (!controller.signal.aborted) setData(result); })
      .catch((cause) => { if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : "综合台账加载失败"); });
    return () => controller.abort();
  }, [api, token, applied]);

  function search(event: FormEvent) { event.preventDefault(); setApplied({ ...query, keyword: query.keyword.trim() }); }
  return <section className="educationLedger">
    <section className="panel educationLedgerIntro">
      <div><p className="eyebrow">EDUCATION LEDGER</p><h3>星曜教培综合台账</h3><p>跨班期统一查看学员、套餐应收、实收、欠费和成本。学费是一口价套餐，已包含住宿与餐饮。</p></div>
      <div className="educationRule"><strong>课程口径</strong><span>一个月 29天 · 三个月 87天</span><span>每周 6天课程 + 1天自主练习</span></div>
    </section>
    <form className="educationLedgerFilters" onSubmit={search}>
      <label>学员或班期关键词<input value={query.keyword} onChange={(e) => setQuery({ ...query, keyword: e.target.value })} maxLength={120} placeholder="姓名、班期、游戏项目" /></label>
      <label>班期<select value={query.cohort_id} onChange={(e) => setQuery({ ...query, cohort_id: e.target.value })}><option value="">全部班期</option>{cohorts.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
      <label>缴费状态<select value={query.payment_status} onChange={(e) => setQuery({ ...query, payment_status: e.target.value })}><option value="all">全部</option><option value="arrears">欠费</option><option value="paid">已收齐</option><option value="overpaid">超收或预收</option></select></label>
      <button className="primaryButton" disabled={busy}>检索台账</button>
    </form>
    {error && <div className="educationError" role="alert">{error}</div>}
    {data && <>
      <section className="educationMetrics">
        <article><span>报名人次</span><strong>{data.summary.student_count}</strong></article>
        <article><span>套餐应收</span><strong>{money(data.summary.receivable)}</strong></article>
        <article><span>净实收</span><strong>{money(data.summary.received)}</strong></article>
        <article><span>欠费</span><strong>{money(data.summary.arrears)}</strong></article>
        <article><span>超收或预收</span><strong>{money(data.summary.overpayment)}</strong></article>
        <article><span>已归集成本</span><strong>{money(data.summary.cost)}</strong></article>
      </section>
      <div className="educationLedgerTable" role="region" aria-label="综合台账学员明细" tabIndex={0}>
        <table><thead><tr><th>学员及班期</th><th>课程</th><th>套餐应收</th><th>净实收</th><th>欠费</th><th>操作</th></tr></thead><tbody>
          {data.items.map((row) => <tr key={row.id}><td><strong>{row.name}</strong><small>{row.cohort_name} · 报名 {row.registration_date}</small></td><td>{row.game}<small>{periodNames[row.course_period] || row.course_period}<br />{row.study_start} 至 {row.study_end}</small></td><td>{money(row.receivable)}</td><td>{money(row.received)}</td><td className={Number(row.arrears) > 0 ? "educationAmountWarn" : ""}>{money(row.arrears)}{Number(row.overpayment) > 0 && <small>超收 {money(row.overpayment)}</small>}</td><td><button type="button" onClick={() => onOpenCohort(row.cohort_id)}>进入班期</button></td></tr>)}
        </tbody></table>
      </div>
      {!data.items.length && <p>当前筛选范围暂无台账记录。</p>}
      {data.has_more && <button type="button" className="secondaryButton" disabled={busy} onClick={() => void load(data.items.length, true)}>加载更多</button>}
    </>}
  </section>;
}

export function EducationPayments({ api, token, cohortId, studentId, canEdit, onChanged }: { api: Api; token: string; cohortId: string; studentId: string; canEdit: boolean; onChanged: () => void }) {
  const [data, setData] = useState<PaymentLedger | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [revision, setRevision] = useState(0);
  const paymentId = useRef<string | null>(null);
  const installmentId = useRef<string | null>(null);
  const path = `v1/pm/education/cohorts/${cohortId}/students/${studentId}`;
  useEffect(() => {
    const controller = new AbortController();
    api<PaymentLedger>(`${path}/payment-ledger`, { signal: controller.signal }, token).then(setData)
      .catch((cause) => { if (!controller.signal.aborted) setError(cause.message || "收款台账加载失败"); });
    return () => controller.abort();
  }, [api, token, path, revision]);

  async function submit(event: FormEvent<HTMLFormElement>, kind: "payment" | "installment") {
    event.preventDefault(); if (busy || !canEdit) return;
    const values = Object.fromEntries(new FormData(event.currentTarget));
    const request = kind === "payment" ? paymentId : installmentId;
    request.current ||= crypto.randomUUID();
    setBusy(true); setError(""); setMessage("");
    try {
      await api(`${path}/${kind === "payment" ? "payments" : "installments"}`, { method: "POST", body: JSON.stringify({ ...values, request_id: request.current, ...(kind === "payment" ? { installment_id: values.installment_id || null } : { active: true }) }), signal: AbortSignal.timeout(20000) }, token);
      request.current = null; event.currentTarget.reset(); setMessage(kind === "payment" ? "收退款明细已登记，净实收和欠费已更新。" : "分期计划已添加。");
      setRevision((value) => value + 1); onChanged();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "保存失败，请刷新核对"); }
    finally { setBusy(false); }
  }
  async function deactivate(item: Installment) {
    if (busy || !canEdit) return;
    setBusy(true); setError("");
    try {
      await api(`${path}/installments/${item.id}`, { method: "PATCH", body: JSON.stringify({ label: item.label, due_on: item.due_on, amount: item.amount, note: item.note, active: false, version: item.version }), signal: AbortSignal.timeout(20000) }, token);
      setRevision((value) => value + 1); setMessage("分期计划已停用，历史记录继续保留。");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "停用失败"); }
    finally { setBusy(false); }
  }
  return <section className="educationPayments">
    <h3>分期与收退款</h3>
    {error && <div className="educationError" role="alert">{error}</div>}{message && <div className="noticeBar" role="status">{message}</div>}
    {data && <><div className="educationMetrics">
      <article><span>套餐应收</span><strong>{money(data.summary.receivable)}</strong></article><article><span>净实收</span><strong>{money(data.summary.net_received)}</strong></article><article><span>欠费</span><strong>{money(data.summary.arrears)}</strong></article><article><span>分期计划合计</span><strong>{money(data.summary.plan_total)}</strong></article>
    </div>{Number(data.summary.plan_difference) !== 0 && <p className="educationHint">分期计划与套餐应收相差 {money(Math.abs(Number(data.summary.plan_difference)))}，请继续补充分期或核对套餐金额。</p>}
      <div className="educationLedgerSplit">
        <div><h4>分期计划</h4>{data.installments.filter((item) => item.active).map((item) => <article className="educationLedgerCard" key={item.id}><strong>{item.label} · {money(item.amount)}</strong><span>到期 {item.due_on} · 已关联收款 {money(item.paid)} · 待收 {money(item.remaining)}</span>{item.note && <span>{item.note}</span>}{canEdit && <button type="button" disabled={busy} onClick={() => void deactivate(item)}>停用计划</button>}</article>)}{!data.installments.some((item) => item.active) && <p>暂无有效分期计划。</p>}</div>
        <div><h4>收退款明细</h4>{data.payments.map((item) => <article className="educationLedgerCard" key={item.id}><strong>{item.direction === "receipt" ? "收款" : "退款"} {money(item.amount)}</strong><span>{item.occurred_on} · {item.method}{item.account ? ` · ${item.account}` : ""} · 经办人 {item.creator_name}</span>{item.note && <span>{item.note}</span>}</article>)}{!data.payments.length && <p>暂无收退款明细；现有累计已收金额作为历史期初数保留。</p>}</div>
      </div>
      {canEdit && <div className="educationLedgerSplit">
        <details><summary>＋ 添加分期计划</summary><form className="educationForm" onSubmit={(event) => void submit(event, "installment")}><label>期次名称<input name="label" required maxLength={80} placeholder="定金、第一期或尾款" /></label><label>到期日<input name="due_on" type="date" required defaultValue={today()} /></label><label>计划金额<input name="amount" type="number" min="0.01" step="0.01" required /></label><label className="educationWide">备注<input name="note" maxLength={1000} /></label><button className="primaryButton" disabled={busy}>保存分期</button></form></details>
        <details><summary>＋ 登记收款或退款</summary><form className="educationForm" onSubmit={(event) => void submit(event, "payment")}><label>方向<select name="direction"><option value="receipt">收款</option><option value="refund">退款</option></select></label><label>金额<input name="amount" type="number" min="0.01" step="0.01" required /></label><label>日期<input name="occurred_on" type="date" required defaultValue={today()} /></label><label>方式<select name="method">{data.methods.map((method) => <option key={method}>{method}</option>)}</select></label><label>关联分期<select name="installment_id"><option value="">暂不关联</option>{data.installments.filter((item) => item.active).map((item) => <option key={item.id} value={item.id}>{item.label} · {money(item.amount)}</option>)}</select></label><label>收款账户或渠道<input name="account" maxLength={120} /></label><label className="educationWide">备注<input name="note" maxLength={1000} placeholder="退款请写明原因；退款不会自动调减套餐应收" /></label><button className="primaryButton" disabled={busy}>登记明细</button></form></details>
      </div>}
    </>}
  </section>;
}
