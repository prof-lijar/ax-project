import type { OcrPage } from "./ax768ImageInput";

type Worker = {
  setParameters(params: Record<string, string>): Promise<unknown>;
  recognize(image: HTMLCanvasElement, options: { rotateAuto: boolean }): Promise<{ data: { text: string; confidence: number } }>;
  terminate(): Promise<unknown>;
};
type Engine = { createWorker(languages: string[], mode: number, options: Record<string, unknown>): Promise<Worker> };
declare global { interface Window { Tesseract?: Engine } }
const ROOT = "/ocr/tesseract-7.0.0";
let loading: Promise<Engine> | undefined;
function engine(): Promise<Engine> {
  if (window.Tesseract) return Promise.resolve(window.Tesseract);
  if (!loading) loading = new Promise<Engine>((resolve, reject) => {
    const script = document.createElement("script");
    const timeout = window.setTimeout(() => fail(), 30_000);
    const fail = () => { window.clearTimeout(timeout); script.remove(); loading = undefined; reject(new Error("Image text extraction failed. Retry or enter the name and address manually.")); };
    script.src = `${ROOT}/tesseract.min.js`; script.async = true;
    script.onload = () => { window.clearTimeout(timeout); if (window.Tesseract) resolve(window.Tesseract); else fail(); };
    script.onerror = fail;
    document.head.append(script);
  });
  return loading;
}
async function enhancedImage(file: File): Promise<HTMLCanvasElement> {
  const bitmap = await createImageBitmap(file, { imageOrientation: "from-image" });
  try {
    if (!bitmap.width || !bitmap.height || bitmap.width * bitmap.height > 24_000_000) throw new Error("Use an image smaller than 24 megapixels.");
    const scale = Math.min(2, 2600 / Math.max(bitmap.width, bitmap.height));
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(bitmap.width * scale); canvas.height = Math.round(bitmap.height * scale);
    const ctx = canvas.getContext("2d", { willReadFrequently: true });
    if (!ctx) throw new Error("Image text extraction is unavailable in this browser.");
    ctx.fillStyle = "white"; ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    const pixels = ctx.getImageData(0, 0, canvas.width, canvas.height);
    const histogram = new Uint32Array(256);
    for (let i = 0; i < pixels.data.length; i += 4) {
      const gray = Math.round(0.299 * pixels.data[i] + 0.587 * pixels.data[i + 1] + 0.114 * pixels.data[i + 2]);
      pixels.data[i] = gray; histogram[gray]++;
    }
    const total = canvas.width * canvas.height;
    let low = 0, high = 255, count = 0;
    while (low < 255 && count + histogram[low] < total * 0.01) count += histogram[low++];
    count = 0;
    while (high > low && count + histogram[high] < total * 0.01) count += histogram[high--];
    for (let i = 0; i < pixels.data.length; i += 4) {
      const value = high - low > 20 ? Math.max(0, Math.min(255, (pixels.data[i] - low) * 255 / (high - low))) : pixels.data[i];
      pixels.data[i] = pixels.data[i + 1] = pixels.data[i + 2] = value;
    }
    ctx.putImageData(pixels, 0, 0);
    return canvas;
  } finally { bitmap.close(); }
}
export async function extractImageText(files: File[], signal: AbortSignal, progress: (value: number) => void): Promise<OcrPage[]> {
  let worker: Worker | undefined;
  let stopped = false;
  let timer: number | undefined;
  let abort = () => {};
  const stoppedPromise = new Promise<never>((_, reject) => {
    abort = () => { stopped = true; reject(new Error("Image text extraction was cancelled.")); };
    signal.addEventListener("abort", abort, { once: true });
    timer = window.setTimeout(() => { stopped = true; reject(new Error("Image text extraction timed out. Use a clearer crop and retry.")); }, 120_000);
  });
  const work = async () => {
    if (signal.aborted) throw new Error("Image text extraction was cancelled.");
    const api = await engine();
    if (stopped) throw new Error("Image text extraction was cancelled.");
    let index = 0;
    worker = await api.createWorker(["kor", "eng"], 1, {
      workerPath: `${ROOT}/worker.min.js`, corePath: `${ROOT}/tesseract-core-lstm.wasm.js`,
      langPath: ROOT, workerBlobURL: false, gzip: true, cacheMethod: "none",
      logger: (event: { status: string; progress: number }) => {
        if (!stopped && event.status === "recognizing text") progress(Math.round((index + event.progress) / files.length * 100));
      },
      errorHandler: () => {},
    });
    if (stopped) { await worker.terminate(); throw new Error("Image text extraction was cancelled."); }
    await worker.setParameters({ tessedit_pageseg_mode: "6", preserve_interword_spaces: "1" });
    const pages: OcrPage[] = [];
    for (const file of files) {
      if (stopped) throw new Error("Image text extraction was cancelled.");
      const canvas = await enhancedImage(file);
      try {
        // EXIF orientation is already applied. Automatic deskew can rotate a
        // single Korean address line incorrectly (observed 0.3 rad on straight text).
        const { data } = await worker.recognize(canvas, { rotateAuto: false });
        if (!data.text.trim()) throw new Error("No readable text was found. Use a clearer crop or type the details.");
        if (data.text.length > 8000) throw new Error("Too much image text. Crop to one subscriber and retry.");
        pages.push({ filename: file.name, text: data.text.trim(), confidence: data.confidence });
      } finally { canvas.width = canvas.height = 1; }
      index++;
    }
    return pages;
  };
  try { return await Promise.race([work(), stoppedPromise]); }
  finally { stopped = true; window.clearTimeout(timer); signal.removeEventListener("abort", abort); await worker?.terminate(); }
}
