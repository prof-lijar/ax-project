import { AlertCircle, ExternalLink, ImagePlus, Inbox, LoaderCircle, Play, Upload, X } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode, type DragEvent, type ClipboardEvent } from "react";
import { t, useLanguage } from "../../shared/i18n";
import { runAx768Workflow, workflowStatusLabels, type WorkflowResult, type WorkflowStage } from "../../shared/api/ax768WorkflowClient";
import { runInformationUpdate, type InformationResult } from "../../shared/api/ax768InformationClient";
import { isSheetUrl } from "../../shared/api/ax768Client";
import { ACTIVE_AX768_WORKFLOW, AX768_WORKFLOWS, type Ax768WorkflowId } from "../../shared/api/ax768Workflows";
import { extractImageText } from "./ax768Ocr";
import { workflowMessage, type ImageDraft } from "./ax768ImageInput";
import { extractWorkflowDraft, rawImageDraft } from "./ax768WorkflowExtraction";
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
  const preview = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const next = URL.createObjectURL(file);
    setUrl(next); setFailed(false);
    return () => URL.revokeObjectURL(next);
  }, [file]);
  return <li className={styles.imageItem}>
    <button type="button" className={styles.thumbnail} disabled={!url || failed}
      aria-label={t("Preview {name}", { name: file.name })} aria-haspopup="dialog" onClick={() => preview.current?.showModal()}>
      {url && !failed ? <img src={url} alt={file.name} onError={() => setFailed(true)} /> : <ImagePlus size={20} aria-hidden />}
    </button>
    <dialog ref={preview} className={styles.imageDialog} aria-label={file.name}>
      <header className={styles.imageDialogHeader}>
        <strong>{file.name}</strong>
        <button type="button" className={styles.closePreview} aria-label={t("Close")} onClick={() => preview.current?.close()}><X size={20} aria-hidden /></button>
      </header>
      {url && !failed && <img className={styles.fullImage} src={url} alt={file.name} />}
    </dialog>
    <div className={styles.fileInfo}><strong title={file.name}>{file.name}</strong><span>{failed ? t("Image preview unavailable") : fileSize(file.size)}</span></div>
    <button type="button" className={styles.remove} aria-label={t("Remove {name}", { name: file.name })} onClick={remove}><X size={16} aria-hidden /></button>
  </li>;
}

function StageDetails({ title, status, attention = false, children }: { title: string; status: string; attention?: boolean; children: ReactNode }) {
  return <details className={styles.stage} open={attention || undefined}>
    <summary className={styles.stageHeading}><span>{t(title)}</span><span className={attention ? styles.attention : undefined}>{t(status)}</span></summary>
    <div className={styles.stageBody}>{children}</div>
  </details>;
}

function LookupDetails({ stage }: { stage: WorkflowStage }) {
  const labels = { found: "Match found", not_found: "No match", skipped: "Skipped", failed: "Run failed", needs_confirmation: "Choose a matching name", candidate: "Candidate" };
  return <>
    <p>{t(labels[stage.status])}</p>
    {stage.row && <strong>{stage.name} · {t("Row {row}", { row: stage.row })}</strong>}
    {(stage.city || stage.sheet_alias) && <p>{[stage.city, stage.sheet_alias, stage.sheet_title].filter(Boolean).join(" · ")}</p>}
    {stage.address && <p>{stage.address}</p>}
    {stage.reason && <p>{stage.reason}</p>}
    {isSheetUrl(stage.sheet_url) && <a href={stage.sheet_url} target="_blank" rel="noreferrer">{t("Open matching row")}<ExternalLink size={12} aria-hidden /></a>}
  </>;
}

