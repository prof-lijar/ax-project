import {
  isBulkJobTerminal,
  weeklyReportBulkClient,
  type WeeklyReportBulkJobStatus
} from "../../shared/api/weeklyReportBulkClient";

// Schedule only after settlement so a slow service cannot queue status requests.
export function pollWeeklyReportJob(
  jobId: string,
  intervalMs: number,
  onStatus: (job: WeeklyReportBulkJobStatus) => void,
  onError: (error: unknown) => void
): () => void {
  const controller = new AbortController();
  let timer: ReturnType<typeof setTimeout> | undefined;
  let delay = intervalMs;

  async function refresh() {
    try {
      const job = await weeklyReportBulkClient.status(jobId, {
        signal: controller.signal
      });
      if (controller.signal.aborted) return;
      onStatus(job);
      if (isBulkJobTerminal(job.status)) return;
      delay = intervalMs;
    } catch (error) {
      if (controller.signal.aborted) return;
      onError(error);
      delay = Math.min(delay * 2, 30_000);
    }
    if (!controller.signal.aborted) {
      timer = setTimeout(() => void refresh(), delay);
    }
  }

  void refresh();
  return () => {
    controller.abort();
    clearTimeout(timer);
  };
}
