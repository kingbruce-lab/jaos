"use client";
import { FormEvent, useEffect, useRef, useState } from "react";

type Api = <T>(path: string, options?: RequestInit, token?: string) => Promise<T>;
type Assessment = { id: string; stage: string; stage_name: string; assessed_on: string; evaluator_staff_id: string; evaluator_name: string; scores: Record<string, number | null>; version: number; [key: string]: unknown };
const common = { observations: "客观观察与证据", strengths: "优势表现", improvements: "待改善事项", goals: "学习目标", teaching_plan: "教学安排 / 纠偏措施", next_steps: "后续建议" };
const parentFields = { parent_feedback: "给家长的客观反馈", parent_response: "家长意见记录", conservative_outlook: "未来预期 · 保守情景", optimistic_outlook: "未来预期 · 乐观情景", outlook_basis: "预期依据、前提与不确定性" };
const allFields = { ...common, grouping: "分班 / 分组建议", stage_summary: "本阶段成长总结", final_summary: "结营综合结论", ...parentFields };

export function EducationAssessments({ api, token, cohortId, studentId, studentName, studyStart, studyEnd, staff }: { api: Api; token: string; cohortId: string; studentId: string; studentName: string; studyStart: string; studyEnd: string; staff: { id: string; name: string; role: string; active?: boolean }[] }) {
  const [registry, setRegistry] = useState<{ items: Assessment[]; stages: Record<string, string>; dimensions: string[] } | null>(null);
  const [stage, setStage] = useState("baseline");
  const [editing, setEditing] = useState<Assessment | null>(null);
  const [revision, setRevision] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [report, setReport] = useState<{ title: string; text: string } | null>(null);
  const requestId = useRef<string | null>(null);
  const path = `v1/pm/education/cohorts/${cohortId}/students/${studentId}`;
  useEffect(() => {
    const controller = new AbortController();
    api<{ items: Assessment[]; stages: Record<string, string>; dimensions: string[] }>(`${path}/assessments`, { signal: controller.signal }, token)
      .then((value) => { if (!controller.signal.aborted) setRegistry(value); })
      .catch((cause) => { if (!controller.signal.aborted) setError(cause.message || "评估加载失败"); });
    return () => controller.abort();
  }, [api, token, path, revision]);

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (busy || !registry) return;
    const fields = Object.fromEntries(new FormData(event.currentTarget));
    const scores: Record<string, number | null> = {};
    for (const dimension of registry.dimensions) { scores[dimension] = fields[`score_${dimension}`] ? Number(fields[`score_${dimension}`]) : null; delete fields[`score_${dimension}`]; }
    const body = { ...Object.fromEntries(Object.keys(allFields).map((key) => [key, editing?.[key] || ""])), ...fields, stage, scores,
      ...(editing ? { version: editing.version } : { request_id: requestId.current ||= crypto.randomUUID() }) };
    setBusy(true); setError(""); setMessage("");
    try {
      await api(`${path}/assessments${editing ? `/${editing.id}` : ""}`, { method: editing ? "PATCH" : "POST", body: JSON.stringify(body), signal: AbortSignal.timeout(20000) }, token);
      setEditing(null); requestId.current = null; setRevision((value) => value + 1); setReport(null); setMessage("评估记录已保存。");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "保存失败，请刷新核对后再试"); }
    finally { setBusy(false); }
  }
  async function makeReport() {
    setBusy(true); setError("");
    try { setReport(await api<{ title: string; text: string }>(`${path}/graduation-report`, {}, token)); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "报告生成失败"); }
    finally { setBusy(false); }
  }
  function downloadReport() {
    if (!report) return;
    const url = URL.createObjectURL(new Blob(["\ufeff", report.text], { type: "text/plain;charset=utf-8" }));
    const anchor = document.createElement("a"); anchor.href = url; anchor.download = `${report.title.replace(/[<>:"/\\|?*]/g, "-")}.txt`; anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  const existing = registry?.items.find((item) => item.stage === stage && stage !== "phase");
  const availableStaff = staff.filter((person) => person.active !== false || person.id === editing?.evaluator_staff_id);
  return <section className="educationAssessments">
    <h3>{studentName} · 教练评估体系</h3>
    <div className="educationAssessmentSteps"><article><strong>1 · 入学基线</strong><span>入营第1天摸底，明确目标和分班分组</span></article><article><strong>2 · 阶段观察</strong><span>每阶段记录成长、问题与纠偏措施，可多次追加</span></article><article><strong>3 · 结营评估</strong><span>总结表现，生成报告与家长反馈</span></article></div>
    <p className="educationHint">可选评分为1–5分：1需持续指导、2初步掌握、3基本独立、4稳定运用、5可迁移运用。应结合具体事例；未观察到的维度留空。未来预期须说明前提，不承诺段位、升学或职业结果。</p>
    {error && <div role="alert" className="educationError">{error}</div>}{message && <p role="status">{message}</p>}
    {registry && <>
      <div className="educationModuleTabs">{Object.entries(registry.stages).map(([key, label]) => <button type="button" key={key} disabled={busy} className={stage === key ? "active" : ""} onClick={() => { setStage(key); setEditing(null); requestId.current = null; setError(""); }}>{label}</button>)}</div>
      {existing && !editing ? <p>已有{registry.stages[stage]}。<button type="button" disabled={busy} onClick={() => setEditing(existing)}>修改该评估</button></p> : <form className="educationForm" key={`${stage}-${editing?.id || "new"}-${revision}`} onSubmit={(e) => void save(e)}>
        <label>评估日期<input name="assessed_on" type="date" required defaultValue={editing?.assessed_on || (stage === "baseline" ? studyStart : stage === "final" ? studyEnd : new Date().toLocaleDateString("sv-SE"))} /></label>
        <label>评估人<select name="evaluator_staff_id" required defaultValue={editing?.evaluator_staff_id || ""}><option value="">请选择教师 / 助教</option>{availableStaff.map((person) => <option key={person.id} value={person.id}>{person.name} · {person.role}{person.active === false ? "（已移除·历史关联）" : ""}</option>)}</select></label>
        <label>评估阶段名称<input name="stage_name" required maxLength={120} defaultValue={editing?.stage_name || (stage === "phase" ? "" : registry.stages[stage])} placeholder="例如：第1周基础训练" /></label>
        {registry.dimensions.map((dimension) => <label key={dimension}>{dimension}<select name={`score_${dimension}`} defaultValue={editing?.scores[dimension] ?? ""}><option value="">未评估</option>{[1, 2, 3, 4, 5].map((score) => <option key={score} value={score}>{score}分</option>)}</select></label>)}
        {Object.entries({ ...common, ...(stage === "baseline" ? { grouping: "分班 / 分组建议" } : stage === "phase" ? { stage_summary: "本阶段成长总结" } : { final_summary: "结营综合结论" }), ...parentFields }).map(([key, label]) => <label key={key} className="educationWide">{label}<textarea name={key} required={key === "observations" || (key === "final_summary" && stage === "final")} maxLength={key === "grouping" ? 500 : ["observations", "stage_summary", "final_summary", "parent_feedback"].includes(key) ? 3000 : 2000} defaultValue={String(editing?.[key] || "")} placeholder={key === "observations" ? "写清观察场景、具体行为和可核对的表现；不要仅填笼统评价" : key === "outlook_basis" ? "保守 / 乐观情景分别依赖哪些训练投入、持续性和外部条件？有哪些不确定性？" : ""} /></label>)}
        <button className="primaryButton" disabled={busy || availableStaff.length === 0}>{busy ? "保存中…" : "保存评估记录"}</button>{availableStaff.length === 0 && <p>请先在本班期人员名册添加教师或助教。</p>}
      </form>}
      <h4>成长记录（{registry.items.length}）</h4>
      {registry.items.map((item) => <details key={`${item.id}-${item.version}`}><summary>{item.assessed_on} · {registry.stages[item.stage]} · {item.stage_name} · {item.evaluator_name}</summary>
        <p>{registry.dimensions.map((dimension) => `${dimension}：${item.scores[dimension] ?? "未评估"}`).join(" / ")}</p>
        {Object.entries(allFields).filter(([key]) => Boolean(item[key])).map(([key, label]) => <p className="educationNotes" key={key}><strong>{label}：</strong>{String(item[key])}</p>)}
        <button type="button" disabled={busy} onClick={() => { setStage(item.stage); setEditing(item); }}>修改评估记录</button>
      </details>)}
      <button type="button" className="primaryButton" disabled={busy || !registry.items.some((item) => item.stage === "final")} onClick={() => void makeReport()}>生成 / 查看结营报告</button>
      {report && <section className="educationReport"><h4>{report.title}</h4><p className="educationHint">请由教练复核后再交给家长。本操作仅生成报告，不会自动发送。</p><pre>{report.text}</pre><button type="button" onClick={downloadReport}>下载结营报告（TXT）</button></section>}
    </>}
  </section>;
}
