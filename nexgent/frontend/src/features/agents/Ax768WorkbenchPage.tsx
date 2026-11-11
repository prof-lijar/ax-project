import { ArrowLeft, ArrowUpRight, CheckCircle2, Clock3, FileSpreadsheet, FilePenLine, Highlighter, Info, LoaderCircle, Search, TriangleAlert } from "lucide-react";
import { useEffect, useState, type MouseEvent } from "react";
import { AX768_CASES, outcomeLabels, type Ax768CaseId, type Ax768Outcome, memberCandidateMessage } from "../../shared/api/ax768Client";
import { t, useLanguage, locale } from "../../shared/i18n";
import { navigateToSection } from "../../shared/navigation/sections";
import { useAx768Store, type Ax768Run } from "../../shared/state/useAx768Store";
import styles from "./Ax768WorkbenchPage.module.css";
import { Ax768WorkflowPanel } from "./Ax768WorkflowPanel";
import { Ax768SheetsPanel } from "./Ax768SheetsPanel";

const WORKSPACE_TABS = ["workflow", "test", "sheets"] as const;
const TAB_LABELS = { test: "Individual tasks", workflow: "Workflow", sheets: "Sheets" };

function back(event: MouseEvent<HTMLAnchorElement>) {
  if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
  event.preventDefault(); navigateToSection("agents");
}
function tone(outcome: Ax768Outcome) {
  return outcome === "highlighted_with_warnings" || outcome === "unknown" || outcome === "disconnected" ? styles.warning :
    outcome === "failed" || outcome === "blocked" ? styles.failure : outcome === "not_found" ? styles.neutral : styles.success;
}

