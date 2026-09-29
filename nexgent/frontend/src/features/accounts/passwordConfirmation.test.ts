import { describe, expect, it, vi } from "vitest";
import { useLanguage } from "../../shared/i18n";
import { clearPasswordConfirmationError, validatePasswordConfirmation } from "./passwordConfirmation";

function resetForm(password: string, repeated: string) {
  let message = "";
  const confirmation = { value: repeated, setCustomValidity: vi.fn((value: string) => { message = value; }) };
  const form = {
    elements: { namedItem: (name: string) => name === "password" ? { value: password } : confirmation },
    reportValidity: vi.fn(() => !message && password.length >= 4 && repeated.length >= 4)
  } as unknown as HTMLFormElement;
  return { form, confirmation };
}

describe("password reset confirmation", () => {
  it("blocks mismatches and reports the error in Korean", () => {
    useLanguage.setState({ language: "ko" });
    const { form, confirmation } = resetForm("abcd", "abce");
    expect(validatePasswordConfirmation(form)).toBe(false);
    expect(confirmation.setCustomValidity).toHaveBeenCalledWith("비밀번호가 일치하지 않습니다.");
    expect(form.reportValidity).toHaveBeenCalledOnce();
  });

  it("clears a previous mismatch when either field changes and accepts the corrected password", () => {
    const { form, confirmation } = resetForm("abcd", "abce");
    expect(validatePasswordConfirmation(form)).toBe(false);
    clearPasswordConfirmationError(form);
    expect(confirmation.setCustomValidity).toHaveBeenLastCalledWith("");
    confirmation.value = "abcd";
    expect(validatePasswordConfirmation(form)).toBe(true);
  });

  it("preserves exact characters instead of trimming passwords", () => {
    const { form } = resetForm("abcd", "abcd ");
    expect(validatePasswordConfirmation(form)).toBe(false);
  });

  it("does not bypass required field validation for two empty passwords", () => {
    expect(validatePasswordConfirmation(resetForm("", "").form)).toBe(false);
  });
});