export function Ax768WorkflowPanel() {
  useLanguage(s => s.language);
  const [message, setMessage] = useState("");
  const [workflowId, setWorkflowId] = useState<Ax768WorkflowId | "">("");
  const [selectionError, setSelectionError] = useState(false);
  const informationUpdate = workflowId === "information_update";
  const workflowChoice = useRef<HTMLSelectElement>(null);
  const messageInput = useRef<HTMLTextAreaElement>(null);
  const [running, setRunning] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [result, setResult] = useState<WorkflowResult | null>(null);
  const [informationResult, setInformationResult] = useState<InformationResult | null>(null);
  const [runError, setRunError] = useState("");
  const [extracting, setExtracting] = useState(false);
  const [ocrProgress, setOcrProgress] = useState(0);
  const [analysing, setAnalysing] = useState(false);
  const [ocrError, setOcrError] = useState("");
  const [draft, setDraft] = useState<ImageDraft | null>(null);
  const ocrGeneration = useRef(0);
  const ocrController = useRef<AbortController | null>(null);
  useEffect(() => () => { ocrGeneration.current++; ocrController.current?.abort(); }, []);
  const busy = useRef(false);
  const generation = useRef(0);
  useEffect(() => () => { generation.current++; }, []);
  useEffect(() => {
    if (!running) return;
    const start = Date.now(); setElapsed(0);
    const timer = window.setInterval(() => setElapsed(Math.floor((Date.now() - start) / 1000)), 1000);
    return () => window.clearInterval(timer);
  }, [running]);
  function resetResult() { setResult(null); setInformationResult(null); setRunError(""); }
  async function run(confirmedName?: string) {
    if (busy.current) return;
    if (!workflowId) { setSelectionError(true); workflowChoice.current?.focus(); return; }
    if (workflowId !== ACTIVE_AX768_WORKFLOW && !informationUpdate) { setRunError("This workflow is coming soon."); return; }
    if (!message.trim()) { setRunError("Enter a message of 1–8,000 characters."); messageInput.current?.focus(); return; }
    if (extracting || (images.length > 0 && !draft)) return;
    if (draft?.conflicts && message === draft.message) { setRunError("Review the extracted name and address before running."); messageInput.current?.focus(); return; }
    let request: string;
    try { request = informationUpdate ? message : workflowMessage(message); }
    catch (error) { setRunError(error instanceof Error ? error.message : "Review the extracted name and address before running."); messageInput.current?.focus(); return; }
    busy.current = true; setRunning(true); setRunError(""); setResult(null); setInformationResult(null);
    const current = generation.current;
    try {
      if (informationUpdate) {
        const next = await runInformationUpdate(request);
        if (current === generation.current) setInformationResult(next);
      } else {
        const next = await runAx768Workflow(workflowId, request, confirmedName);
        if (current === generation.current) setResult(next);
      }
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
  async function readImages(next: File[], original: string, selected = workflowId, cachedPages?: ImageDraft["pages"]) {
    ocrController.current?.abort();
    const current = ++ocrGeneration.current;
    const controller = new AbortController(); ocrController.current = controller;
    const hasInput = next.length > 0 || (selected === "information_update" && !!original.trim());
    setDraft(null); setOcrError(""); setOcrProgress(0); setAnalysing(false); setExtracting(hasInput);
    setMessage(original);
    if (!hasInput) return;
    try {
      const pages = cachedPages ?? (next.length ? await extractImageText(next, controller.signal, value => { if (current === ocrGeneration.current) setOcrProgress(value); }) : []);
      if (current !== ocrGeneration.current) return;
      // Keep all recognized text available even if agent analysis fails.
      const raw = rawImageDraft(pages, original);
      setDraft(raw); setMessage(raw.message);
      setAnalysing(selected === "information_update");
      const extracted = await extractWorkflowDraft(selected, pages, original, controller.signal);
      if (current !== ocrGeneration.current) return;
      setDraft(extracted); setMessage(extracted.message); resetResult();
    } catch (error) {
      if (current === ocrGeneration.current) setOcrError(error instanceof Error && /^(Image text|Use an image|Use up to|No readable text|Too much image text|Information extraction|Restart Agent Server)/.test(error.message) ? error.message : "Information extraction failed. Review the original text and try again.");
    } finally { if (current === ocrGeneration.current) { setExtracting(false); setAnalysing(false); } }
  }
  function selectWorkflow(next: Ax768WorkflowId | "") {
    if (busy.current) return;
    const original = originalInput();
    const pages = draft?.pages;
    setWorkflowId(next); setSelectionError(false); resetResult();
    void readImages(files.current, original, next, pages);
  }
  function originalInput() { return draft && message === draft.message ? draft.original : message; }
  function removeImage(file: File) {
    if (busy.current) return;
    const original = originalInput();
    const next = files.current.filter(item => item !== file);
    resetResult(); updateImages(next); setErrors([]);
    // Discard generated text from a removed image; preserve deliberate user edits.
    if (draft && message === draft.message) setMessage(original);
    void readImages(next, original);
  }
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
    if (next.length !== files.current.length) { updateImages(next); void readImages(next, originalInput()); }
    setErrors([...new Set(rejected)]);
  }
  function pasteImages(event: ClipboardEvent<HTMLDivElement>) {
    const items = Array.from(event.clipboardData.items)
      .filter(item => item.kind === "file" && item.type.startsWith("image/"))
      .flatMap(item => { const file = item.getAsFile(); return file ? [file] : []; });
    const pasted = items.length ? items : Array.from(event.clipboardData.files).filter(file => file.type.startsWith("image/"));
    if (!pasted.length) return; // Keep ordinary text paste native.
    event.preventDefault();
    addImages(pasted);
  }
  function preventFileDrop(event: DragEvent) {
    event.preventDefault(); event.stopPropagation();
  }
  function clear() {
    if (busy.current) return;
    ocrGeneration.current++; ocrController.current?.abort(); setExtracting(false); setAnalysing(false); setDraft(null); setOcrError("");
    resetResult(); setMessage(""); updateImages([]); setErrors([]); setDragging(false); dragDepth.current = 0;
    if (picker.current) picker.current.value = "";
  }
  const structuringState = extracting ? analysing ? "structuring" : "extracting" : ocrError ? "failed" : draft?.noInformation ? "empty" : draft?.structured ? "complete" : "before";
  const structuringLabel = { empty: "No case information found", before: "Before structuring", extracting: "Extracting text…", structuring: "Structuring…", complete: "Structuring complete · ready to edit", failed: "Structuring failed · original text kept" }[structuringState];
  return <div className={styles.workspace} onPaste={pasteImages}>
    <section className={styles.inputPanel} aria-labelledby="ax-workflow-input-title">
      <header className={styles.panelHeader}><h2 id="ax-workflow-input-title">{t("New request")}</h2>
        <button type="button" className={styles.clear} disabled={running || (!message && !images.length && !errors.length && !draft)} onClick={clear}>{t("Clear input")}</button>
      </header>
      <div className={styles.workflowPicker}>
        <label htmlFor="ax-workflow-choice">{t("Select workflow")} <span className={styles.required}>{t("Required")}</span></label>
        <select id="ax-workflow-choice" ref={workflowChoice} value={workflowId} required disabled={running}
          aria-invalid={selectionError || undefined} aria-describedby={selectionError ? "ax-workflow-selection-error" : undefined}
          onChange={event => selectWorkflow(event.target.value as Ax768WorkflowId | "")}>
          <option value="">{t("Select workflow")}</option>
          {AX768_WORKFLOWS.map(workflow => <option key={workflow.id} value={workflow.id} disabled={!workflow.available}>
            {workflow.name}{!workflow.available ? ` · ${t("Coming soon")}` : ""}
          </option>)}
        </select>
      </div>
      {selectionError && <p id="ax-workflow-selection-error" className={styles.selectionAlert} role="alert"><AlertCircle size={16} aria-hidden />{t("Please select a workflow.")}</p>}
      <div className={styles.inputHeading}>
        <label htmlFor="ax-workflow-message" className={styles.inputLabel}>{t(informationUpdate && draft?.structured ? "Structured information" : "Request")}</label>
        {informationUpdate && <span id="ax-structuring-status" className={styles.structuringStatus} role="status" aria-live="polite" data-state={structuringState}>
          {extracting && <LoaderCircle className={styles.spinner} size={14} aria-hidden />}{t(structuringLabel)}
        </span>}
      </div>
      <div className={`${styles.composer} ${dragging ? styles.dragging : ""}`} role="group" aria-label={t("Request with text and images")}
        onDragEnter={event => { if (event.dataTransfer.types.includes("Files")) { preventFileDrop(event); dragDepth.current++; setDragging(true); } }}
        onDragOver={event => { if (event.dataTransfer.types.includes("Files")) { preventFileDrop(event); event.dataTransfer.dropEffect = "copy"; } }}
        onDragLeave={event => { preventFileDrop(event); dragDepth.current = Math.max(0, dragDepth.current - 1); if (!dragDepth.current) setDragging(false); }}
        onDrop={event => { if (!event.dataTransfer.files.length) return; preventFileDrop(event); dragDepth.current = 0; setDragging(false); addImages(Array.from(event.dataTransfer.files)); }}>
        <textarea ref={messageInput} id="ax-workflow-message" value={message} disabled={running || extracting} onChange={event => { setMessage(event.target.value); resetResult(); }} maxLength={informationUpdate || !workflowId ? 64000 : 8000} rows={4}
          aria-label={t("Request")} aria-busy={extracting} aria-describedby={informationUpdate ? "ax-structuring-status" : undefined} placeholder={t("Enter a request or paste a screenshot (Ctrl+V)…")} />
        {images.length > 0 && <ul className={styles.images} aria-label={t("Attached images")}>{images.map(file => <ImagePreview key={fileKey(file)} file={file}
          remove={() => removeImage(file)} />)}</ul>}
        <input ref={picker} type="file" accept="image/png,image/jpeg,image/webp" multiple hidden aria-label={t("Upload images")}
          onChange={event => { addImages(Array.from(event.target.files ?? [])); event.target.value = ""; }} />
        <div className={styles.toolbar}>
          <button type="button" className={styles.attach} disabled={running} onClick={() => picker.current?.click()}><ImagePlus size={17} aria-hidden />{t("Add images")}{images.length > 0 && <span className={styles.imageCount}>{images.length}/5</span>}</button>
          {informationUpdate && <button type="button" className={styles.attach} disabled={running || extracting || (!originalInput().trim() && !images.length)} onClick={() => void readImages(files.current, originalInput(), workflowId, draft?.pages)}>{t("Analyse & extract")}</button>}
          <span className={styles.characterCount}>{message.length.toLocaleString()} / {informationUpdate || !workflowId ? "64,000" : "8,000"}</span>
          <button type="button" className={styles.run} disabled={running || extracting || (images.length > 0 && !draft)} onClick={() => void run()} aria-describedby={informationUpdate ? "ax-structuring-status" : images.length ? "ax-workflow-setup-note" : undefined}>{running ? <LoaderCircle className={styles.spinner} size={15} aria-hidden /> : <Play size={15} aria-hidden />}{t(running ? "Running…" : "Run workflow")}</button>
        </div>
        {dragging && <div className={styles.dropOverlay}><Upload size={26} aria-hidden /><strong>{t("Drop images here")}</strong></div>}
      </div>
      {errors.length > 0 && <div role="alert"><ul className={styles.errors}>{errors.map(error => <li key={error}>{error}</li>)}</ul></div>}
      {(informationUpdate ? !!ocrError || (!!draft && draft.needsReview && !extracting) : images.length > 0) && <div id="ax-workflow-setup-note" className={styles.ocrPanel}>
        {!informationUpdate && <p className={styles.localNote}>{t(workflowId ? "Image text is extracted on this device. Review the name and address before running." : "Select a workflow to analyse the recognized text.")}</p>}
        {extracting && !informationUpdate && <p role="status"><LoaderCircle className={styles.spinner} size={14} aria-hidden /> {analysing ? t("Analysing available information…") : t("Extracting Korean text… {percent}%", { percent: ocrProgress })}</p>}
        {ocrError && <p className={styles.imageWarning} role="alert">{t(ocrError)}</p>}
        {!informationUpdate && !extracting && images.length > 0 && <button type="button" className={styles.attach} disabled={running} onClick={() => void readImages(files.current, originalInput())}>{t("Extract again")}</button>}
        {draft && !extracting && <>
          {!ocrError && (!informationUpdate || draft.needsReview) && <p role="status">{t(draft.needsReview ? "Some text is unclear or conflicts. Correct the extracted fields before running." : "Text extracted. The structured input is ready to review.")}</p>}
          {!informationUpdate && <details><summary>{t("Recognized text and original input")}</summary>
            {draft.original && <section><strong>{t("Original input")}</strong><pre>{draft.original}</pre></section>}
            {draft.pages.map((page, index) => <section key={index}><strong>{page.filename}</strong><pre>{page.text}</pre></section>)}
          </details>}
        </>}
      </div>}
    </section>
    <div className={styles.outputColumn} aria-busy={running}>
      <section className={styles.resultPanel} aria-labelledby="ax-workflow-result-title">
        <header className={styles.panelHeader}><h2 id="ax-workflow-result-title">{t("Result")}</h2>
          <span className={styles.status} data-status={running ? "running" : runError ? "failed" : informationResult?.status ?? result?.status ?? "idle"} role="status">{running ? <LoaderCircle className={styles.spinner} size={14} aria-hidden /> : <span aria-hidden />}{t(running ? "Running…" : runError ? "Needs attention" : informationResult ? ({completed: "Completed", blocked: "Needs attention", failed: "Run failed"})[informationResult.status] : result ? workflowStatusLabels[result.status] : "Not started")}</span>
        </header>
        {runError && <p className={styles.imageWarning} role="alert">{t(runError)}</p>}
        {informationResult ? <>
          <p className={styles.response}>{informationResult.response}</p>
          <span className={styles.localNote}>{informationResult.region ? `${informationResult.region} · ` : ""}{t("Finished in {seconds}s", { seconds: (informationResult.duration_ms / 1000).toFixed(1) })}</span>
          {([['roster', '1. 가입자 명부 반영'], ['as_update', '2. AS 시트 반영'], ['member_note', '3. 마스터페이지 일반사항']] as const).map(([key, title]) => {
            const stage = informationResult.receipts[key];
            return <StageDetails key={key} title={title} status={({updated:'Saved and verified', skipped:'Skipped', blocked:'Needs attention', unknown:'Update not confirmed'})[stage.status]} attention={['blocked','unknown'].includes(stage.status)}>
              <p>{stage.reason}</p>
              {!!stage.rows.length && <p>{key === 'member_note' ? '가입자 ID' : '행'}: {stage.rows.join(', ')}</p>}
              {stage.changes.map((change,index) => <p key={index}>{change}</p>)}
            </StageDetails>;
          })}
        </> : result ? <>
          <p className={styles.response}>{result.response}</p>
          <span className={styles.localNote}>{t("Finished in {seconds}s", { seconds: (result.duration_ms / 1000).toFixed(1) })}</span>
          <p className={styles.parsed}>{[result.parsed.lookup_name, result.parsed.address].filter(Boolean).join(" · ")}</p>
          {result.notices.length > 0 && <ul className={styles.notices}>{result.notices.map((notice, i) => <li key={i}>{notice}</li>)}</ul>}
          {result.status === "needs_confirmation" && <div className={styles.candidates}><p>{t("Choose a matching name to continue the AS lookup.")}</p>{result.candidates.map((candidate, i) => <button type="button" key={`${candidate.sheet_alias}-${candidate.row}-${i}`} disabled={running || !candidate.name} onClick={() => candidate.name && void run(candidate.name)}><strong>{candidate.name}</strong><span>{candidate.city} · {t("Row {row}", { row: candidate.row ?? "—" })} · {candidate.address}</span></button>)}</div>}
          <StageDetails title="1. Signal check" status={({connected: "Signal confirmed", disconnected: "Device disconnected", failed: "Signal check failed", skipped: "Skipped"})[result.signal.status]} attention={["failed", "disconnected"].includes(result.signal.status) || ["not_found", "failed", "needs_confirmation"].includes(result.roster.status)}>
            <LookupDetails stage={result.roster} />
            <dl className={styles.signalValues}>
              {result.signal.imei && <div><dt>IMEI ({result.signal.imei_column})</dt><dd>{result.signal.imei}</dd></div>}
              {result.signal.sn && <div><dt>S/N</dt><dd>{result.signal.sn}</dd></div>}
              {result.signal.signal_label && <div><dt>{t("Signal strength")}</dt><dd>{result.signal.signal_label}{result.signal.rssi !== null ? ` (RSSI ${result.signal.rssi})` : ""}</dd></div>}
            </dl>
            {result.signal.reason && <p>{result.signal.reason}</p>}
          </StageDetails>
          <StageDetails title="2. AS sheet update" status={({updated: "Saved and verified", skipped: "Skipped", failed: "Not updated", unknown: "Update not confirmed"})[result.as_update.status]} attention={["failed", "unknown"].includes(result.as_update.status) || ["failed", "not_found"].includes(result.as_lookup.status)}>
            <LookupDetails stage={result.as_lookup} />
            {result.as_update.row && <strong>{t("Row {row}", { row: result.as_update.row })}</strong>}
            {result.as_update.reason && <p>{result.as_update.reason}</p>}
            {result.as_update.changes.length > 0 && <><p>{t(result.as_update.verified ? "Verified values" : "Requested values · not verified")}</p><dl className={styles.updateValues}>{result.as_update.changes.map(change => <div key={change.column}><dt>{change.column}</dt><dd>{change.value}</dd></div>)}</dl></>}
            {result.as_update.y_action === "unchanged" && <p>{t("Y left unchanged: C did not match either completion rule.")}</p>}
            {result.as_update.status === "unknown" && <p className={styles.imageWarning}>{t("Check the AS row before running again. The update may already be saved.")}</p>}
          </StageDetails>
          <StageDetails title="3. Master page · General notes" status={result.member_note ? ({saved: "Saved and verified", already_present: "General note already present", not_found: "No match", needs_confirmation: "Needs attention", blocked: "Needs attention", failed: "Not updated", unknown: "Update not confirmed"})[result.member_note.status] : "Skipped"} attention={!!result.member_note && !["saved", "already_present"].includes(result.member_note.status)}>
            {result.member_note && <>
              <p>{result.member_note.name} · {result.member_note.address}{result.member_note.member_id ? ` · ID ${result.member_note.member_id}` : ""}</p>
              <p>{t(result.member_note.verified ? "Verified values" : "Requested values · not verified")}</p>
              <p>{result.member_note.note}</p>
              <a href="https://admin.ansimk.com/members" target="_blank" rel="noreferrer">{t("Open member admin")}</a>
              {result.member_note.candidates.map(candidate => <p key={candidate.member_id}>{candidate.name} · {candidate.address} · ID {candidate.member_id}</p>)}
              {result.member_note.status === "unknown" && <p className={styles.imageWarning}>{t("Check member general notes before running again. The update may already be saved.")}</p>}
            </>}
          </StageDetails>

          {result.attempts.length > 0 && <details className={styles.help}><summary>{t("Search details")}</summary><ol className={styles.attempts}>{result.attempts.map((a, i) => <li key={`${a.sheet_alias}-${i}`}>{a.city} · {a.sheet_alias}<span>{t(a.status === "found" ? "Match found" : a.status === "not_found" ? "No exact match" : "Run failed")}</span></li>)}</ol></details>}
        </> : !runError && <div className={styles.empty}>{running ? <LoaderCircle className={styles.spinner} size={26} aria-hidden /> : <Inbox size={26} strokeWidth={1.4} aria-hidden />}<h3>{t(running ? informationUpdate ? "명부·AS·마스터페이지 반영 중" : "Checking signal, AS and general notes" : "No results yet")}</h3><p>{running ? t("Elapsed {seconds}s", { seconds: elapsed }) : t("Choose a workflow and add your request.")}</p></div>}
      </section>
    </div>
  </div>;
}
