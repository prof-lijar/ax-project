import { create } from "zustand";
import ko from "./ko.json";

export type Language = "en" | "ko";
export const LANGUAGE_STORAGE_KEY = "nexgent.language";

export function readLanguage(storage?: Pick<Storage, "getItem">): Language {
  try {
    const value = (storage ?? window.localStorage).getItem(LANGUAGE_STORAGE_KEY);
    return value === "en" ? "en" : "ko";
  } catch {
    return "ko";
  }
}

export const useLanguage = create<{
  language: Language;
  setLanguage: (language: Language) => void;
}>((set) => ({
  language: readLanguage(),
  setLanguage: (language) => {
    if (language !== "en" && language !== "ko") return;
    try {
      window.localStorage.setItem(LANGUAGE_STORAGE_KEY, language);
    } catch {
      // A blocked/full storage must not prevent switching for this session.
    }
    set({ language });
  }
}));

export function locale() {
  return useLanguage.getState().language === "ko" ? "ko-KR" : "en-US";
}

/** Only pass product copy here; user content and service payloads stay intact. */
export function t(message: string, values?: Record<string, string | number>): string {
  const translated = useLanguage.getState().language === "ko" && Object.prototype.hasOwnProperty.call(ko, message)
    ? (ko as Record<string, string>)[message]
    : message;
  return values
    ? translated.replace(/\{(\w+)\}/g, (placeholder, name: string) => String(values[name] ?? placeholder))
    : translated;
}