export function Ax768WorkbenchPage() {
  useLanguage(s => s.language);
  const state = useAx768Store();
  const selected = AX768_CASES.find(c => c.id === state.selectedCase)!;
  const message = state.drafts[state.selectedCase] ?? "";
  const run = state.history.find(r => r.id === state.selectedRunId) ?? null;
  const [activeTab, setActiveTab] = useState<typeof WORKSPACE_TABS[number]>("workflow");
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (!state.active) return;
    setNow(Date.now());
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [state.active?.id]);
  return <section className={styles.page}>
    <a href="/agents" onClick={back} className={styles.back}><ArrowLeft size={15} />{t("Back to Agents")}</a>
    <header className={styles.header}>
      <span className={styles.avatar}><FileSpreadsheet size={24} /></span>
      <div><h1>운영시트에이젠트</h1></div>
      <span className={styles.access}>{t("Admin workspace")}</span>
    </header>
    <div className={styles.tabs} role="tablist" aria-label={t("운영시트에이젠트 workspace")}>
      {WORKSPACE_TABS.map(tab => <button key={tab} id={`ax-tab-${tab}`} type="button" role="tab"
        aria-selected={activeTab === tab} aria-controls={`ax-panel-${tab}`} tabIndex={activeTab === tab ? 0 : -1}
        onClick={() => setActiveTab(tab)} onKeyDown={event => {
          if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
          event.preventDefault();
          const index = WORKSPACE_TABS.indexOf(tab);
          const next = event.key === "Home" ? WORKSPACE_TABS[0] : event.key === "End" ? WORKSPACE_TABS[WORKSPACE_TABS.length - 1]
            : WORKSPACE_TABS[(index + (event.key === "ArrowRight" ? 1 : -1) + WORKSPACE_TABS.length) % WORKSPACE_TABS.length];
          setActiveTab(next);
          document.getElementById(`ax-tab-${next}`)?.focus();
        }}>
        {t(TAB_LABELS[tab])}
        {tab === "test" && state.active && <LoaderCircle size={14} className={styles.spin} aria-label={t("Running…")} />}
      </button>)}
    </div>
    <div id="ax-panel-test" role="tabpanel" aria-labelledby="ax-tab-test" tabIndex={0}
      hidden={activeTab !== "test"} className={`${styles.tabPanel} ${styles.workspace}`}>
      <form className={styles.inputPanel} onSubmit={event => { event.preventDefault(); void state.run(); }}>
        <div className={styles.sectionTitle}><h2>{t("Individual tasks")}</h2></div>
        <label className={styles.label} htmlFor="ax-case">{t("Workflow case")}</label>
        <select id="ax-case" value={state.selectedCase} disabled={!!state.active}
          onChange={event => state.selectCase(event.target.value as Ax768CaseId)}>
          {AX768_CASES.map(c => <option value={c.id} key={c.id}>{["imei", "member_note"].includes(c.id) ? t(c.title) : `${c.id} · ${t(c.title)}`}</option>)}
        </select>
        <details className={styles.taskHelp}><summary>{t("Task details")}</summary>
        <p className={styles.description}>{t(selected.description)}</p>
        <div className={styles.target}><FileSpreadsheet size={16} aria-hidden /><div><span>{t("Search location")}</span><strong>{t(selected.target)}</strong></div></div>
        </details>
        <div className={styles.mode}>{selected.id === "member_note" ? <FilePenLine size={14} /> : selected.writes ? <Highlighter size={14} /> : <Search size={14} />}{t(selected.id === "member_note" ? "Replaces General notes with the entered text" : selected.id === "imei" ? "Signal check · no sheet changes" : selected.writes ? "Applies yellow to the latest match" : "Search only · no sheet changes")}</div>
        <div className={styles.labelRow}><label htmlFor="ax-message" className={styles.label}>{t("Message")}</label><button type="button" className={styles.textButton} disabled={!!state.active} onClick={() => state.setDraft(selected.example)}>{t("Use example")}</button></div>
        <textarea id="ax-message" value={message} disabled={!!state.active} maxLength={8000} rows={5} placeholder={selected.example}
          aria-describedby="ax-input-format" onChange={event => state.setDraft(event.target.value)} />
        <div id="ax-input-format" className={styles.inputHint}><span>{t(selected.format)}</span><span>{message.length.toLocaleString()} / 8,000</span></div>
        {selected.id === "member_note" && <p className={styles.note}><Info size={15} /><span>{t("This test saves a real member note. Check the member and date before saving.")}</span></p>}
        {selected.writes && selected.id !== "member_note" && <p className={styles.note}><Info size={15} /><span>{t("Existing formatting can hide yellow. We report saved and visible colors separately.")}</span></p>}
        <button className={styles.submit} type="submit" disabled={!!state.active || !message.trim()}>
          {state.active ? <LoaderCircle className={styles.spin} size={17} /> : selected.id === "member_note" ? <FilePenLine size={17} /> : selected.writes ? <Highlighter size={17} /> : <Search size={17} />}
          {t(state.active ? "Running…" : selected.id === "member_note" ? "Find member and replace notes" : selected.id === "imei" ? "Check signal" : selected.writes ? "Search and apply yellow" : "Search")}
        </button>
      </form>
      <div className={styles.resultColumn}>
        <section className={styles.resultPanel} aria-label={t("Result")}>
          <div className={styles.sectionTitle}><h2>{t("Result")}</h2></div>
          <div aria-live="polite" aria-atomic="true">
            {state.active ? <div className={styles.empty}><LoaderCircle className={styles.spin} size={27} /><h3>{t("운영시트에이젠트 is working")}</h3><p>{t(state.active.caseId === "imei" ? "Finding the roster IMEI and waiting for the device response." : "Searching the configured sheets and checking the result.")}</p><span className={styles.elapsed}><Clock3 size={14} />{Math.max(0, Math.floor((now - state.active.startedAt) / 1000))}s</span><small>{t("You can navigate within the app while this runs. Refreshing clears this session.")}</small></div> : run ? <Ax768ResultView run={run} /> : <div className={styles.empty}><Search size={30} strokeWidth={1.4} /><h3>{t("No results yet")}</h3></div>}
          </div>
        </section>
        <details className={styles.history}>
          <summary className={styles.historyHeader}><span>{t("Recent results")} ({state.history.length})</span><span>{t("This session only")}</span></summary>
          {state.history.length === 0 ? <p className={styles.historyEmpty}>{t("Your last 20 runs will appear here until you refresh or sign out.")}</p> : <ul>{state.history.map(item => {
            const outcome = item.result?.outcome ?? item.outcome ?? "unknown";
            return <li key={item.id}><button type="button" aria-pressed={item.id === state.selectedRunId} disabled={!!state.active} onClick={() => state.selectRun(item.id)}>
              <span className={styles.caseBadge}>{item.caseId}</span><span className={styles.historyBody}><strong>{item.message}</strong><span className={tone(outcome)}>{t(outcomeLabels[outcome])}{item.result?.selected_row ? ` · ${t("Row {row}", { row: item.result.selected_row })}` : ""}</span></span>
              <time dateTime={new Date(item.startedAt).toISOString()}>{new Date(item.startedAt).toLocaleTimeString(locale(), { hour: "2-digit", minute: "2-digit" })}</time>
            </button></li>;
          })}</ul>}
        </details>
      </div>
    </div>
    <section id="ax-panel-workflow" role="tabpanel" aria-labelledby="ax-tab-workflow" tabIndex={0}
      hidden={activeTab !== "workflow"} className={styles.tabPanel}>
      <Ax768WorkflowPanel />
    </section>
    <section id="ax-panel-sheets" role="tabpanel" aria-labelledby="ax-tab-sheets" tabIndex={0}
      hidden={activeTab !== "sheets"} className={styles.tabPanel}>
      <Ax768SheetsPanel />
    </section>
  </section>;
}

