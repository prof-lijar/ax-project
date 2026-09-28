import { afterEach, describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { SignIn } from "../../features/accounts/AccountApp";
import { AgentsPageView } from "../../features/agents/AgentsPage";
import { SearchPanel, isDeleteConfirmationValid } from "../../features/rag/RagPage";
import { formatWeeklySchedule } from "../../features/weekly-report/WeeklyReportSchedulePanel";
import { createConversation, useChatStore } from "../state/useChatStore";
import { LANGUAGE_STORAGE_KEY, locale, readLanguage, t, useLanguage } from ".";
import ko from "./ko.json";

afterEach(() => {
  useLanguage.setState({ language: "en" });
  vi.unstubAllGlobals();
});

describe("language preference", () => {
  it.each([null, "", "broken-json", "fr", '{"language":"ko"}']) (
    "defaults to Korean for an absent or invalid preference (%s)", (value) => {
      expect(readLanguage({ getItem: () => value })).toBe("ko");
    }
  );

  it("restores a saved Korean preference and survives denied reads", () => {
    expect(readLanguage({ getItem: () => "ko" })).toBe("ko");
    expect(readLanguage({ getItem: () => "en" })).toBe("en");
    expect(readLanguage({ getItem: () => { throw new Error("denied"); } })).toBe("ko");
  });

  it("persists just the language and restores it on initialization", async () => {
    const values = new Map<string, string>();
    vi.stubGlobal("window", { localStorage: {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => values.set(key, value)
    } });
    useLanguage.getState().setLanguage("ko");
    expect([...values]).toEqual([[LANGUAGE_STORAGE_KEY, "ko"]]);
    expect(locale()).toBe("ko-KR");
    vi.resetModules();
    const reloaded = await import(".");
    expect(reloaded.useLanguage.getState().language).toBe("ko");
    reloaded.useLanguage.getState().setLanguage("en");
    expect(values.get(LANGUAGE_STORAGE_KEY)).toBe("en");
  });

  it("switches in memory when storage writes fail, without changing drafts", () => {
    vi.stubGlobal("window", { get localStorage() { throw new Error("denied"); } });
    const conversation = { ...createConversation(), draft: "내 초안 / My draft" };
    const previous = useChatStore.getState();
    useChatStore.setState({ conversations: [conversation], activeId: conversation.id });
    try {
      useLanguage.getState().setLanguage("ko");
      expect(t("Send message")).toBe("메시지 보내기");
      expect(useChatStore.getState().conversations[0]).toBe(conversation);
      useLanguage.getState().setLanguage("en");
      expect(t("Send message")).toBe("Send message");
    } finally {
      useChatStore.setState(previous);
    }
  });
});

describe("interface translations", () => {
  it("switches sign-in labels and accessibility copy without changing form field names", () => {
    const render = () => renderToStaticMarkup(<SignIn onSignedIn={async () => {}} />);
    expect(render()).toContain("Sign in");
    useLanguage.setState({ language: "ko" });
    const korean = render();
    expect(korean).toContain("로그인");
    expect(korean).toContain('aria-label="언어"');
    expect(korean).toContain('name="username"');
    expect(korean).toContain('name="password"');
    useLanguage.setState({ language: "en" });
    expect(render()).toContain("Sign in");
  });

  it("renders Korean co-worker empty states and count grammar", () => {
    useLanguage.setState({ language: "ko" });
    const markup = renderToStaticMarkup(<AgentsPageView agents={[]} search="" />);
    expect(markup).toContain("함께 일하는 동료");
    expect(markup).toContain("아직 동료가 없습니다");
    expect(markup).toContain("동료 0명");
    expect(markup).toContain('aria-label="동료 찾기"');
  });

  it("keeps user source text intact while translating knowledge result counts", () => {
    useLanguage.setState({ language: "ko" });
    const markup = renderToStaticMarkup(<SearchPanel query="my original query" searchedQuery="my original query"
      topKInput="5" topKIsValid isPending={false} apiError={null}
      results={[]} timing={null} onQueryChange={() => {}} onTopKChange={() => {}} onSubmit={() => {}} />);
    expect(markup).toContain("일치하는 구절 0개");
    expect(markup).toContain("my original query");
    expect(isDeleteConfirmationValid("DELETE")).toBe(true);
    expect(isDeleteConfirmationValid("삭제")).toBe(false);
  });

  it("formats schedules in Korean and preserves raw substitution values", () => {
    useLanguage.setState({ language: "ko" });
    expect(formatWeeklySchedule("monday", "03:00")).toBe("매주 월요일 오전 3:00");
    expect(t("Remove {0}", { 0: "$& <original>.txt" })).toBe("$& <original>.txt 제거");
    expect(t("unknown server content")).toBe("unknown server content");
    expect(t("constructor")).toBe("constructor");
  });

  it("has nonempty translations and no undeclared interpolation placeholders", () => {
    for (const [english, korean] of Object.entries(ko)) {
      expect(korean.trim(), english).not.toBe("");
      const original = new Set(english.match(/\{\w+\}/g) ?? []);
      for (const token of korean.match(/\{\w+\}/g) ?? []) expect(original.has(token), english).toBe(true);
    }
  });
});
