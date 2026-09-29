import { t } from "../../shared/i18n";

export function clearPasswordConfirmationError(form: HTMLFormElement) {
  const confirmation = form.elements.namedItem("confirm_password") as HTMLInputElement;
  confirmation.setCustomValidity("");
}

export function validatePasswordConfirmation(form: HTMLFormElement): boolean {
  const password = form.elements.namedItem("password") as HTMLInputElement;
  const confirmation = form.elements.namedItem("confirm_password") as HTMLInputElement;
  confirmation.setCustomValidity(password.value === confirmation.value
    ? "" : t("Passwords do not match."));
  return form.reportValidity();
}
