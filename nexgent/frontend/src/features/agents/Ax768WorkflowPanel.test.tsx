import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { Ax768WorkflowPanel } from "./Ax768WorkflowPanel";
import { useLanguage } from "../../shared/i18n";

describe("AX768 workflow selection", () => {
  it("requires an explicit selection and enables the information update development workspace", () => {
    const html = renderToStaticMarkup(<Ax768WorkflowPanel />);
    const select = html.match(/<select[^>]*id="ax-workflow-choice"[\s\S]*?<\/select>/)?.[0] ?? "";
    expect(select).toContain('required=""');
    expect(select).toContain('<option value="" selected="">Select workflow</option>');
    expect(select).toContain('<option value="device_adjustment_power">기기위치조정/전원연결</option>');
    expect(select).toContain('<option value="information_update">정보확인&amp;수정</option>');
    for (const name of ["기기회수", "기기교체", "기기분실", "가입자신규설치"]) {
      expect(select).toContain(`disabled="">${name} · Coming soon</option>`);
    }
    expect((select.match(/<option /g) ?? [])).toHaveLength(7);
    // Keep Run available so missing selection can produce an actionable alert.
    const runButton = (html.match(/<button\b[^>]*>[\s\S]*?<\/button>/g) ?? []).find(button => button.includes("Run workflow"));
    expect(runButton).toBeDefined();
    expect(runButton).not.toContain('disabled');
    expect(html).toContain("Choose a workflow and add your request.");
    expect(html).not.toContain("Workflow status");
    expect(html).not.toContain("Uljin → Gwangmyeong → Yeongdeok → AS → Update");
  });

  it("localizes required selection guidance", () => {
    useLanguage.setState({ language: "ko" });
    const html = renderToStaticMarkup(<Ax768WorkflowPanel />);
    expect(html).toContain("워크플로 선택");
    expect(html).toContain("필수");
  });
});
