import { beforeEach, describe, expect, it } from "vitest";

import { useChatStore } from "./useChatStore";

describe("useChatStore", () => {
  beforeEach(() => {
    useChatStore.setState({ messages: [], errorMessage: null });
  });

  it("keeps a visible error alongside the session transcript", () => {
    useChatStore.getState().appendMessage({
      id: "message-1",
      role: "user",
      content: "Generate a report"
    });
    useChatStore.getState().setErrorMessage("The request failed.");

    expect(useChatStore.getState()).toMatchObject({
      errorMessage: "The request failed.",
      messages: [{ id: "message-1", content: "Generate a report" }]
    });
  });

  it("clears an old error without clearing the session transcript", () => {
    useChatStore.getState().appendMessage({
      id: "message-1",
      role: "user",
      content: "Generate a report"
    });
    useChatStore.getState().setErrorMessage("The request failed.");

    useChatStore.getState().setErrorMessage(null);

    expect(useChatStore.getState().errorMessage).toBeNull();
    expect(useChatStore.getState().messages).toHaveLength(1);
  });
});
