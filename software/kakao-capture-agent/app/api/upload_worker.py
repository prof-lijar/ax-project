import asyncio
import threading
import time

import httpx

from app.api.client import UploadError, retry_delay, upload


class UploadWorker(threading.Thread):
    def __init__(self, queue, config, token_provider, notify):
        super().__init__(name="uploads", daemon=False)
        self.queue, self.config = queue, config
        self.token_provider, self.notify = token_provider, notify
        self.shutdown = threading.Event()
        self.auth_paused = threading.Event()

    def retry(self):
        self.queue.retry_failed(self.config.api_url)
        self.auth_paused.clear()

    def run(self):
        asyncio.run(self.process())

    async def process(self):
        maintenance_at = 0
        async with httpx.AsyncClient(
            timeout=self.config.request_timeout_seconds, follow_redirects=False, trust_env=False
        ) as client:
            while not self.shutdown.is_set():
                job = None
                try:
                    if time.monotonic() >= maintenance_at:
                        await asyncio.to_thread(self.queue.maintain)
                        maintenance_at = time.monotonic() + 60
                    job = (
                        None
                        if self.auth_paused.is_set()
                        else await asyncio.to_thread(self.queue.claim, self.config.api_url)
                    )
                    if not job:
                        await asyncio.sleep(0.25)
                        continue
                    self.notify("Uploading queued capture")
                    try:
                        token = self.token_provider(job["destination"])
                        try:
                            await asyncio.wait_for(
                                upload(client, job, token),
                                timeout=self.config.request_timeout_seconds,
                            )
                        except TimeoutError:
                            raise UploadError(
                                "Upload exceeded request deadline", retryable=True
                            ) from None
                    except UploadError as error:
                        count = job["retry_count"] + 1
                        delay = (
                            retry_delay(count, error.retry_after)
                            if error.retryable and count <= self.config.max_retries
                            else None
                        )
                        await asyncio.to_thread(
                            self.queue.fail, job["capture_id"], str(error), count, delay
                        )
                        if error.authentication:
                            self.auth_paused.set()
                        self.notify(
                            str(error)
                            + (
                                "; retry scheduled"
                                if delay is not None
                                else "; operator review required"
                            )
                        )
                    except Exception:
                        await asyncio.to_thread(
                            self.queue.fail,
                            job["capture_id"],
                            "Upload configuration or credential error",
                            job["retry_count"] + 1,
                        )
                        self.notify(
                            "Upload configuration or credential error; operator review required"
                        )
                    else:
                        await asyncio.to_thread(self.queue.acknowledge, job["capture_id"])
                        self.notify("Upload successful")
                except Exception:
                    if job:
                        try:
                            await asyncio.to_thread(self.queue.release, job["capture_id"])
                        except Exception:
                            pass  # Restart recovery also releases interrupted jobs.
                    self.notify("Upload queue storage error; retrying after 5 seconds")
                    for _ in range(20):
                        if self.shutdown.is_set():
                            break
                        await asyncio.sleep(0.25)
