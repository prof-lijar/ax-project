/** Conservative extraction: an uncertain or conflicting field stays editable and blank. */
export type OcrPage = { filename: string; text: string; confidence: number };
export type ImageDraft = { message: string; pages: OcrPage[]; original: string; needsReview: boolean; conflicts: boolean };
const roadPattern = /[가-힣0-9·.]+(?:로|길)\s*\d+(?:\s*-\s*\d+)?/g;
const compact = (value: string) => value.normalize("NFKC").replace(/\s+/g, "");
const normalizeAddress = (value: string) => value.replace(/\s*-\s*/g, "-").replace(/([로길])\s*(?=\d)/g, "$1 ");
const labels = new Set(["이름", "성명", "주소", "요청", "신호확인", "수신확인", "가입자", "대상자", "수령인", "연락처", "전화번호", "기기위치조정", "전원연결"]);
function requestedActions(text: string): string[] {
  const value = compact(text);
  return ["기기위치조정", "전원연결"].filter(action => value.includes(action));
}
function candidates(raw: string) {
  const text = raw.normalize("NFKC");
  const names = new Set<string>();
  const addresses = new Set<string>();
  function name(value: string) {
    const normalized = compact(value.replace(/[,.~]+$/g, ""));
    if (/^[가-힣]{2,5}$/.test(normalized) && !labels.has(normalized)) names.add(normalized);
  }
  for (const line of text.split(/[\r\n]+/)) {
    const roads = [...line.matchAll(roadPattern)];
    roads.forEach(match => addresses.add(normalizeAddress(match[0])));
    const labeled = line.match(/^\s*(?:이\s*름|성\s*명|가입자명|대상자명)\s*[:：]?\s*([가-힣\s]+?)\s*$/);
    if (labeled) name(labeled[1]);
    for (const match of line.matchAll(/([가-힣](?:[ \t]*[가-힣]){1,4})\s*님/g)) name(match[1]);
    if (roads.length === 1) {
      const suffix = line.slice(roads[0].index! + roads[0][0].length).trim().replace(/^,\s*/, "");
      const person = suffix.match(/^([가-힣](?:[ \t]*[가-힣]){1,4})(?:님|,|$)/);
      if (person) name(person[1]);
    }
    // A name on its own line is common on labels. Administrative region lines
    // and known field headings are not subscriber names.
    if (/^\s*[가-힣](?:[ \t]*[가-힣]){1,3}\s*$/.test(line) && !/[시군구읍면동리]\s*$/.test(line)) name(line);
  }
  return { names, addresses };
}
export function makeImageDraft(pages: OcrPage[], original: string): ImageDraft {
  const text = [original, ...pages.map(page => page.text)].join("\n");
  const all = candidates(text);
  const actions = requestedActions(text);
  const conflicts = all.addresses.size > 1 || all.names.size > 1 || actions.length > 1;
  const name = all.names.size === 1 ? [...all.names][0] : "";
  const address = all.addresses.size === 1 ? [...all.addresses][0] : "";
  return {
    message: `이름: ${name}\n주소: ${address}\n요청: ${actions.length === 1 ? actions[0] + " " : actions.length > 1 ? "기기위치조정/전원연결 " : ""}신호확인`,
    original, pages,
    conflicts,
    needsReview: !name || !address || conflicts || pages.some(page => page.confidence < 65),
  };
}
/** Keep the existing deployed text-only workflow contract. Never send raw OCR as instructions. */
export function workflowMessage(input: string): string {
  if (!/^\s*(?:이름|주소|요청)\s*[:：]/m.test(input)) return input;
  const fields = new Map<string, string>();
  for (const line of input.split(/\r?\n/).filter(line => line.trim())) {
    const match = line.match(/^\s*(이름|주소|요청)\s*[:：]\s*(.*?)\s*$/);
    if (!match || fields.has(match[1])) throw new Error("Review the extracted name and address before running.");
    fields.set(match[1], match[2]);
  }
  const name = compact(fields.get("이름") ?? "");
  const address = fields.get("주소") ?? "";
  if (!/^[가-힣]{2,5}$/.test(name) || (address && [...address.matchAll(roadPattern)].length !== 1)) {
    throw new Error("Review the extracted name and address before running.");
  }
  // Only the two workflow actions survive normalization; raw OCR is never executed.
  const actions = requestedActions(fields.get("요청") ?? "");
  if (actions.length > 1) throw new Error("Choose either device adjustment or power connection in the request.");
  const road = address.match(roadPattern)?.[0];
  return `${road ? normalizeAddress(road) + " " : ""}${name}님 ${actions.length ? actions[0] + " " : ""}신호확인요.`;
}
