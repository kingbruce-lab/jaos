// Line icons drawn on a 24px grid so navigation and empty states render the
// same on Windows, macOS, and phones (text glyphs like ⌂ ▦ ▣ did not).
export type IconName =
  | "home"
  | "finance"
  | "projects"
  | "upload"
  | "contracts"
  | "search"
  | "write"
  | "review"
  | "governance"
  | "status"
  | "accounts"
  | "more"
  | "refresh";

const paths: Record<IconName, string[]> = {
  home: ["M3.5 10.5 12 4l8.5 6.5", "M5.5 9v10.5h13V9", "M10 19.5v-5h4v5"],
  finance: ["M7 4.5 12 11l5-6.5", "M12 11v8.5", "M8 12.5h8", "M8 16h8"],
  projects: ["M4 5h16v14H4z", "M4 9.5h16", "M9.5 9.5V19"],
  upload: ["M12 15.5V4.5", "M7.5 9 12 4.5 16.5 9", "M4.5 15v4.5h15V15"],
  contracts: ["M6 3.5h8l4 4v13H6z", "M14 3.5v4h4", "M9 12h6", "M9 15.5h6"],
  search: ["M10.5 17a6.5 6.5 0 1 0 0-13 6.5 6.5 0 0 0 0 13z", "M15.5 15.5 20 20"],
  write: ["M4.5 19.5h4l10-10-4-4-10 10z", "M13 7l4 4"],
  review: ["M8 4.5h8v3H8z", "M16 6h2.5v14h-13V6H8", "M9 13.5l2 2 4-4.5"],
  governance: ["M12 3.5 19 6v5.5c0 4.2-2.9 7.4-7 9-4.1-1.6-7-4.8-7-9V6z", "M9 12l2 2 4-4.5"],
  status: ["M3.5 12h4l2.5-6 4 12 2.5-6h4"],
  accounts: ["M9 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7z", "M3 20c.5-3.5 2.8-5.5 6-5.5s5.5 2 6 5.5", "M16 4.5a3.5 3.5 0 0 1 0 6.5", "M18 14.8c1.7.7 2.8 2.5 3 5.2"],
  more: ["M6 12h.01", "M12 12h.01", "M18 12h.01"],
  refresh: ["M19.5 12a7.5 7.5 0 1 1-2.2-5.3", "M19.5 4.5v4h-4"],
};

export function Icon({ name, size = 18 }: { name: IconName; size?: number }) {
  const strokeWidth = name === "more" ? 3 : 1.8;
  return (
    <svg
      className="uiIcon"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {paths[name].map((d) => <path d={d} key={d} />)}
    </svg>
  );
}
