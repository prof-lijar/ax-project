import { create } from "zustand";
import { ax768Client, Ax768ClientError, type Ax768CaseId, type Ax768Result } from "../api/ax768Client";

export interface Ax768Run { id: string; caseId: Ax768CaseId; message: string; startedAt: number; result: Ax768Result | null; error: string | null; outcome: "unknown" | "blocked" | null }
interface Ax768State {
  selectedCase: Ax768CaseId; drafts: Partial<Record<Ax768CaseId, string>>;
  active: Ax768Run | null; history: Ax768Run[]; selectedRunId: string | null;
  selectCase: (id: Ax768CaseId) => void; setDraft: (value: string) => void;
  selectRun: (id: string) => void; run: () => Promise<void>; reset: () => void;
}
let generation = 0;
let sequence = 0;
export const useAx768Store = create<Ax768State>((set, get) => ({
  selectedCase: "4.2", drafts: {}, active: null, history: [], selectedRunId: null,
  selectCase: selectedCase => set({ selectedCase }),
  setDraft: value => set(s => ({ drafts: { ...s.drafts, [s.selectedCase]: value } })),
  selectRun: selectedRunId => set({ selectedRunId }),
  reset: () => { generation++; set({ selectedCase: "4.2", drafts: {}, active: null, history: [], selectedRunId: null }); },
  run: async () => {
    const state = get();
    if (state.active) return;
    const message = (state.drafts[state.selectedCase] ?? "").trim();
    if (!message || message.length > 8000) return;
    const epoch = generation;
    const run: Ax768Run = { id: `ax-${Date.now()}-${++sequence}`, caseId: state.selectedCase, message,
      startedAt: Date.now(), result: null, error: null, outcome: null };
    set({ active: run, selectedRunId: null });
    try { run.result = await ax768Client.run(run.caseId, message); }
    catch (error) {
      run.error = error instanceof Error ? error.message : "The result could not be confirmed. Inspect the sheet before running again.";
      run.outcome = error instanceof Ax768ClientError ? error.outcome : "unknown";
    }
    if (epoch !== generation) return;
    set(s => ({ active: null, history: [run, ...s.history].slice(0, 20), selectedRunId: run.id }));
  }
}));
