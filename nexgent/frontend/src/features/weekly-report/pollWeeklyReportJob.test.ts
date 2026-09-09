import { afterEach, expect, it, vi } from "vitest";
import { weeklyReportBulkClient, type WeeklyReportBulkJobStatus } from "../../shared/api/weeklyReportBulkClient";
import { pollWeeklyReportJob } from "./pollWeeklyReportJob";

const running = { status: "running", max_reports: 10000 } as WeeklyReportBulkJobStatus;
afterEach(() => { vi.restoreAllMocks(); vi.useRealTimers(); });

it("keeps only one slow status request in flight and stops at completion", async () => {
  vi.useFakeTimers();
  let resolve!: (job: WeeklyReportBulkJobStatus) => void;
  const status = vi.spyOn(weeklyReportBulkClient, "status")
    .mockImplementationOnce(() => new Promise((done) => { resolve = done; }))
    .mockResolvedValue({ ...running, status: "completed" });
  const onStatus = vi.fn();
  const stop = pollWeeklyReportJob("job", 2000, onStatus, vi.fn());
  await vi.advanceTimersByTimeAsync(60_000);
  expect(status).toHaveBeenCalledTimes(1);
  resolve(running);
  await vi.advanceTimersByTimeAsync(1999);
  expect(status).toHaveBeenCalledTimes(1);
  await vi.advanceTimersByTimeAsync(1);
  expect(status).toHaveBeenCalledTimes(2);
  await vi.advanceTimersByTimeAsync(60_000);
  expect(status).toHaveBeenCalledTimes(2);
  expect(onStatus).toHaveBeenLastCalledWith(expect.objectContaining({ status: "completed" }));
  stop();
});

it("backs off failures to 30 seconds and resets after recovery", async () => {
  vi.useFakeTimers();
  const status = vi.spyOn(weeklyReportBulkClient, "status").mockRejectedValue(new Error("offline"));
  const stop = pollWeeklyReportJob("job", 2000, vi.fn(), vi.fn());
  for (const delay of [4000, 8000, 16000, 30000, 30000]) {
    const calls = status.mock.calls.length;
    await vi.advanceTimersByTimeAsync(delay - 1);
    expect(status).toHaveBeenCalledTimes(calls);
    await vi.advanceTimersByTimeAsync(1);
    expect(status).toHaveBeenCalledTimes(calls + 1);
  }
  status.mockResolvedValue(running);
  await vi.advanceTimersByTimeAsync(30000);
  const calls = status.mock.calls.length;
  await vi.advanceTimersByTimeAsync(2000);
  expect(status).toHaveBeenCalledTimes(calls + 1);
  stop();
  await vi.advanceTimersByTimeAsync(60000);
  expect(status).toHaveBeenCalledTimes(calls + 1);
});

it("aborts on cleanup and ignores a late response", async () => {
  vi.useFakeTimers();
  let resolve!: (job: WeeklyReportBulkJobStatus) => void;
  const status = vi.spyOn(weeklyReportBulkClient, "status")
    .mockImplementation(() => new Promise((done) => { resolve = done; }));
  const onStatus = vi.fn();
  const stop = pollWeeklyReportJob("job", 2000, onStatus, vi.fn());
  const signal = status.mock.calls[0][1]?.signal;
  stop();
  expect(signal?.aborted).toBe(true);
  resolve(running);
  await vi.advanceTimersByTimeAsync(60000);
  expect(onStatus).not.toHaveBeenCalled();
  expect(status).toHaveBeenCalledTimes(1);
});
