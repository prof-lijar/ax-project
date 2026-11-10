import { AlertCircle, ExternalLink, ImagePlus, Inbox, LoaderCircle, Play, Upload, X } from "lucide-react";
import { useEffect, useRef, useState, type DragEvent } from "react";
import { t, useLanguage } from "../../shared/i18n";
import { runAx768Workflow, workflowStatusLabels, type WorkflowResult, type WorkflowStage } from "../../shared/api/ax768WorkflowClient";
import { isSheetUrl } from "../../shared/api/ax768Client";
import { ACTIVE_AX768_WORKFLOW, AX768_WORKFLOWS, type Ax768WorkflowId } from "../../shared/api/ax768Workflows";
import styles from "./Ax768WorkflowPanel.module.css";

const IMAGE_TYPES = new Set(["image/png", "image/jpeg", "image/webp"]);
const MAX_IMAGES = 5;
const MAX_BYTES = 50 * 1024 * 1024;
const fileKey = (file: File) => `${file.name}:${file.size}:${file.lastModified}:${file.type}`;
function fileSize(bytes: number) {
  return bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function ImagePreview({ file, remove }: { file: File; remove: () => void }) {
  const [url, setUrl] = useState("");
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    const next = URL.createObjectURL(file);
    setUrl(next); setFailed(false);
    return () => URL.revokeObjectURL(next);
  }, [file]);
  return <li className={styles.imageItem}>
    <div className={styles.thumbnail}>{url && !failed ? <img src={url} alt={file.name} onError={() => setFailed(true)} /> : <ImagePlus size={20} aria-hidden />}</div>
    <div className={styles.fileInfo}><strong title={file.name}>{file.name}</strong><span>{failed ? t("Image preview unavailable") : fileSize(file.size)}</span></div>
    <button type="button" className={styles.remove} aria-label={t("Remove {name}", { name: file.name })} onClick={remove}><X size={16} aria-hidden /></button>
  </li>;
}

function StageResult({ title, stage }: { title: string; stage: WorkflowStage }) {
  const labels = { found: "Match found", not_found: "No match", skipped: "Skipped", failed: "Run failed", needs_confirmation: "Choose a matching name", candidate: "Candidate" };
  return <section className={styles.stage} aria-label={t(title)}>
    <div className={styles.stageHeading}><h3>{t(title)}</h3><span>{t(labels[stage.status])}</span></div>
    {stage.row && <strong>{stage.name} · {t("Row {row}", { row: stage.row })}</strong>}
    {(stage.city || stage.sheet_alias) && <p>{[stage.city, stage.sheet_alias, stage.sheet_title].filter(Boolean).join(" · ")}</p>}
    {stage.address && <p>{stage.address}</p>}
    {stage.reason && <p>{stage.reason}</p>}
    {isSheetUrl(stage.sheet_url) && <a href={stage.sheet_url} target="_blank" rel="noreferrer">{t("Open matching row")}<ExternalLink size={12} aria-hidden /></a>}
  </section>;
}