export function Ax768ResultView({ run }: { run: Ax768Run }) {
  const busy = useAx768Store(s => !!s.active);
  const result = run.result;
  const outcome = result?.outcome ?? run.outcome ?? "unknown";
  const warning = ["highlighted_with_warnings", "unknown", "failed", "blocked", "disconnected"].includes(outcome);
  const fields = result ? [["City", result.city], ["Sheet", result.sheet_title ?? result.sheet_alias], ["Name", result.name], ["Address", result.address], [result.imei_column ? `IMEI (${result.imei_column})` : "IMEI", result.imei], ["S/N", result.ping?.sn], ["Signal strength", result.ping?.signal_label], ["RSSI", result.ping?.rssi == null ? null : String(result.ping.rssi)]] : [];
  return <div className={styles.result}>
    <div className={`${styles.resultStatus} ${tone(outcome)}`}>{warning ? <TriangleAlert size={19} /> : outcome === "not_found" ? <Search size={19} /> : <CheckCircle2 size={19} />}<strong>{t(outcomeLabels[outcome])}</strong><span className={styles.resultCase}>{t("Case")} {run.caseId}</span></div>
    {result?.member_note && <section className={styles.notice} aria-label={t("Member general note")}>
      <p>{result.response}</p>
      {result.member_note.member_id && <p>{t("Member ID")}: {result.member_note.member_id}</p>}
      {result.member_note.note && <pre className={styles.memberNoteText}>{result.member_note.note}</pre>}
      <a href="https://admin.ansimk.com/members" target="_blank" rel="noopener noreferrer">{t("Open member admin")}</a>
      {result.member_note.candidates.map(candidate => <button type="button" className={`${styles.textButton} ${styles.memberCandidate}`} key={candidate.member_id} disabled={busy} onClick={() => {
        const store = useAx768Store.getState(); store.selectCase("member_note"); store.setDraft(memberCandidateMessage(run.message, candidate));
        document.getElementById("ax-message")?.focus();
      }}>{t("Select member")}: {candidate.name} · {candidate.address} · ID {candidate.member_id}</button>)}
    </section>}
    {result?.selected_row && <div className={styles.rowHeading}><div><span>{t("Latest matching row")}</span><h3>{result.selected_row}</h3></div>{result.sheet_url && <a className={styles.openSheet} href={result.sheet_url} target="_blank" rel="noopener noreferrer">{t("Open sheet")}<ArrowUpRight size={16} /></a>}</div>}
    <dl className={styles.facts}>{fields.filter(([, value]) => value).map(([label, value]) => <div key={label}><dt>{t(label!)}</dt><dd>{value}</dd></div>)}</dl>
    {result && run.caseId === "imei" && !["failed", "blocked"].includes(outcome) && <p className={styles.notice}>{result.response}</p>}
    {result?.stored_verified !== null && result?.stored_verified !== undefined && <div className={styles.formatting}>
      <span>{t("Yellow saved")} <strong>{t(result.stored_verified ? "Confirmed" : "Not confirmed")}</strong></span>
      <span>{t("Visible yellow")} <strong>{t(result.visible_verified ? "Confirmed" : "Not confirmed")}</strong></span>
    </div>}
    {outcome === "highlighted_with_warnings" && <div className={styles.warningNote}><TriangleAlert size={17} /><div><strong>{t("Yellow is saved, but may not appear on the sheet.")}</strong><p>{t("Existing formatting overrides the display in {count} cells.", { count: result?.overridden_cell_count ?? 0 })}</p><p className={styles.cellList}>{result?.overridden_cells.join(", ")}{(result?.overridden_cell_count ?? 0) > (result?.overridden_cells.length ?? 0) ? " …" : ""}</p></div></div>}
    {outcome === "not_found" && run.caseId !== "member_note" && <p className={styles.notice}>{t("No matching row was found. No cells were changed.")}</p>}
    {run.error && <p className={styles.notice} role="alert">{t(run.error)}</p>}
    {result && run.caseId !== "member_note" && ["failed", "blocked"].includes(outcome) && <p className={styles.notice}>{result.response}</p>}
    {!!result?.attempts.length && <ol className={styles.attempts} aria-label={t("Search order")}>{result.attempts.map((attempt, index) => <li key={attempt.sheet_alias ?? index}><span>{index + 1}</span><strong>{attempt.city ?? attempt.sheet_alias}</strong><small>{t(attempt.status === "found" ? "Match found" : attempt.status === "not_found" ? "No match" : "Run failed")}</small></li>)}</ol>}
    {result && <details className={styles.details}><summary>{t("Result details")}</summary><p>{result.response}</p>{result.match_count > 1 && <p>{t("Matching rows or cells: {count}", { count: result.match_count })}</p>}<small>{t("Duration")}: {(result.duration_ms / 1000).toFixed(1)}s</small></details>}
  </div>;
}
