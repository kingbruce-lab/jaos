import React, { useState } from "react";
import { createRoot } from "react-dom/client";
import { ProjectCashflowEditor } from "../app/project-cashflow-editor";
import "../app/globals.css";

function Fixture() {
  const [item, setItem] = useState({ id: "plan", direction: "receivable", due_date: "2026-09-30", amount: "480000", counterparty: "测试客户", note: "" });
  return <main style={{ padding: 16 }}><output data-testid="amount">{item.amount}</output><ProjectCashflowEditor item={item} onSave={async (_, values) => {
    if (Number(values.amount) < 100000) throw new Error("计划金额不能小于财务已确认的实际收付款金额");
    setItem({ ...item, ...values, counterparty: values.counterparty || "", note: values.note || "" });
  }} /></main>;
}
createRoot(document.getElementById("root")!).render(<Fixture />);