export function Ax768WorkflowPanel() {
  useLanguage(s => s.language);
  const [message, setMessage] = useState("");
  const [workflowId, setWorkflowId] = useState<Ax768WorkflowId | "">("");
  const [selectionError, setSelectionError] = useState(false);
  const workflowChoice = useRef<HTMLSelectElement>(null);
  const messageInput = useRef<HTMLTextAreaElement>(null);
  const selectedWorkflow = AX768_WORKFLOWS.find(workflow => workflow.id === workflowId);
  const [running, setRunning] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [result, setResult] = useState<WorkflowResult | null>(null);
  const [runError, setRunError] = useState("");
  const busy = useRef(false);
  const generation = useRef(0);
  useEffect(() => () => { generation.current++; }, []);
  useEffect(() => {
    if (!running) return;
    const start = Date.now(); setElapsed(0);
    const timer = window.setInterval(() => setElapsed(Math.floor((Date.now() - start) / 1000)), 1000);
    return () => window.clearInterval(timer);
  }, [running]);
  function resetResult() { setResult(null); setRunError(""); }
  async function run(confirmedName?: string) {
    if (busy.current) return;
    if (!workflowId) { setSelectionError(true); workflowChoice.current?.focus(); return; }
    if (workflowId !== ACTIVE_AX768_WORKFLOW) { setRunError("This workflow is coming soon."); return; }
    if (!message.trim()) { setRunError("Enter a message of 1–8,000 characters."); messageInput.current?.focus(); return; }
    if (images.length) return;
    busy.current = true; setRunning(true); setRunError(""); setResult(null);
    const current = generation.current;
    try {
      const next = await runAx768Workflow(workflowId, message, confirmedName);
      if (current === generation.current) setResult(next);
    } catch (error) {
      if (current === generation.current) setRunError(error instanceof Error ? error.message : "The workflow result could not be retrieved. Check the AS row before running again.");
    } finally {
      if (current === generation.current) { busy.current = false; setRunning(false); }
    }
  }
  const [images, setImages] = useState<File[]>([]);
  const [errors, setErrors] = useState<string[]>([]);
  const [dragging, setDragging] = useState(false);
  const picker = useRef<HTMLInputElement>(null);
  const files = useRef<File[]>([]);
  const dragDepth = useRef(0);
  function updateImages(next: File[]) { files.current = next; setImages(next); }
  function addImages(incoming: File[]) {
    if (busy.current) return;
    resetResult();
    const next = [...files.current];
    const rejected: string[] = [];
    let bytes = next.reduce((sum, file) => sum + file.size, 0);
    for (const file of incoming) {
      if (!IMAGE_TYPES.has(file.type)) { rejected.push(t("{name}: choose a PNG, JPG or WebP image.", { name: file.name })); continue; }
      if (!file.size) { rejected.push(t("{name}: this file is empty.", { name: file.name })); continue; }
      if (next.some(existing => fileKey(existing) === fileKey(file))) continue;
      if (next.length >= MAX_IMAGES) { rejected.push(t("You can add up to 5 images.")); break; }
      if (bytes + file.size > MAX_BYTES) { rejected.push(t("Images must total 50 MB or less.")); continue; }
      next.push(file); bytes += file.size;
    }
    updateImages(next); setErrors([...new Set(rejected)]);
  }
  function preventFileDrop(event: DragEvent) {
    event.preventDefault(); event.stopPropagation();
  }
  function clear() {
    if (busy.current) return;
    resetResult(); setMessage(""); updateImages([]); setErrors([]); setDragging(false); dragDepth.current = 0;
    if (picker.current) picker.current.value = "";
  }
  return <div className={styles.workspace}>
    <section className={styles.inputPanel} aria-labelledby="ax-workflow-input-title">
      <div className={styles.workflowPicker}>
        <label htmlFor="ax-workflow-choice">{t("Select workflow")} <span className={styles.required}>{t("Required")}</span></label>
        <select id="ax-workflow-choice" ref={workflowChoice} value={workflowId} required disabled={running}
          aria-invalid={selectionError || undefined} aria-describedby={selectionError ? "ax-workflow-selection-error" : undefined}
          onChange={event => { setWorkflowId(event.target.value as Ax768WorkflowId | ""); setSelectionError(false); resetResult(); }}>
          <option value="">{t("Select workflow")}</option>
          {AX768_WORKFLOWS.map(workflow => <option key={workflow.id} value={workflow.id} disabled={!workflow.available}>
            {workflow.name}{!workflow.available ? ` · ${t("Coming soon")}` : ""}
          </option>)}
        </select>
      </div>
      {selectionError && <p id="ax-workflow-selection-error" className={styles.selectionAlert} role="alert"><AlertCircle size={16} aria-hidden />{t("Please select a workflow.")}</p>}
      <header className={styles.panelHeader}><h2 id="ax-workflow-input-title">{t("User input")}</h2>
        <button type="button" className={styles.clear} disabled={running || (!message && !images.length && !errors.length)} onClick={clear}>{t("Clear input")}</button>
      </header>
      <div className={`${styles.composer} ${dragging ? styles.dragging : ""}`} role="group" aria-label={t("Request with text and images")}
        onDragEnter={event => { if (event.dataTransfer.types.includes("Files")) { preventFileDrop(event); dragDepth.current++; setDragging(true); } }}
        onDragOver={event => { if (event.dataTransfer.types.includes("Files")) { preventFileDrop(event); event.dataTransfer.dropEffect = "copy"; } }}
        onDragLeave={event => { preventFileDrop(event); dragDepth.current = Math.max(0, dragDepth.current - 1); if (!dragDepth.current) setDragging(false); }}
        onDrop={event => { if (!event.dataTransfer.files.length) return; preventFileDrop(event); dragDepth.current = 0; setDragging(false); addImages(Array.from(event.dataTransfer.files)); }}>
        <textarea ref={messageInput} id="ax-workflow-message" value={message} disabled={running} onChange={event => { setMessage(event.target.value); resetResult(); }} maxLength={8000} rows={8}
          aria-label={t("Request")} placeholder={t("Type your request here…\nDrop images into this box or use Add images below.")}
          aria-describedby="ax-workflow-image-hint" />
        {images.length > 0 && <ul className={styles.images} aria-label={t("Attached images")}>{images.map(file => <ImagePreview key={fileKey(file)} file={file}
          remove={() => { if (busy.current) return; resetResult(); updateImages(files.current.filter(item => item !== file)); setErrors([]); }} />)}</ul>}
        <input ref={picker} type="file" accept="image/png,image/jpeg,image/webp" multiple hidden aria-label={t("Upload images")}
          onChange={event => { addImages(Array.from(event.target.files ?? [])); event.target.value = ""; }} />
        <div className={styles.toolbar}>
          <button type="button" className={styles.attach} disabled={running} onClick={() => picker.current?.click()}><ImagePlus size={17} aria-hidden />{t("Add images")}{images.length > 0 && <span className={styles.imageCount}>{images.length}/5</span>}</button>
          <span className={styles.characterCount}>{message.length.toLocaleString()} / 8,000</span>
          <button type="button" className={styles.run} disabled={running || images.length > 0} onClick={() => void run()} aria-describedby={images.length ? "ax-workflow-setup-note" : undefined}>{running ? <LoaderCircle className={styles.spinner} size={15} aria-hidden /> : <Play size={15} aria-hidden />}{t(running ? "Running…" : "Run workflow")}</button>
        </div>
        {dragging && <div className={styles.dropOverlay}><Upload size={26} aria-hidden /><strong>{t("Drop images here")}</strong></div>}
      </div>
      <p id="ax-workflow-image-hint" className={styles.localNote}>{t("PNG, JPG or WebP · up to 5 images · 50 MB total")}</p>
      <div aria-live="polite">{errors.length > 0 && <ul className={styles.errors}>{errors.map(error => <li key={error}>{error}</li>)}</ul>}</div>
      {images.length > 0 && <p id="ax-workflow-setup-note" className={styles.imageWarning}>{t("Type the address from the image, then remove attachments to run this text workflow.")}</p>}
    </section>
    <div className={styles.outputColumn} aria-busy={running}>
      <section className={styles.statusPanel} aria-labelledby="ax-workflow-status-title" aria-live="polite">
        <header className={styles.panelHeader}><h2 id="ax-workflow-status-title">{t("Workflow status")}</h2><span className={styles.status}>{running ? <LoaderCircle className={styles.spinner} size={14} aria-hidden /> : <span aria-hidden />}{t(running ? "Running…" : runError ? "Needs attention" : result ? workflowStatusLabels[result.status] : "Not started")}</span></header>
        <p className={styles.selectedWorkflow}>{selectedWorkflow?.name ?? t("No workflow selected")}</p>
        <p className={styles.description}>{running ? t("Checking the device signal and AS result… {seconds}s elapsed", { seconds: elapsed }) : selectedWorkflow ? t("AS address if needed → Roster IMEI → Signal → AS update when connected") : null}</p>
        {runError && <p className={styles.imageWarning} role="alert">{t(runError)}</p>}
        {result && <><p className={styles.response}>{result.response}</p><span className={styles.localNote}>{t("Finished in {seconds}s", { seconds: (result.duration_ms / 1000).toFixed(1) })}</span></>}
        {result?.attempts.length ? <ol className={styles.attempts}>{result.attempts.map((a, i) => <li key={`${a.sheet_alias}-${i}`}>{a.city} · {a.sheet_alias}<span>{t(a.status === "found" ? "Match found" : a.status === "not_found" ? "No exact match" : "Run failed")}</span></li>)}</ol> : null}
      </section>
      <section className={styles.resultPanel} aria-labelledby="ax-workflow-result-title">
        <header className={styles.panelHeader}><h2 id="ax-workflow-result-title">{t("Workflow result")}</h2></header>
        {result ? <>
          <p className={styles.parsed}>{[result.parsed.lookup_name, result.parsed.address].filter(Boolean).join(" · ")}</p>
          {result.notices.length > 0 && <ul className={styles.notices}>{result.notices.map((notice, i) => <li key={i}>{notice}</li>)}</ul>}
          <StageResult title="1. User roster" stage={result.roster} />
          <section className={styles.stage} aria-label={t("2. Device signal")}>
            <div className={styles.stageHeading}><h3>{t("2. Device signal")}</h3><span>{t(({connected: "Signal confirmed", disconnected: "Device disconnected", failed: "Signal check failed", skipped: "Skipped"})[result.signal.status])}</span></div>
            <dl className={styles.signalValues}>
              {result.signal.imei && <div><dt>IMEI ({result.signal.imei_column})</dt><dd>{result.signal.imei}</dd></div>}
              {result.signal.sn && <div><dt>S/N</dt><dd>{result.signal.sn}</dd></div>}
              {result.signal.signal_label && <div><dt>{t("Signal strength")}</dt><dd>{result.signal.signal_label}{result.signal.rssi !== null ? ` (RSSI ${result.signal.rssi})` : ""}</dd></div>}
            </dl>
            {result.signal.reason && <p>{result.signal.reason}</p>}
          </section>
          <StageResult title="3. Latest AS match" stage={result.as_lookup} />
          <section className={styles.stage} aria-label={t("4. AS row update")}>
            <div className={styles.stageHeading}><h3>{t("4. AS row update")}</h3><span>{t(({updated: "Saved and verified", skipped: "Skipped", failed: "Not updated", unknown: "Update not confirmed"})[result.as_update.status])}</span></div>
            {result.as_update.row && <strong>{t("Row {row}", { row: result.as_update.row })}</strong>}
            {result.as_update.reason && <p>{result.as_update.reason}</p>}
            {result.as_update.changes.length > 0 && <><p>{t(result.as_update.verified ? "Verified values" : "Requested values · not verified")}</p><dl className={styles.updateValues}>{result.as_update.changes.map(change => <div key={change.column}><dt>{change.column}</dt><dd>{change.value}</dd></div>)}</dl></>}
            {result.as_update.y_action === "unchanged" && <p>{t("Y left unchanged: C did not match either completion rule.")}</p>}
            {result.as_update.status === "unknown" && <p className={styles.imageWarning}>{t("Check the AS row before running again. The update may already be saved.")}</p>}
          </section>
          {result.status === "needs_confirmation" && <div className={styles.candidates}><p>{t("Choose a matching name to continue the AS lookup.")}</p>{result.candidates.map((candidate, i) => <button type="button" key={`${candidate.sheet_alias}-${candidate.row}-${i}`} disabled={running || !candidate.name} onClick={() => candidate.name && void run(candidate.name)}><strong>{candidate.name}</strong><span>{candidate.city} · {t("Row {row}", { row: candidate.row ?? "—" })} · {candidate.address}</span></button>)}</div>}
        </> : <div className={styles.empty}>{running ? <LoaderCircle className={styles.spinner} size={32} aria-hidden /> : <Inbox size={32} strokeWidth={1.4} aria-hidden />}<h3>{t(running ? "Looking for matching rows" : "No results yet")}</h3><p>{t("The workflow output and completion status will appear here after a run.")}</p></div>}
      </section>
    </div>
  </div>;
}
